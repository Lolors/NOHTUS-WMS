import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import nohtus.pages.material_management as materials
import nohtus.pages.outbound as outbound
import nohtus.pages.product_matching_business as product_matching
import nohtus.pages.stocktake as stocktake
from nohtus.services import products


class MaterialManagementTests(unittest.TestCase):
    def test_material_inventory_summary_blanks_erp_name_for_non_data_company(self):
        captured = {}

        def fake_q(sql, params=()):
            captured["sql"] = sql
            return pd.DataFrame()

        with patch.object(materials, "q", fake_q):
            materials.material_inventory_summary()
        self.assertIn("WHEN TRIM(COALESCE(i.company,''))='비자료' THEN ''", captured["sql"])

    def test_registered_material_editor_deletion_unflags_standard_product(self):
        con = sqlite3.connect(":memory:")
        con.execute("CREATE TABLE products(standard_name TEXT, is_material INTEGER, material_type TEXT)")
        con.executemany("INSERT INTO products VALUES('트레이',1,'트레이')", [(), ()])
        original = pd.DataFrame([
            {"_row_key": "0", "material_type": "트레이", "standard_name": "트레이", "company": "NOH", "erp_name": "ERP", "qty": 2},
            {"_row_key": "1", "material_type": "트레이", "standard_name": "트레이", "company": "비자료", "erp_name": "", "qty": 3},
        ])
        edited = original.loc[original["_row_key"] != "0"].copy()

        class ContextConnection:
            def __enter__(self): return con
            def __exit__(self, *args): return False

        with patch.object(materials, "connect", return_value=ContextConnection()):
            deleted, _updated = materials.update_registered_materials(original, edited)
        self.assertEqual(1, deleted)
        self.assertEqual([(0, None), (0, None)], con.execute("SELECT is_material, material_type FROM products").fetchall())
        con.close()

    def test_registered_material_editor_uses_native_header_sorting(self):
        source = Path(materials.__file__).read_text(encoding="utf-8")
        self.assertNotIn('"정렬 기준"', source)
        self.assertNotIn('["오름차순", "내림차순"]', source)
        self.assertIn('num_rows="fixed"', source)
        self.assertIn('CheckboxColumn("삭제")', source)

    def test_outbound_product_search_requests_material_exclusion(self):
        source = Path(outbound.__file__).read_text(encoding="utf-8")
        self.assertIn("product_options(term, exclude_materials=True)", source)

    def test_product_options_excludes_legacy_true_values_for_outbound(self):
        rows = pd.DataFrame([
            {"standard_name": "완제품", "is_material": 0},
            {"standard_name": "부자재", "is_material": 1},
        ])
        captured = {}

        def fake_q(sql, params=()):
            captured["sql"] = sql
            captured["params"] = params
            return rows.drop(columns=["is_material"])

        with patch.object(products, "q", fake_q):
            products.product_options("", exclude_materials=True)
        self.assertIn("'true'", captured["sql"])
        self.assertNotIn("NOT EXISTS", captured["sql"])
        self.assertNotIn("LIKE 'G1%'", captured["sql"])
        self.assertNotIn("홍보물랙", captured["sql"])
        self.assertEqual((1,), captured["params"])

    def test_save_bom_replaces_composition_and_quantities(self):
        con = sqlite3.connect(":memory:")
        con.execute("""CREATE TABLE product_bom_items(
            id INTEGER PRIMARY KEY, finished_product TEXT, material_product TEXT,
            quantity_per REAL, updated_at TEXT,
            UNIQUE(finished_product, material_product))""")

        class ContextConnection:
            def __enter__(self): return con
            def __exit__(self, *args): return False

        with patch.object(materials, "connect", return_value=ContextConnection()):
            count = materials.save_bom("패키지 완제품", [
                {"material_product": "트레이", "quantity_per": 2},
                {"material_product": "라벨", "quantity_per": 1.5},
            ])
        self.assertEqual(2, count)
        self.assertEqual(
            [("라벨", 1.5), ("트레이", 2.0)],
            con.execute("SELECT material_product, quantity_per FROM product_bom_items ORDER BY material_product").fetchall(),
        )
        con.close()

    def test_package_production_deducts_stock_and_records_history(self):
        con = sqlite3.connect(":memory:")
        con.executescript("""
            CREATE TABLE product_bom_items(id INTEGER PRIMARY KEY, finished_product TEXT,
                material_product TEXT, quantity_per REAL, updated_at TEXT,
                UNIQUE(finished_product, material_product));
            CREATE TABLE products(standard_name TEXT, material_type TEXT);
            CREATE TABLE inventory(id INTEGER PRIMARY KEY, company TEXT, product_name TEXT,
                warehouse_name TEXT, lot TEXT, exp_date TEXT, location TEXT, qty INTEGER, updated_at TEXT);
            CREATE TABLE transactions(id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT, actor TEXT,
                tx_type TEXT, product_name TEXT, warehouse_name TEXT, lot TEXT, exp_date TEXT,
                from_company TEXT, from_location TEXT, to_company TEXT, to_location TEXT,
                qty INTEGER, memo TEXT, final_stock INTEGER);
            INSERT INTO product_bom_items VALUES(1,'완제품','트레이',2,NULL);
            INSERT INTO products VALUES('트레이','트레이');
            INSERT INTO inventory VALUES(1,'NOH','트레이','ERP트레이','L1','2027-01-01','G1',3,NULL);
            INSERT INTO inventory VALUES(2,'노투스','트레이','ERP트레이','L2','2028-01-01','A1',5,NULL);
        """)

        class ContextConnection:
            def __enter__(self): return con
            def __exit__(self, *args): return False

        def fake_q(sql, params=()):
            return pd.read_sql_query(sql, con, params=params)

        with patch.object(materials, "connect", return_value=ContextConnection()), patch.object(materials, "q", fake_q):
            plan = materials.execute_package_production("완제품", 3)
        self.assertEqual(6, int(plan.iloc[0]["required_qty"]))
        self.assertEqual([(1, 0), (2, 2)], con.execute("SELECT id, qty FROM inventory ORDER BY id").fetchall())
        self.assertEqual(
            [("패키지 생산", "트레이", "NOH", 3), ("패키지 생산", "트레이", "노투스", 3)],
            con.execute("SELECT tx_type, product_name, from_company, qty FROM transactions ORDER BY id").fetchall(),
        )
        con.close()

    def test_set_material_updates_every_mapping_for_standard_name(self):
        con = sqlite3.connect(":memory:")
        con.execute("CREATE TABLE products (standard_name TEXT, is_material, material_type TEXT)")
        con.executemany("INSERT INTO products VALUES (?,0,NULL)", [("트레이",), ("트레이",), ("완제품",)])

        class ContextConnection:
            def __enter__(self): return con
            def __exit__(self, *args): return False

        with patch.object(materials, "connect", return_value=ContextConnection()):
            materials.set_material_products(["트레이"], True, "트레이")
        self.assertEqual([(1, "트레이"), (1, "트레이")], con.execute("SELECT is_material, material_type FROM products WHERE standard_name='트레이'").fetchall())
        self.assertEqual((0,), con.execute("SELECT is_material FROM products WHERE standard_name='완제품'").fetchone())
        con.close()

    def test_general_product_master_screens_no_longer_edit_material_flag(self):
        matching_source = Path(product_matching.__file__).read_text(encoding="utf-8")
        stocktake_source = Path(stocktake.__file__).read_text(encoding="utf-8")
        self.assertNotIn('st.checkbox(\n                "부자재"', matching_source)
        self.assertNotIn("stock_master_is_material", stocktake_source)
        self.assertNotIn("UPDATE products SET is_material", stocktake_source)

    def test_product_matching_excel_no_longer_exposes_material_column(self):
        source = Path(products.__file__).read_text(encoding="utf-8")
        export_section = source.split("def product_master_excel_bytes", 1)[1].split("def _clean_text", 1)[0]
        self.assertNotIn('"is_material": "부자재"', export_section)
        self.assertIn('df.drop(columns=["부자재", "is_material"]', source)


if __name__ == "__main__":
    unittest.main()
