import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nohtus.services.outbound_orders import save_outbound_order


class SaveOutboundOrderDateTests(unittest.TestCase):
    """save_outbound_order()에 order_date 파라미터를 추가하면서(2026-08-10,
    outbound_date_fix.py의 저장 후 UPDATE 방식을 INSERT 시점 지정으로 통합)
    기존 기본 동작(오늘 날짜)과 새 동작(지정한 날짜) 모두 깨지지 않는지 확인한다."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "save_outbound.db"

        class ClosingConnection(sqlite3.Connection):
            def __exit__(self, exc_type, exc_value, traceback):
                try:
                    return super().__exit__(exc_type, exc_value, traceback)
                finally:
                    self.close()

        self.connection_factory = ClosingConnection

        def connect_test_db():
            return sqlite3.connect(self.db_path, factory=ClosingConnection)

        self.connect_patcher = patch(
            "nohtus.services.outbound_orders.connect", connect_test_db
        )
        self.connect_patcher.start()

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
                (1, "A1-01", "NOH", "제품", "ERP-A", "LOT-1", "2027-01-01", 10, "2026-01-01"),
            )

    def tearDown(self):
        self.connect_patcher.stop()
        self.temp_dir.cleanup()

    def _order_date_of(self, order_id):
        with sqlite3.connect(self.db_path, factory=self.connection_factory) as con:
            row = con.execute(
                "SELECT order_date FROM outbound_orders WHERE id=?", (order_id,)
            ).fetchone()
        return row[0]

    def test_defaults_to_today_when_order_date_not_given(self):
        from datetime import date

        order_id = save_outbound_order(
            [{"id": 1, "요청수량": 2}], title="테스트 출고"
        )
        self.assertEqual(self._order_date_of(order_id), date.today().strftime("%Y-%m-%d"))

    def test_uses_explicit_order_date_when_given(self):
        order_id = save_outbound_order(
            [{"id": 1, "요청수량": 3}], title="테스트 출고", order_date="2026-03-15"
        )
        self.assertEqual(self._order_date_of(order_id), "2026-03-15")


if __name__ == "__main__":
    unittest.main()
