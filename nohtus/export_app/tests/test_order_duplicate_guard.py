from __future__ import annotations

import unittest

import pandas as pd

from nohtus.export_app.services import order_save_guard


def _orders(*names: str) -> pd.DataFrame:
    return order_save_guard.with_row_numbers(pd.DataFrame([
        {'제품명': name, '수량': 1, '단위': 'EA', '매입가': 0}
        for name in names
    ]))


class OrderDuplicateGuardTests(unittest.TestCase):
    def test_packaging_quantity_keeps_products_distinct(self) -> None:
        rows = _orders(
            '리쥬네르 34 9핀 니들 (1EA)',
            '리쥬네르 34 9핀 니들(20EA)',
        )

        self.assertEqual(order_save_guard.find_duplicate_rows(rows), [])

    def test_spacing_only_difference_is_still_duplicate(self) -> None:
        rows = _orders(
            '리쥬네르 34 9핀 니들 (1EA)',
            ' 리쥬네르 34  9핀 니들(1ea) ',
        )

        duplicates = order_save_guard.find_duplicate_rows(rows)

        self.assertEqual([row['행'] for row in duplicates], [1, 2])
