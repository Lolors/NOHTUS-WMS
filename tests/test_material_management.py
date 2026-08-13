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
        self.assertIn("NOT EXISTS", captured["sql"])
        self.assertIn("LIKE 'G1%'", captured["sql"])
        self.assertIn("홍보물랙", captured["sql"])
        self.assertEqual((1,), captured["params"])

    def test_set_material_updates_every_mapping_for_standard_name(self):
        con = sqlite3.connect(":memory:")
        con.execute("CREATE TABLE products (standard_name TEXT, is_material)")
        con.executemany("INSERT INTO products VALUES (?,0)", [("트레이",), ("트레이",), ("완제품",)])

        class ContextConnection:
            def __enter__(self): return con
            def __exit__(self, *args): return False

        with patch.object(materials, "connect", return_value=ContextConnection()):
            materials.set_material_products(["트레이"], True)
        self.assertEqual([(1,), (1,)], con.execute("SELECT is_material FROM products WHERE standard_name='트레이'").fetchall())
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
