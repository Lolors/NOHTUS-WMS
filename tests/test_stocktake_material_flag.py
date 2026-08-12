import unittest
from pathlib import Path

import nohtus.pages.stocktake as stocktake


class StocktakeMaterialFlagTests(unittest.TestCase):
    def test_product_master_dialog_persists_standard_product_material_flag(self):
        source = Path(stocktake.__file__).read_text(encoding="utf-8")
        self.assertIn('st.checkbox(\n        "부자재"', source)
        self.assertIn("UPDATE products SET is_material=? WHERE TRIM(standard_name)=?", source)
        self.assertIn("보관 위치와 관계없이 이 표준제품 전체를 부자재로 분류", source)


if __name__ == "__main__":
    unittest.main()
