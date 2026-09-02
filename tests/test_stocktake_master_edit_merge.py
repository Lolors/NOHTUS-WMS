import sqlite3
import tempfile
import unittest
from pathlib import Path

import pandas as pd

import nohtus.pages.stocktake as stocktake_page
import nohtus.pages.stocktake_business as stocktake_business


def _create_tables(con):
    con.executescript(
        """
        CREATE TABLE inventory(
            id INTEGER PRIMARY KEY, company TEXT, product_name TEXT,
            warehouse_name TEXT, lot TEXT, exp_date TEXT, location TEXT,
            qty INTEGER, updated_at TEXT
        );
        CREATE TABLE products(
            id INTEGER PRIMARY KEY, product_code TEXT, standard_name TEXT,
            warehouse_name TEXT, aliases TEXT, erp_nohtuspharm_name TEXT,
            erp_nohtus_name TEXT, erp_noh_name TEXT, erp_noh_code TEXT,
            bidata_name TEXT, image_path TEXT
        );
        CREATE TABLE export_waiting_items(
            id INTEGER PRIMARY KEY, order_id INTEGER, source_inventory_id INTEGER,
            company TEXT, product_name TEXT, warehouse_name TEXT, lot TEXT,
            exp_date TEXT, source_location TEXT, waiting_location TEXT,
            qty INTEGER, moved_at TEXT, confirmed INTEGER DEFAULT 0,
            confirmed_company TEXT, confirmed_customer_code TEXT,
            confirmed_customer_name TEXT, confirmed_at TEXT, waiting_inventory_id INTEGER
        );
        """
    )


_MAPPING_DF = pd.DataFrame([{
    "id": None, "노투스팜 ERP명": "", "노투스팜 ERP 제품코드": "", "NOH ERP명": "",
    "NOH ERP 제품코드": "", "노투스 ERP명": "", "비자료명": "", "별칭": "",
}])


class StocktakeMasterEditMergeTests(unittest.TestCase):
    """실제 '제품마스터 수정' 다이얼로그는 6개 값으로 언패킹한다
    (saved_product, saved_lot, saved_exp, mapping_count, propagation_error, merged).
    stocktake_business의 패치 버전이 그보다 적게/많이 반환하면 저장할 때마다
    ValueError로 깨진다 — 실제로 이 불일치 때문에 매 저장이 실패했었다."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self._tmpdir.name) / "test.db"
        with sqlite3.connect(self.db_path) as con:
            _create_tables(con)
        self._orig_connect = stocktake_business.connect
        self._orig_propagate = stocktake_page._propagate_master_edit_to_shipment_items
        stocktake_business.connect = lambda: sqlite3.connect(self.db_path)
        stocktake_page._propagate_master_edit_to_shipment_items = lambda *a, **k: ""

    def tearDown(self):
        stocktake_business.connect = self._orig_connect
        stocktake_page._propagate_master_edit_to_shipment_items = self._orig_propagate
        self._tmpdir.cleanup()

    def _seed(self, rows):
        with sqlite3.connect(self.db_path) as con:
            con.executemany(
                "INSERT INTO inventory VALUES(?,?,?,?,?,?,?,?,?)", rows
            )

    def _inventory_rows(self):
        with sqlite3.connect(self.db_path) as con:
            return con.execute("SELECT id, lot, qty FROM inventory ORDER BY id").fetchall()

    def test_merges_into_existing_matching_row_and_returns_expected_arity(self):
        self._seed([
            (1, "노투스팜", "제품A", "제품A", "LOTA", "2028-01-01", "A1-01-01", 10, "2026-08-31"),
            (2, "노투스팜", "제품A", "제품A", "LOTB", "2028-01-01", "A1-01-01", 5, "2026-08-31"),
        ])

        saved_product, saved_lot, saved_exp, mapping_count, propagation_error, merged = (
            stocktake_business._update_inventory_and_product_mappings_business(
                2, "제품A", "LOTA", "2028-01-01", _MAPPING_DF
            )
        )

        self.assertEqual(saved_product, "제품A")
        self.assertEqual(saved_lot, "LOTA")
        self.assertEqual(mapping_count, 1)
        self.assertEqual(propagation_error, "")
        self.assertTrue(merged)
        self.assertEqual(self._inventory_rows(), [(2, "LOTA", 15)])

    def test_no_merge_when_no_existing_duplicate(self):
        self._seed([
            (1, "노투스팜", "제품A", "제품A", "LOTB", "2028-01-01", "A1-01-01", 5, "2026-08-31"),
        ])

        _, saved_lot, _, _, _, merged = stocktake_business._update_inventory_and_product_mappings_business(
            1, "제품A", "LOTA", "2028-01-01", _MAPPING_DF
        )

        self.assertEqual(saved_lot, "LOTA")
        self.assertFalse(merged)
        self.assertEqual(self._inventory_rows(), [(1, "LOTA", 5)])

    def test_lot_edit_propagates_to_waiting_item_staged_at_t_location_without_direct_link(self):
        """수출대기 보관 위치가 P뿐 아니라 T1~T5까지 확장된 뒤에도, 고유 ID
        연결이 없는(과거 엑셀 등으로 들어온) 수출대기 행은 실제 재고키가
        일치하는 P 위치만 찾아 연결했다. T4에 있는 품목의 LOT/유통기한을
        나중에 채워도 수출대기 쪽에 반영되지 않던 사고를 재현한다.

        같은 재고키의 T4 행이 2개라 ensure_export_waiting_tables()의 자동
        고유ID 복구(정확히 1행일 때만 복구)가 스스로는 못 붙잡는 경우를
        일부러 만들어서, _linked_waiting_items의 위치 폴백 자체가 T4를
        찾아내는지만 검증한다."""
        self._seed([
            (1, "노투스팜", "제품A", "제품A", "-", "-", "T4", 5, "2026-08-31"),
            (2, "노투스팜", "제품A", "제품A", "-", "-", "T4", 3, "2026-08-31"),
        ])
        with sqlite3.connect(self.db_path) as con:
            con.execute(
                """INSERT INTO export_waiting_items(
                       id, order_id, source_inventory_id, company, product_name,
                       warehouse_name, lot, exp_date, source_location, waiting_location,
                       qty, moved_at, confirmed, waiting_inventory_id
                   ) VALUES(1, 1, NULL, '노투스팜', '제품A', '제품A', '-', '-', 'REC', 'T4', 5, '2026-08-31', 0, NULL)"""
            )
            con.commit()

        stocktake_business._update_inventory_and_product_mappings_business(
            1, "제품A", "LOT-NEW", "2028-05-01", _MAPPING_DF
        )

        with sqlite3.connect(self.db_path) as con:
            waiting = con.execute(
                "SELECT lot, exp_date FROM export_waiting_items WHERE id=1"
            ).fetchone()
        self.assertEqual(waiting[0], "LOT-NEW")
        self.assertEqual(waiting[1], "2028-05-01")


if __name__ == "__main__":
    unittest.main()
