import unittest

import pandas as pd

from nohtus.pages.closing_date_fix import _deduplicate_outbound_details


class ClosingOutboundDetailDeduplicationTests(unittest.TestCase):
    @staticmethod
    def _row(detail_id, *, order_id=1, quantity=10):
        return {
            "출고지시서ID": order_id,
            "출고상세ID": detail_id,
            "재고ID": 7,
            "사업장": "노투스팜",
            "로케이션": "B1-03-02",
            "표준제품명": "제품A",
            "제조번호": "LOT-1",
            "유통기한": "2029-05-28",
            "매출처": "거래처A",
            "출고수량": quantity,
        }

    def test_same_outbound_detail_is_counted_once(self):
        rows = pd.DataFrame([self._row(101), self._row(101), self._row(101)])

        result = _deduplicate_outbound_details(rows)

        self.assertEqual(len(result), 1)
        self.assertEqual(result["매출처"].tolist(), ["거래처A"])
        self.assertEqual(int(result["출고수량"].sum()), 10)

    def test_same_saved_shipment_with_distinct_detail_ids_is_counted_once(self):
        rows = pd.DataFrame([self._row(detail_id) for detail_id in range(101, 109)])

        result = _deduplicate_outbound_details(rows)

        self.assertEqual(len(result), 1)
        self.assertEqual(int(result["출고수량"].sum()), 10)

    def test_same_shipment_from_different_orders_is_preserved(self):
        rows = pd.DataFrame([self._row(101, order_id=1), self._row(102, order_id=2)])

        result = _deduplicate_outbound_details(rows)

        self.assertEqual(result["출고수량"].tolist(), [10, 10])

    def test_export_rows_are_preserved(self):
        rows = pd.DataFrame(
            [
                self._row(None, order_id=-1, quantity=30),
                self._row(None, order_id=-1, quantity=30),
            ]
        )

        result = _deduplicate_outbound_details(rows)

        self.assertEqual(result["출고수량"].tolist(), [30, 30])


if __name__ == "__main__":
    unittest.main()
