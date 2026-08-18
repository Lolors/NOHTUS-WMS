from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nohtus.export_app.services import wms_inventory_picker_service as picker


class WmsInventoryPickerServiceTests(unittest.TestCase):
    """실출고 입력 화면에서 주문품목에 실제 WMS 재고를 연결할 때 쓰는 조회
    함수들. nohtus/pages/move.py(이동 등록)의 캐스케이딩 쿼리와 동일한
    로직을 임시 WMS DB로 검증한다."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "wms.db"

        class ClosingConnection(sqlite3.Connection):
            def __exit__(self, exc_type, exc_value, traceback):
                try:
                    return super().__exit__(exc_type, exc_value, traceback)
                finally:
                    self.close()

        self.connection_factory = ClosingConnection

        def connect_test_db():
            return sqlite3.connect(self.db_path, factory=ClosingConnection)

        self.connect_patcher = patch("nohtus.db.connect", connect_test_db)
        self.connect_patcher.start()

        with sqlite3.connect(self.db_path, factory=ClosingConnection) as con:
            con.execute(
                """CREATE TABLE inventory(
                       id INTEGER PRIMARY KEY,location TEXT,company TEXT,product_name TEXT,
                       warehouse_name TEXT,lot TEXT,exp_date TEXT,qty INTEGER,updated_at TEXT
                   )"""
            )
            con.execute(
                """CREATE TABLE products(
                       id INTEGER PRIMARY KEY,standard_name TEXT,warehouse_name TEXT,aliases TEXT,
                       erp_nohtuspharm_name TEXT,erp_nohtus_name TEXT,erp_noh_name TEXT,bidata_name TEXT,
                       is_material INTEGER DEFAULT 0
                   )"""
            )
            con.execute(
                "INSERT INTO products(id,standard_name) VALUES(1,'제품A')"
            )
            con.execute(
                "INSERT INTO products(id,standard_name,is_material) VALUES(2,'부자재A',1)"
            )
            con.execute(
                "INSERT INTO products(id,standard_name,is_material) VALUES(3,'제품C',0)"
            )
            con.execute(
                """CREATE TABLE export_waiting_orders(
                       id INTEGER PRIMARY KEY,export_no TEXT,status TEXT
                   )"""
            )
            con.execute(
                """CREATE TABLE export_waiting_items(
                       id INTEGER PRIMARY KEY,order_id INTEGER,source_inventory_id INTEGER,
                       waiting_inventory_id INTEGER,company TEXT,source_location TEXT,
                       product_name TEXT,warehouse_name TEXT,lot TEXT,exp_date TEXT,
                       qty INTEGER,confirmed INTEGER DEFAULT 0
                   )"""
            )
            con.executemany(
                """INSERT INTO inventory(id,location,company,product_name,warehouse_name,lot,exp_date,qty,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                [
                    (1, "A1-01", "NOH", "제품A", "ERP-A", "LOT-1", "2027-01-01", 10, "2026-01-01"),
                    (2, "B1-02", "노투스팜", "제품A", "ERP-A", "LOT-1", "2027-01-01", 5, "2026-01-01"),
                    (3, "A1-02", "NOH", "제품A", "ERP-A", "LOT-2", "2027-06-01", 20, "2026-01-01"),
                    (4, "A1-03", "NOH", "제품A", "ERP-A", "LOT-1", "2027-01-01", 0, "2026-01-01"),
                    (5, "A1-04", "NOH", "부자재A", "ERP-M", "MAT-1", "2027-01-01", 30, "2026-01-01"),
                    (6, "P", "NOH", "제품C", "ERP-C", "LOT-C", "2028-01-01", 2, "2026-01-01"),
                ],
            )
            con.execute(
                "INSERT INTO export_waiting_orders(id,export_no,status) VALUES(1,'EXP-1','waiting')"
            )
            con.execute(
                """INSERT INTO export_waiting_items(
                       id,order_id,source_inventory_id,waiting_inventory_id,company,source_location,
                       product_name,warehouse_name,lot,exp_date,qty,confirmed
                   ) VALUES(1,1,99,6,'NOH','REC','제품C','ERP-C','LOT-C','2028-01-01',2,0)"""
            )

    def tearDown(self):
        self.connect_patcher.stop()
        self.temp_dir.cleanup()

    def test_search_products_matches_standard_name(self):
        df = picker.search_products("제품A")
        self.assertEqual(list(df["standard_name"]), ["제품A"])

    def test_search_products_excludes_materials(self):
        df = picker.search_products("부자재A")
        self.assertTrue(df.empty)

    def test_product_stock_rows_excludes_materials(self):
        rows = picker.product_stock_rows("부자재A")
        self.assertTrue(rows.empty)

    def test_reserved_product_stock_rows_only_returns_current_export_p_stock(self):
        rows = picker.reserved_product_stock_rows("제품C", "EXP-1")
        self.assertEqual(len(rows), 1)
        self.assertEqual(int(rows.iloc[0]["id"]), 99)
        self.assertEqual(rows.iloc[0]["location"], "REC")
        self.assertEqual(int(rows.iloc[0]["qty"]), 2)
        self.assertTrue(picker.reserved_product_stock_rows("제품C", "EXP-OTHER").empty)

    def test_expiry_options_lists_distinct_dates_with_stock_only(self):
        options = picker.expiry_options("제품A")
        self.assertEqual(options, ["2027-01-01", "2027-06-01"])

    def test_lot_options_scoped_to_expiry_date(self):
        options = picker.lot_options("제품A", "2027-01-01")
        self.assertEqual(options, ["LOT-1"])

    def test_resolve_stock_rows_returns_all_company_location_rows(self):
        rows = picker.resolve_stock_rows("제품A", "LOT-1", "2027-01-01")
        self.assertEqual(len(rows), 2)
        companies = sorted(rows["company"].tolist())
        self.assertEqual(companies, ["NOH", "노투스팜"])

    def test_resolve_stock_rows_excludes_zero_qty(self):
        rows = picker.resolve_stock_rows("제품A", "LOT-1", "2027-01-01")
        self.assertNotIn(4, rows["id"].tolist())


if __name__ == "__main__":
    unittest.main()
