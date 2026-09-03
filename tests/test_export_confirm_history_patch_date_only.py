import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nohtus.services.export_confirm_history_patch import (
    _patched_update_confirmed_export_waiting_items,
)
from nohtus.services.export_waiting import ensure_export_waiting_tables


class ExportConfirmHistoryPatchDateOnlyTests(unittest.TestCase):
    """실사용 요청: 확정 출고내역 수정에서 출고일자만 바뀐 경우는 실제로
    아무 재고 이동도 없는데 "출고지시취소" 이력이 남아 혼란을 줬다.
    ERP 사업장/코드/매출처가 그대로면 출고일자만 바뀌어도 이력을 남기지
    않아야 한다."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "confirm-history.db"

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
            "nohtus.services.export_waiting.connect", connect_test_db
        )
        self.connect_patcher.start()
        self.patch_connect_patcher = patch(
            "nohtus.services.export_confirm_history_patch.connect", connect_test_db
        )
        self.patch_connect_patcher.start()
        with sqlite3.connect(self.db_path, factory=ClosingConnection) as con:
            con.execute(
                """CREATE TABLE inventory(
                       id INTEGER PRIMARY KEY,location TEXT,company TEXT,product_name TEXT,
                       warehouse_name TEXT,lot TEXT,exp_date TEXT,qty INTEGER,
                       updated_at TEXT,is_shippable INTEGER
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
        ensure_export_waiting_tables()

    def tearDown(self):
        self.patch_connect_patcher.stop()
        self.connect_patcher.stop()
        self.temp_dir.cleanup()

    def _add_confirmed_order(self):
        with sqlite3.connect(self.db_path, factory=self.connection_factory) as con:
            order = con.execute(
                """INSERT INTO export_waiting_orders(
                       export_no,country,buyer,transport_method,title,status,erp_company,
                       erp_customer_code,erp_customer_name,order_date,created_at,updated_at
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    "OLD-1", "KR", "Old Buyer", "항공", "KR-Old Buyer-항공", "confirmed",
                    "ERP-NOH", "C001", "수출매출처", "2026-01-15", "2026-01-01", "2026-01-01",
                ),
            )
            order_id = int(order.lastrowid)
            con.execute(
                """INSERT INTO inventory(
                       id,location,company,product_name,warehouse_name,lot,exp_date,qty,updated_at,is_shippable
                   ) VALUES(10,'A1','NOH','제품','ERP-A','LOT-1','2027-01-01',0,'2026-01-01',1)"""
            )
            con.execute(
                """INSERT INTO export_waiting_items(
                       order_id,source_inventory_id,company,product_name,warehouse_name,lot,exp_date,
                       source_location,waiting_location,qty,moved_at,confirmed,confirmed_company,
                       confirmed_customer_code,confirmed_customer_name,confirmed_at
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,1,?,?,?,?)""",
                (
                    order_id, 10, "NOH", "제품", "ERP-A", "LOT-1", "2027-01-01",
                    "A1", "P", 3, "2026-01-01", "ERP-NOH", "C001", "수출매출처",
                    "2026-01-15 09:00:00",
                ),
            )
        return order_id

    def test_date_only_change_writes_no_history(self):
        order_id = self._add_confirmed_order()

        result = _patched_update_confirmed_export_waiting_items(
            order_id,
            [1],
            erp_company="ERP-NOH",
            customer_code="C001",
            customer_name="수출매출처",
            shipment_date="2026-02-20",
        )

        with sqlite3.connect(self.db_path, factory=self.connection_factory) as con:
            tx_count = con.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
            confirmed_at = con.execute(
                "SELECT confirmed_at FROM export_waiting_items WHERE id=1"
            ).fetchone()[0]

        self.assertEqual(result["order_date"], "2026-02-20")
        self.assertTrue(confirmed_at.startswith("2026-02-20 "))
        self.assertEqual(tx_count, 0)

    def test_customer_change_still_writes_cancel_and_reregister_history(self):
        order_id = self._add_confirmed_order()

        _patched_update_confirmed_export_waiting_items(
            order_id,
            [1],
            erp_company="ERP-NOH",
            customer_code="C002",
            customer_name="새 수출처",
            shipment_date="2026-01-15",
        )

        with sqlite3.connect(self.db_path, factory=self.connection_factory) as con:
            tx_types = [
                row[0]
                for row in con.execute(
                    "SELECT tx_type FROM transactions ORDER BY id"
                ).fetchall()
            ]

        self.assertEqual(tx_types, ["출고지시취소", "출고지시"])


if __name__ == "__main__":
    unittest.main()
