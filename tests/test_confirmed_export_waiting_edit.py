import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nohtus.services.export_waiting import (
    ensure_export_waiting_tables,
    save_export_waiting_order,
    update_confirmed_export_waiting_metadata,
)


class ConfirmedExportWaitingEditTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "confirmed-edit.db"

        class ClosingConnection(sqlite3.Connection):
            def __exit__(self, exc_type, exc_value, traceback):
                try:
                    return super().__exit__(exc_type, exc_value, traceback)
                finally:
                    self.close()

        self.connection_factory = ClosingConnection

        def connect_test_db():
            return sqlite3.connect(self.db_path, factory=ClosingConnection)

        self.connect_patcher = patch("nohtus.services.export_waiting.connect", connect_test_db)
        self.connect_patcher.start()
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
        self.connect_patcher.stop()
        self.temp_dir.cleanup()

    def _add_order(self, status="confirmed"):
        with sqlite3.connect(self.db_path, factory=self.connection_factory) as con:
            order = con.execute(
                """INSERT INTO export_waiting_orders(
                       export_no,country,buyer,transport_method,title,status,erp_company,
                       erp_customer_code,erp_customer_name,order_date,created_at,updated_at
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    "OLD-1", "KR", "Old Buyer", "항공", "KR-Old Buyer-항공", status,
                    "ERP-NOH", "C001", "수출매출처", "2026-01-15", "2026-01-01", "2026-01-01",
                ),
            )
            order_id = int(order.lastrowid)
            con.executemany(
                """INSERT INTO inventory(
                       id,location,company,product_name,warehouse_name,lot,exp_date,qty,updated_at,is_shippable
                   ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                [
                    (10, "A1", "NOH", "제품", "ERP-A", "LOT-1", "2027-01-01", 0, "2026-01-01", 1),
                    (11, "B1", "NOH", "새제품", "ERP-B", "LOT-2", "2028-02-02", 5, "2026-01-01", 1),
                ],
            )
            con.execute(
                """INSERT INTO export_waiting_items(
                       order_id,source_inventory_id,company,product_name,warehouse_name,lot,exp_date,
                       source_location,waiting_location,qty,moved_at,confirmed
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,1)""",
                (order_id, 10, "NOH", "제품", "ERP-A", "LOT-1", "2027-01-01", "A1", "P", 3, "2026-01-01"),
            )
        return order_id

    def test_updates_confirmed_order_metadata_without_changing_items(self):
        order_id = self._add_order()

        title = update_confirmed_export_waiting_metadata(
            order_id,
            country="JP",
            buyer="New Buyer",
            transport_method="해상",
            export_no="NEW-9",
        )

        with sqlite3.connect(self.db_path, factory=self.connection_factory) as con:
            order = con.execute(
                "SELECT country,buyer,transport_method,export_no,title,status FROM export_waiting_orders WHERE id=?",
                (order_id,),
            ).fetchone()
            item = con.execute(
                "SELECT source_inventory_id,qty,confirmed FROM export_waiting_items WHERE order_id=?",
                (order_id,),
            ).fetchone()

        self.assertEqual(title, "JP-New Buyer-해상")
        self.assertEqual(order, ("JP", "New Buyer", "해상", "NEW-9", title, "confirmed"))
        self.assertEqual(item, (10, 3, 1))

    def test_rejects_non_confirmed_order(self):
        order_id = self._add_order(status="waiting")

        with self.assertRaisesRegex(ValueError, "수출확정된 건만"):
            update_confirmed_export_waiting_metadata(
                order_id,
                country="JP",
                buyer="Buyer",
                transport_method="항공",
                export_no="NEW-1",
            )

    def test_validates_required_metadata(self):
        order_id = self._add_order()

        with self.assertRaisesRegex(ValueError, "국가를 입력"):
            update_confirmed_export_waiting_metadata(
                order_id,
                country="",
                buyer="Buyer",
                transport_method="항공",
                export_no="NEW-1",
            )

    def test_replaces_confirmed_items_and_rebalances_inventory(self):
        order_id = self._add_order()

        result = save_export_waiting_order(
            [
                {
                    "id": 10, "사업장": "NOH", "제품명": "제품", "warehouse_name": "ERP-A",
                    "LOT": "LOT-1", "유통기한": "2027-01-01", "로케이션": "A1", "요청수량": 1,
                },
                {
                    "id": 11, "사업장": "NOH", "제품명": "새제품", "warehouse_name": "ERP-B",
                    "LOT": "LOT-2", "유통기한": "2028-02-02", "로케이션": "B1", "요청수량": 2,
                },
            ],
            country="JP",
            buyer="New Buyer",
            transport_method="해상",
            export_no="NEW-9",
            editing_order_id=order_id,
        )

        with sqlite3.connect(self.db_path, factory=self.connection_factory) as con:
            order = con.execute(
                """SELECT status,country,buyer,transport_method,export_no,erp_company,
                          erp_customer_code,erp_customer_name,order_date
                   FROM export_waiting_orders WHERE id=?""",
                (order_id,),
            ).fetchone()
            items = con.execute(
                """SELECT source_inventory_id,product_name,qty,confirmed,confirmed_company,
                          confirmed_customer_code,confirmed_customer_name
                   FROM export_waiting_items WHERE order_id=? ORDER BY source_inventory_id""",
                (order_id,),
            ).fetchall()
            stocks = con.execute(
                "SELECT id,qty FROM inventory WHERE id IN (10,11) ORDER BY id"
            ).fetchall()
            p_stock = con.execute(
                "SELECT COALESCE(SUM(qty),0) FROM inventory WHERE location='P'"
            ).fetchone()[0]
            history = con.execute(
                "SELECT tx_type,product_name,qty,final_stock FROM transactions ORDER BY id"
            ).fetchall()

        self.assertEqual(result["total_qty"], 3)
        self.assertEqual(
            order,
            ("confirmed", "JP", "New Buyer", "해상", "NEW-9", "ERP-NOH", "C001", "수출매출처", "2026-01-15"),
        )
        self.assertEqual(
            items,
            [
                (10, "제품", 1, 1, "ERP-NOH", "C001", "수출매출처"),
                (11, "새제품", 2, 1, "ERP-NOH", "C001", "수출매출처"),
            ],
        )
        self.assertEqual(stocks, [(10, 2), (11, 3)])
        self.assertEqual(p_stock, 0)
        self.assertEqual(
            history,
            [
                ("출고지시취소", "제품", 3, 3),
                ("출고", "제품", 1, 2),
                ("출고", "새제품", 2, 3),
            ],
        )

    def test_rolls_back_confirmed_edit_when_new_quantity_is_too_large(self):
        order_id = self._add_order()

        with self.assertRaisesRegex(ValueError, "재고 부족"):
            save_export_waiting_order(
                [
                    {
                        "id": 10, "사업장": "NOH", "제품명": "제품", "warehouse_name": "ERP-A",
                        "LOT": "LOT-1", "유통기한": "2027-01-01", "로케이션": "A1", "요청수량": 4,
                    }
                ],
                country="JP",
                buyer="Buyer",
                transport_method="항공",
                export_no="NEW-1",
                editing_order_id=order_id,
            )

        with sqlite3.connect(self.db_path, factory=self.connection_factory) as con:
            item = con.execute(
                "SELECT source_inventory_id,qty,confirmed FROM export_waiting_items WHERE order_id=?",
                (order_id,),
            ).fetchone()
            source_qty = con.execute("SELECT qty FROM inventory WHERE id=10").fetchone()[0]
            history_count = con.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
            export_no = con.execute(
                "SELECT export_no FROM export_waiting_orders WHERE id=?", (order_id,)
            ).fetchone()[0]

        self.assertEqual(item, (10, 3, 1))
        self.assertEqual(source_qty, 0)
        self.assertEqual(history_count, 0)
        self.assertEqual(export_no, "OLD-1")


if __name__ == "__main__":
    unittest.main()
