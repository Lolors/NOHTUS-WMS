import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nohtus.services.export_waiting import (
    ensure_export_waiting_tables,
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
                       warehouse_name TEXT,lot TEXT,exp_date TEXT,qty INTEGER
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
                       export_no,country,buyer,transport_method,title,status,created_at,updated_at
                   ) VALUES(?,?,?,?,?,?,?,?)""",
                ("OLD-1", "KR", "Old Buyer", "항공", "KR-Old Buyer-항공", status, "2026-01-01", "2026-01-01"),
            )
            order_id = int(order.lastrowid)
            con.execute(
                """INSERT INTO export_waiting_items(
                       order_id,source_inventory_id,company,product_name,warehouse_name,lot,exp_date,
                       source_location,waiting_location,qty,moved_at,confirmed
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,1)""",
                (order_id, 10, "NOH", "제품", "", "LOT-1", "2027-01-01", "A1", "P", 3, "2026-01-01"),
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


if __name__ == "__main__":
    unittest.main()
