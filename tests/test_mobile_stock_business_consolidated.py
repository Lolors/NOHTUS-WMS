"""mobile_stock 5파일 몽키패치 체인(mobile_stock.py <- live_fix <- v1 <- v2 <- v3
<- business.py)을 mobile_stock.py(순수 데이터) + mobile_stock_business.py
(렌더링) 2개 파일로 통합한 뒤의 순수 로직을 고정하는 테스트. Streamlit 위젯
트리라 전체 페이지를 골든 텍스트로 비교할 순 없어서, 함수 호출로 검증
가능한 부분(필터링/배지 로직)만 다룬다. 실제 렌더링은 이 세션에서
page_mobile_stock_finder()/각 탭 함수를 직접 호출해 예외 없이 도는지
수동으로 확인했다(P존 재고 포함)."""

import sqlite3
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import nohtus.db as db
from nohtus.pages import mobile_stock_business as mb


def _make_db(path):
    con = sqlite3.connect(path)
    try:
        con.executescript(
            """
            CREATE TABLE inventory(
                id INTEGER PRIMARY KEY, company TEXT, product_name TEXT,
                warehouse_name TEXT, lot TEXT, exp_date TEXT, location TEXT, qty INTEGER
            );
            CREATE TABLE products(
                id INTEGER PRIMARY KEY, standard_name TEXT, aliases TEXT, image_path TEXT,
                is_material INTEGER DEFAULT 0
            );
            """
        )
        con.commit()
    finally:
        con.close()


class MobileStockBusinessLogicTests(unittest.TestCase):
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

    def _seed_inventory(self, rows):
        con = sqlite3.connect(self.db_path)
        try:
            con.executemany(
                "INSERT INTO inventory(company, product_name, warehouse_name, lot, exp_date, location, qty) "
                "VALUES(?,?,?,?,?,?,?)",
                rows,
            )
            con.commit()
        finally:
            con.close()

    def _seed_products(self, rows):
        con = sqlite3.connect(self.db_path)
        try:
            con.executemany(
                "INSERT INTO products(standard_name, aliases, image_path, is_material) VALUES(?,?,?,?)",
                rows,
            )
            con.commit()
        finally:
            con.close()

    def test_export_waiting_stock_detected_for_p_zone_location(self):
        rows = pd.DataFrame({"location": ["A1-01-01", "P-1"]})
        self.assertTrue(mb._has_export_waiting_stock(rows))

    def test_export_waiting_stock_false_when_no_p_zone_rows(self):
        rows = pd.DataFrame({"location": ["A1-01-01", "B2-03-01"]})
        self.assertFalse(mb._has_export_waiting_stock(rows))

    def test_expiry_badge_empty_when_no_expiry_column(self):
        rows = pd.DataFrame({"qty": [1, 2]})
        self.assertEqual(mb._expiry_badge(rows), "")

    def test_expiry_badge_present_when_expiry_column_has_near_date(self):
        near = pd.Timestamp(date.today() + timedelta(days=10))
        rows = pd.DataFrame({"_expiry": [near]})
        badge_html = mb._expiry_badge(rows)
        self.assertIn("mobile-expiry-badge", badge_html)

    def test_stock_rows_excludes_material_location(self):
        self._seed_inventory([
            ("노투스", "제품A", "ERP-A", "LOT-1", "2027-01-01", "A1-01-01", 10),
            ("노투스", "제품A", "ERP-A", "LOT-2", "2027-01-01", "G1-01", 5),
        ])
        rows = mb._stock_rows("제품A")
        self.assertEqual(sorted(rows["location"].tolist()), ["A1-01-01"])

    def test_has_visible_stock_false_when_only_material_location(self):
        self._seed_inventory([
            ("노투스", "제품B", "ERP-B", "LOT-1", "2027-01-01", "G1-01", 5),
        ])
        self.assertFalse(mb._has_visible_stock("제품B"))

    def test_filtered_expiry_df_excludes_bidata_when_checked(self):
        self._seed_inventory([
            ("비자료", "제품C", "ERP-C", "LOT-1", "2026-10-01", "A1-01-01", 5),
            ("노투스", "제품C", "ERP-C", "LOT-2", "2026-10-01", "A1-01-02", 5),
        ])
        df = mb._filtered_expiry_df("1년 이내", exclude_bidata=True)
        self.assertEqual(sorted(df["company"].unique().tolist()), ["노투스"])

    def test_filtered_expiry_df_keeps_bidata_when_unchecked(self):
        self._seed_inventory([
            ("비자료", "제품D", "ERP-D", "LOT-1", "2026-10-01", "A1-01-01", 5),
        ])
        df = mb._filtered_expiry_df("1년 이내", exclude_bidata=False)
        self.assertEqual(df["company"].tolist(), ["비자료"])

    def test_product_candidates_prunes_material_only_matches(self):
        self._seed_products([
            ("제품E", "", "", 0),
            ("제품F", "", "", 0),
        ])
        self._seed_inventory([
            ("노투스", "제품E", "ERP-E", "LOT-1", "2027-01-01", "A1-01-01", 10),
            ("노투스", "제품F", "ERP-F", "LOT-1", "2027-01-01", "G1-01", 10),
        ])
        candidates = mb._product_candidates("제품", limit=10)
        self.assertIn("제품E", candidates)
        self.assertNotIn("제품F", candidates)


if __name__ == "__main__":
    unittest.main()
