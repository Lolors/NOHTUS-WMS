import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nohtus.services.outbound_orders import save_outbound_order, update_outbound_order


class UpdateOutboundOrderLineCancelHistoryTests(unittest.TestCase):
    """출고지시 수정 시, 품목 하나를 통째로 다른 품목으로 바꾸면(예: A사업장 3개를
    취소하고 B사업장 3개로 교체) 두 줄 다 '출고지시 재차감'으로 찍혀서 어느 쪽이
    취소이고 어느 쪽이 새 출고인지 헷갈리던 문제를 고친다. 완전히 빠지는 품목은
    이제 '출고지시취소'로 남긴다(기존 전체 주문 취소와 같은 이력유형)."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "update_outbound.db"

        class ClosingConnection(sqlite3.Connection):
            def __exit__(self, exc_type, exc_value, traceback):
                try:
                    return super().__exit__(exc_type, exc_value, traceback)
                finally:
                    self.close()

        self.connection_factory = ClosingConnection

        def connect_test_db():
            return sqlite3.connect(self.db_path, factory=ClosingConnection)

        self.connect_patcher_orders = patch(
            "nohtus.services.outbound_orders.connect", connect_test_db
        )
        self.connect_patcher_orders.start()
        self.connect_patcher_inventory = patch(
            "nohtus.services.inventory.connect", connect_test_db
        )
        self.connect_patcher_inventory.start()

        with sqlite3.connect(self.db_path, factory=ClosingConnection) as con:
            con.execute(
                """CREATE TABLE inventory(
                       id INTEGER PRIMARY KEY,location TEXT,company TEXT,product_name TEXT,
                       warehouse_name TEXT,lot TEXT,exp_date TEXT,qty INTEGER,updated_at TEXT
                   )"""
            )
            con.execute(
                """CREATE TABLE outbound_orders(
                       id INTEGER PRIMARY KEY AUTOINCREMENT,created_at TEXT NOT NULL,
                       order_date TEXT NOT NULL,title TEXT,status TEXT DEFAULT '저장됨',memo TEXT
                   )"""
            )
            con.execute(
                """CREATE TABLE outbound_order_items(
                       id INTEGER PRIMARY KEY AUTOINCREMENT,order_id INTEGER NOT NULL,
                       inventory_id INTEGER,location TEXT,product_name TEXT,lot TEXT,exp_date TEXT,
                       qty INTEGER NOT NULL,company TEXT,warehouse_name TEXT
                   )"""
            )
            con.execute(
                """CREATE TABLE transactions(
                       id INTEGER PRIMARY KEY AUTOINCREMENT,created_at TEXT,actor TEXT,tx_type TEXT,
                       product_name TEXT,warehouse_name TEXT,lot TEXT,exp_date TEXT,
                       from_company TEXT,from_location TEXT,to_company TEXT,to_location TEXT,
                       qty INTEGER,memo TEXT,final_stock INTEGER
                   )"""
            )
            con.execute(
                """INSERT INTO inventory(
                       id,location,company,product_name,warehouse_name,lot,exp_date,qty,updated_at
                   ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (1, "A1-01", "A사업장", "ㄱ제품", "ERP-A", "LOT-1", "2027-01-01", 10, "2026-01-01"),
            )
            con.execute(
                """INSERT INTO inventory(
                       id,location,company,product_name,warehouse_name,lot,exp_date,qty,updated_at
                   ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (2, "B1-01", "B사업장", "ㄴ제품", "ERP-B", "LOT-2", "2027-02-01", 10, "2026-01-01"),
            )

    def tearDown(self):
        self.connect_patcher_orders.stop()
        self.connect_patcher_inventory.stop()
        self.temp_dir.cleanup()

    def _transactions_for_order(self, order_id):
        with sqlite3.connect(self.db_path, factory=self.connection_factory) as con:
            rows = con.execute(
                "SELECT tx_type, qty FROM transactions WHERE memo LIKE ? ORDER BY id",
                (f"%출고지시서 #{order_id}%",),
            ).fetchall()
        return rows

    def test_replacing_a_line_logs_cancel_for_removed_and_rededuct_for_added(self):
        order_id = save_outbound_order([{"id": 1, "요청수량": 3}], title="테스트 출고")

        update_outbound_order(order_id, [{"id": 2, "요청수량": 3}])

        rows = self._transactions_for_order(order_id)
        by_type = {}
        for tx_type, qty in rows:
            if tx_type in ("출고지시취소", "출고지시 재차감"):
                by_type[tx_type] = qty

        self.assertEqual(by_type.get("출고지시취소"), 3)
        self.assertEqual(by_type.get("출고지시 재차감"), 3)

        with sqlite3.connect(self.db_path, factory=self.connection_factory) as con:
            qty_a = con.execute("SELECT qty FROM inventory WHERE id=1").fetchone()[0]
            qty_b = con.execute("SELECT qty FROM inventory WHERE id=2").fetchone()[0]
        self.assertEqual(qty_a, 10)
        self.assertEqual(qty_b, 7)

    def test_partial_quantity_decrease_still_uses_rededuct_type(self):
        order_id = save_outbound_order([{"id": 1, "요청수량": 5}], title="테스트 출고")

        update_outbound_order(order_id, [{"id": 1, "요청수량": 2}])

        rows = self._transactions_for_order(order_id)
        types = [tx_type for tx_type, _qty in rows if tx_type in ("출고지시취소", "출고지시 재차감")]
        self.assertNotIn("출고지시취소", types)
        self.assertIn("출고지시 재차감", types)


if __name__ == "__main__":
    unittest.main()
