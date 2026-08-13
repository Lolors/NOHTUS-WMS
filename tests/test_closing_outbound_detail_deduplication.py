import unittest

import pandas as pd

from nohtus.pages.closing_date_fix import _deduplicate_outbound_details


class ClosingOutboundDetailDeduplicationTests(unittest.TestCase):
    def test_same_outbound_detail_is_counted_once(self):
        rows = pd.DataFrame(
            [
                {"출고상세ID": 101, "매출처": "거래처A", "출고수량": 10},
                {"출고상세ID": 101, "매출처": "거래처A", "출고수량": 10},
                {"출고상세ID": 101, "매출처": "거래처A", "출고수량": 10},
            ]
        )

        result = _deduplicate_outbound_details(rows)

        self.assertEqual(len(result), 1)
        self.assertEqual(result["매출처"].tolist(), ["거래처A"])
        self.assertEqual(int(result["출고수량"].sum()), 10)

    def test_distinct_and_non_outbound_rows_are_preserved(self):
        rows = pd.DataFrame(
            [
                {"출고상세ID": 101, "출고수량": 10},
                {"출고상세ID": 102, "출고수량": 20},
                {"출고상세ID": None, "출고수량": 30},
                {"출고상세ID": None, "출고수량": 40},
            ]
        )

        result = _deduplicate_outbound_details(rows)

        self.assertEqual(result["출고수량"].tolist(), [10, 20, 30, 40])


if __name__ == "__main__":
    unittest.main()
