"""outbound_date_fix.py를 outbound.py/outbound_entry.py에 인라인하기 전,
실제로 활성화돼 있던 동작(매출처 최근거래일 폴백, 수출대기 재고 숨김,
outbound_business._BASE_* 오염 방어)을 고정하는 특성화 테스트."""

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import nohtus.db as db
import nohtus.pages.outbound as outbound_page
import nohtus.pages.outbound_business as outbound_business
import nohtus.pages.outbound_entry as outbound_entry


def _make_db(path):
    con = sqlite3.connect(path)
    try:
        con.executescript(
            """
            CREATE TABLE inventory(
                id INTEGER PRIMARY KEY, company TEXT, product_name TEXT,
                warehouse_name TEXT, lot TEXT, exp_date TEXT, location TEXT, qty INTEGER
            );
            CREATE TABLE outbound_orders(
                id INTEGER PRIMARY KEY, order_date TEXT, title TEXT, status TEXT,
                created_at TEXT, customer_name TEXT, customer_company TEXT
            );
            CREATE TABLE outbound_order_items(
                id INTEGER PRIMARY KEY, order_id INTEGER, product_name TEXT, qty INTEGER,
                company TEXT
            );
            CREATE TABLE customer_last_sales(
                id INTEGER PRIMARY KEY AUTOINCREMENT, customer_name TEXT NOT NULL,
                company TEXT NOT NULL DEFAULT '', last_sale_date TEXT NOT NULL,
                source_company TEXT, updated_at TEXT, UNIQUE(customer_name, company)
            );
            """
        )
        con.commit()
    finally:
        con.close()


class LastSaleFallbackTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self.temp_dir.name) / "wms.db"
        _make_db(self.db_path)
        self.db_path_patcher = patch.object(db, "DB_PATH", self.db_path)
        self.db_path_patcher.start()

    def tearDown(self):
        self.db_path_patcher.stop()
        try:
            self.temp_dir.cleanup()
        except PermissionError:
            pass

    def _seed_order(self, customer, company, order_date, product="제품A", qty=5, status="완료"):
        con = sqlite3.connect(self.db_path)
        try:
            cur = con.cursor()
            cur.execute(
                "INSERT INTO outbound_orders(order_date, title, status, created_at, customer_name, customer_company) "
                "VALUES(?,?,?,?,?,?)",
                (order_date, f"{customer} - 테스트", status, f"{order_date} 09:00:00", customer, company),
            )
            order_id = cur.lastrowid
            cur.execute(
                "INSERT INTO outbound_order_items(order_id, product_name, qty) VALUES(?,?,?)",
                (order_id, product, qty),
            )
            con.commit()
        finally:
            con.close()

    def test_exact_map_hit_is_used_first(self):
        exact_map = {("거래처A", "노투스"): "2026-01-01"}
        name_map = {"거래처A": "2020-01-01"}
        last_date = outbound_page._resolved_last_sale_date("거래처A", "노투스", exact_map, name_map)
        self.assertEqual(last_date, "2026-01-01")

    def test_falls_back_to_name_map_when_company_is_blank(self):
        # company가 비어 있을 때만 name_map을 본다 — company가 있는데 exact_map에
        # 없으면 name_map이 아니라 바로 실제 출고 이력으로 폴백한다(아래 테스트).
        exact_map = {}
        name_map = {"거래처A": "2025-06-01"}
        last_date = outbound_page._resolved_last_sale_date("거래처A", "", exact_map, name_map)
        self.assertEqual(last_date, "2025-06-01")

    def test_falls_back_to_real_order_history_when_maps_are_empty(self):
        self._seed_order("거래처A", "노투스", "2026-02-15")
        last_date = outbound_page._resolved_last_sale_date("거래처A", "노투스", {}, {})
        self.assertEqual(last_date, "2026-02-15")

    def test_last_sale_text_reflects_history_fallback(self):
        self._seed_order("거래처A", "노투스", "2026-02-15")
        text = outbound_page._last_sale_text("거래처A", "노투스", {}, {})
        self.assertIn("2026-02-15", text)

    def test_customer_select_label_also_falls_back_to_history(self):
        self._seed_order("거래처A", "노투스", "2026-02-15")

        class Row:
            customer_name = "거래처A"
            company = "노투스"

        label = outbound_page._customer_select_label(Row(), {}, {})
        self.assertIn("2026-02-15", label)

    def test_cancelled_order_is_not_used_as_recent_history(self):
        self._seed_order("거래처A", "노투스", "2026-03-01", status="취소됨")
        last_date = outbound_page._resolved_last_sale_date("거래처A", "노투스", {}, {})
        self.assertEqual(last_date, "")


class InventoryQueryExportWaitingFilterTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self.temp_dir.name) / "wms.db"
        _make_db(self.db_path)
        con = sqlite3.connect(self.db_path)
        try:
            con.executemany(
                "INSERT INTO inventory(company, product_name, warehouse_name, lot, exp_date, location, qty) "
                "VALUES(?,?,?,?,?,?,?)",
                [
                    ("노투스", "제품A", "ERP-A", "LOT-1", "2027-01-01", "A1-01-01", 10),
                    ("노투스", "제품A", "ERP-A", "LOT-2", "2027-01-01", "P-1", 5),
                    ("NOH", "제품A", "ERP-A", "LOT-3", "2027-01-01", "P2", 3),
                ],
            )
            con.commit()
        finally:
            con.close()
        self.db_path_patcher = patch.object(db, "DB_PATH", self.db_path)
        self.db_path_patcher.start()

    def tearDown(self):
        self.db_path_patcher.stop()
        try:
            self.temp_dir.cleanup()
        except PermissionError:
            pass

    def test_company_scoped_query_excludes_export_waiting_locations(self):
        rows = outbound_page._inventory_query_for_outbound("제품A", "노투스")
        self.assertEqual(sorted(rows["location"].tolist()), ["A1-01-01"])

    def test_ignore_company_query_excludes_export_waiting_locations_across_companies(self):
        rows = outbound_page._inventory_query_for_outbound("제품A", "", ignore_company=True)
        self.assertEqual(sorted(rows["location"].tolist()), ["A1-01-01"])


class OutboundBusinessBaseWidgetResetTests(unittest.TestCase):
    """outbound_business._BASE_*가 (다른 패치로) 오염돼 있어도, 일반 출고지시
    진입점을 통과하는 동안에는 항상 진짜 네이티브 위젯으로 강제 리셋되고,
    끝나면 원래 값으로 복원되는지 확인한다."""

    def test_base_attrs_are_reset_during_render_and_restored_after(self):
        def fake_widget(*args, **kwargs):
            return None

        outbound_business._BASE_TEXT_INPUT = fake_widget
        outbound_business._BASE_CHECKBOX = fake_widget
        outbound_business._BASE_DATA_EDITOR = fake_widget
        outbound_business._BASE_MARKDOWN = fake_widget
        outbound_business._BASE_CAPTION = fake_widget

        seen_during_render = {}

        def stub_page_outbound():
            seen_during_render["text_input"] = outbound_business._BASE_TEXT_INPUT
            seen_during_render["checkbox"] = outbound_business._BASE_CHECKBOX

        with patch.object(outbound_entry, "_page_outbound", stub_page_outbound):
            outbound_entry.page_outbound()

        self.assertIs(
            seen_during_render["text_input"],
            outbound_entry._OUTBOUND_NATIVE_WIDGETS["text_input"],
        )
        self.assertIs(
            seen_during_render["checkbox"],
            outbound_entry._OUTBOUND_NATIVE_WIDGETS["checkbox"],
        )
        # 렌더링이 끝난 뒤에는 오염됐던(하지만 호출 전 값이었던) fake_widget로 복원된다.
        self.assertIs(outbound_business._BASE_TEXT_INPUT, fake_widget)
        self.assertIs(outbound_business._BASE_CHECKBOX, fake_widget)


if __name__ == "__main__":
    unittest.main()
