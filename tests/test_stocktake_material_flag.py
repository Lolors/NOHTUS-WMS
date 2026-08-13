import unittest
from pathlib import Path

import nohtus.pages.stocktake as stocktake


class StocktakeMaterialFlagTests(unittest.TestCase):
    def test_product_master_dialog_no_longer_manages_material_flag(self):
        source = Path(stocktake.__file__).read_text(encoding="utf-8")
        self.assertNotIn("stock_master_is_material", source)
        self.assertNotIn("UPDATE products SET is_material", source)
        self.assertNotIn("보관 위치와 관계없이 이 표준제품 전체를 부자재로 분류", source)


if __name__ == "__main__":
    unittest.main()
