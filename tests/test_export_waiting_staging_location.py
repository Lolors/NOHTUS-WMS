import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nohtus.services.export_waiting import (
    ensure_export_waiting_tables,
    save_export_waiting_order,
    cancel_export_waiting_order,
    confirm_export_waiting_items,
)


class ExportWaitingStagingLocationTests(unittest.TestCase):
    """수출대기 재고는 기본적으로 P에 쌓이지만, P가 가득 찼거나 별도 보관이
    필요하면 T1~T5 중 아무 위치나 골라서 대신 쌓을 수 있어야 한다."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "staging.db"

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
            con.execute(
                """INSERT INTO inventory(
                       id,location,company,product_name,warehouse_name,lot,exp_date,qty,updated_at,is_shippable
                   ) VALUES(1,'A1','NOH','제품','ERP-A','LOT-1','2027-01-01',10,'2026-01-01',1)"""
            )
        ensure_export_waiting_tables()

    def tearDown(self):
        self.connect_patcher.stop()
        self.temp_dir.cleanup()

    def _cart(self, qty=4):
        return [{
            "id": 1, "사업장": "NOH", "제품명": "제품", "warehouse_name": "ERP-A",
            "LOT": "LOT-1", "유통기한": "2027-01-01", "로케이션": "A1", "요청수량": qty,
        }]

    def test_new_order_stages_stock_at_chosen_t_location_instead_of_p(self):
        result = save_export_waiting_order(
            self._cart(), country="KR", export_no="EXP-1", staging_location="T3",
        )

        with sqlite3.connect(self.db_path, factory=self.connection_factory) as con:
            item = con.execute(
                "SELECT source_location,waiting_location,qty FROM export_waiting_items WHERE order_id=?",
                (result["order_id"],),
            ).fetchone()
            source_qty = con.execute("SELECT qty FROM inventory WHERE id=1").fetchone()[0]
            t3_qty = con.execute("SELECT COALESCE(SUM(qty),0) FROM inventory WHERE location='T3'").fetchone()[0]
            p_qty = con.execute("SELECT COALESCE(SUM(qty),0) FROM inventory WHERE location='P'").fetchone()[0]

        self.assertEqual(item, ("A1", "T3", 4))
        self.assertEqual(source_qty, 6)
        self.assertEqual(t3_qty, 4)
        self.assertEqual(p_qty, 0)

    def test_rejects_unknown_staging_location(self):
        with self.assertRaisesRegex(ValueError, "P, T1~T5"):
            save_export_waiting_order(
                self._cart(), country="KR", export_no="EXP-1", staging_location="Z9",
            )

    def test_cancel_restores_stock_from_t_location_back_to_source(self):
        result = save_export_waiting_order(
            self._cart(), country="KR", export_no="EXP-1", staging_location="T4",
        )

        cancel_export_waiting_order(result["order_id"])

        with sqlite3.connect(self.db_path, factory=self.connection_factory) as con:
            source_qty = con.execute("SELECT qty FROM inventory WHERE id=1").fetchone()[0]
            t4_qty = con.execute("SELECT COALESCE(SUM(qty),0) FROM inventory WHERE location='T4'").fetchone()[0]
            status = con.execute(
                "SELECT status FROM export_waiting_orders WHERE id=?", (result["order_id"],)
            ).fetchone()[0]

        self.assertEqual(source_qty, 10)
        self.assertEqual(t4_qty, 0)
        self.assertEqual(status, "cancelled")

    def test_confirm_consumes_stock_from_its_own_t_location_not_p(self):
        result = save_export_waiting_order(
            self._cart(), country="KR", export_no="EXP-1", staging_location="T5",
        )
        with sqlite3.connect(self.db_path, factory=self.connection_factory) as con:
            item_id = con.execute(
                "SELECT id FROM export_waiting_items WHERE order_id=?", (result["order_id"],)
            ).fetchone()[0]

        confirm_export_waiting_items(
            result["order_id"], [item_id],
            erp_company="NOH", customer_code="C1", customer_name="수출처",
            shipment_date="2026-03-01",
        )

        with sqlite3.connect(self.db_path, factory=self.connection_factory) as con:
            t5_qty = con.execute("SELECT COALESCE(SUM(qty),0) FROM inventory WHERE location='T5'").fetchone()[0]
            confirmed = con.execute(
                "SELECT confirmed FROM export_waiting_items WHERE id=?", (item_id,)
            ).fetchone()[0]

        self.assertEqual(t5_qty, 0)
        self.assertEqual(confirmed, 1)

    def test_unrelated_resave_does_not_relocate_existing_staged_item(self):
        """T3에 이미 쌓아둔 재고가 있는 주문을, 다른 이유로 (기본 P인 채로)
        다시 저장해도 기존 품목은 T3에 그대로 남아야 한다 — target_location은
        새로 담기는 품목에만 적용된다."""
        with sqlite3.connect(self.db_path, factory=self.connection_factory) as con:
            con.execute(
                """INSERT INTO inventory(
                       id,location,company,product_name,warehouse_name,lot,exp_date,qty,updated_at,is_shippable
                   ) VALUES(2,'B1','NOH','제품B','ERP-B','LOT-2','2028-01-01',10,'2026-01-01',1)"""
            )
        result = save_export_waiting_order(
            self._cart(qty=4), country="KR", export_no="EXP-1", staging_location="T3",
        )

        save_export_waiting_order(
            [
                self._cart(qty=4)[0],
                {
                    "id": 2, "사업장": "NOH", "제품명": "제품B", "warehouse_name": "ERP-B",
                    "LOT": "LOT-2", "유통기한": "2028-01-01", "로케이션": "B1", "요청수량": 3,
                },
            ],
            country="KR", export_no="EXP-1", editing_order_id=result["order_id"],
        )

        with sqlite3.connect(self.db_path, factory=self.connection_factory) as con:
            locations = dict(con.execute(
                "SELECT source_inventory_id,waiting_location FROM export_waiting_items WHERE order_id=?",
                (result["order_id"],),
            ).fetchall())
            t3_qty = con.execute("SELECT COALESCE(SUM(qty),0) FROM inventory WHERE location='T3'").fetchone()[0]
            p_qty = con.execute("SELECT COALESCE(SUM(qty),0) FROM inventory WHERE location='P'").fetchone()[0]

        self.assertEqual(locations, {1: "T3", 2: "P"})
        self.assertEqual(t3_qty, 4)
        self.assertEqual(p_qty, 3)

    def test_default_staging_location_is_still_p(self):
        result = save_export_waiting_order(self._cart(), country="KR", export_no="EXP-1")

        with sqlite3.connect(self.db_path, factory=self.connection_factory) as con:
            waiting_location = con.execute(
                "SELECT waiting_location FROM export_waiting_items WHERE order_id=?",
                (result["order_id"],),
            ).fetchone()[0]
            p_qty = con.execute("SELECT COALESCE(SUM(qty),0) FROM inventory WHERE location='P'").fetchone()[0]

        self.assertEqual(waiting_location, "P")
        self.assertEqual(p_qty, 4)


if __name__ == "__main__":
    unittest.main()
