import ast
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import nohtus.pages.export_waiting as export_waiting_page
import nohtus.pages.outbound as outbound_page


class ExportWaitingSaveCustomerNeutralizedTests(unittest.TestCase):
    """수출대기 저장은 export_waiting_orders.id를 만들고, 그 id는 outbound_orders의
    id 체계와 무관하다. patched_save가 항상 0을 반환하던 예전 버그는 우연히
    _save_outbound_customer(0, ...)를 무해한 no-op으로 만들어 사고를 막고
    있었을 뿐이다. 이제 실제 order_id를 반환하므로, outbound_page._save_outbound_customer
    자체를 수출대기 렌더링 동안 명시적으로 무력화해야 한다. 이 계약이 깨지면
    id가 우연히 겹치는 다른 출고지시서의 매출처 정보를 지워버릴 수 있다."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "ew.db"

        class ClosingConnection(sqlite3.Connection):
            def __exit__(self, exc_type, exc_value, traceback):
                try:
                    return super().__exit__(exc_type, exc_value, traceback)
                finally:
                    self.close()

        def connect_test_db():
            return sqlite3.connect(self.db_path, factory=ClosingConnection)

        self.connect_patchers = [
            patch("nohtus.services.export_waiting.connect", connect_test_db),
            patch("nohtus.pages.export_waiting.connect", connect_test_db),
        ]
        for p in self.connect_patchers:
            p.start()

        with sqlite3.connect(self.db_path, factory=ClosingConnection) as con:
            con.execute(
                """CREATE TABLE inventory(
                       id INTEGER PRIMARY KEY,location TEXT,company TEXT,product_name TEXT,
                       warehouse_name TEXT,lot TEXT,exp_date TEXT,qty INTEGER,updated_at TEXT
                   )"""
            )

        self._orig_save_customer = outbound_page._save_outbound_customer

    def tearDown(self):
        for p in self.connect_patchers:
            p.stop()
        outbound_page._save_outbound_customer = self._orig_save_customer
        self.temp_dir.cleanup()

    def test_save_outbound_customer_is_neutralized_during_render_and_restored_after(self):
        captured = {}

        def stub_page_outbound():
            captured["during_render"] = outbound_page._save_outbound_customer
            return "rendered"

        with patch.object(export_waiting_page, "_page_outbound", side_effect=stub_page_outbound):
            export_waiting_page.page_export_waiting()

        self.assertIn("during_render", captured)
        self.assertIsNot(captured["during_render"], self._orig_save_customer)
        # 어떤 id를 넘겨도 아무 행도 건드리지 않아야 한다.
        self.assertIsNone(captured["during_render"](999999, {"customer_name": "SHOULD_NOT_WRITE"}))
        self.assertIs(outbound_page._save_outbound_customer, self._orig_save_customer)

    def test_save_outbound_customer_restored_even_when_render_raises(self):
        with patch.object(export_waiting_page, "_page_outbound", side_effect=RuntimeError("boom")):
            with self.assertRaisesRegex(RuntimeError, "boom"):
                export_waiting_page.page_export_waiting()

        self.assertIs(outbound_page._save_outbound_customer, self._orig_save_customer)


class PatchedSaveReturnsRealOrderIdTests(unittest.TestCase):
    """patched_save가 다시 상수 0을 반환하도록 되돌아가면 위 안전장치(neutralize)에만
    의존하게 되어 취약해진다. 실제 order_id를 반환하는 것 자체도 회귀 테스트로 고정한다."""

    def test_patched_save_returns_result_order_id_not_a_constant(self):
        source = Path(export_waiting_page.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        page_export_waiting = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "page_export_waiting"
        )
        patched_save = next(
            node for node in ast.walk(page_export_waiting)
            if isinstance(node, ast.FunctionDef) and node.name == "patched_save"
        )
        returns = [n for n in ast.walk(patched_save) if isinstance(n, ast.Return)]
        self.assertTrue(returns, "patched_save에 return 문이 없습니다.")
        last_return_source = ast.unparse(returns[-1].value)
        self.assertNotEqual(last_return_source, "0")
        self.assertIn("order_id", last_return_source)


if __name__ == "__main__":
    unittest.main()
