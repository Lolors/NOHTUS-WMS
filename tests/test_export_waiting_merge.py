import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nohtus.services.export_waiting import ensure_export_waiting_tables, merge_export_waiting_orders


class ExportWaitingMergeTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "merge.db"

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
        ensure_export_waiting_tables()

    def tearDown(self):
        self.connect_patcher.stop()
        self.temp_dir.cleanup()

    def _add_order(self, export_no, status="waiting"):
        with sqlite3.connect(self.db_path, factory=self.connection_factory) as con:
            cur = con.execute(
                """INSERT INTO export_waiting_orders(
                       export_no,country,buyer,transport_method,title,status,created_at,updated_at
                   ) VALUES(?,?,?,?,?,?,?,?)""",
                (export_no, "KR", "Buyer", "항공", f"KR-Buyer-{export_no}", status, "2026-01-01", "2026-01-01"),
            )
            return int(cur.lastrowid)

    def _add_item(self, order_id, source_inventory_id, qty, *, confirmed=0):
        with sqlite3.connect(self.db_path, factory=self.connection_factory) as con:
            con.execute(
                """INSERT INTO export_waiting_items(
                       order_id,source_inventory_id,company,product_name,warehouse_name,lot,exp_date,
                       source_location,waiting_location,qty,moved_at,confirmed
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    order_id,
                    source_inventory_id,
                    "NOH",
                    "제품",
                    "",
                    "LOT-1",
                    "2027-01-01",
                    "A1",
                    "P",
                    qty,
                    "2026-01-01",
                    confirmed,
                ),
            )

    def test_merge_moves_items_to_target_and_combines_duplicates(self):
        source_id = self._add_order("A")
        target_id = self._add_order("B")
        self._add_item(source_id, 10, 3)
        self._add_item(target_id, 10, 7)
        self._add_item(source_id, 11, 5)

        result = merge_export_waiting_orders(source_id, target_id)

        with sqlite3.connect(self.db_path, factory=self.connection_factory) as con:
            orders = con.execute(
                "SELECT id,export_no FROM export_waiting_orders ORDER BY id"
            ).fetchall()
            items = con.execute(
                "SELECT source_inventory_id,qty FROM export_waiting_items WHERE order_id=? ORDER BY source_inventory_id",
                (target_id,),
            ).fetchall()

        self.assertEqual(orders, [(target_id, "B")])
        self.assertEqual(items, [(10, 10), (11, 5)])
        self.assertEqual(result["merged_qty"], 8)
        self.assertEqual(result["result_qty"], 15)

    def test_merge_rejects_orders_with_confirmed_items(self):
        source_id = self._add_order("A")
        target_id = self._add_order("B")
        self._add_item(source_id, 10, 3, confirmed=1)

        with self.assertRaisesRegex(ValueError, "수출확정된 품목"):
            merge_export_waiting_orders(source_id, target_id)

        with sqlite3.connect(self.db_path, factory=self.connection_factory) as con:
            order_count = con.execute(
                "SELECT COUNT(*) FROM export_waiting_orders"
            ).fetchone()[0]
        self.assertEqual(order_count, 2)


if __name__ == "__main__":
    unittest.main()
