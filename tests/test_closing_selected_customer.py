import unittest
from unittest.mock import patch

import pandas as pd

from nohtus.pages.closing import (
    _outbound_customer_from_saved_or_title,
    _scheduled_outbound_business_log,
)


class ClosingSelectedCustomerTests(unittest.TestCase):
    def setUp(self):
        self.customers = pd.DataFrame(
            [
                {"customer_name": "선택 매출처", "manager": "선택 담당자"},
                {"customer_name": "제목 매출처", "manager": "제목 담당자"},
            ]
        )

    def test_saved_customer_wins_over_title(self):
        customer, manager = _outbound_customer_from_saved_or_title(
            "선택 매출처",
            "제목 매출처 - 제품A",
            self.customers,
        )

        self.assertEqual(customer, "선택 매출처")
        self.assertEqual(manager, "선택 담당자")

    def test_legacy_blank_customer_falls_back_to_title(self):
        customer, manager = _outbound_customer_from_saved_or_title(
            "",
            "제목 매출처 - 제품A",
            self.customers,
        )

        self.assertEqual(customer, "제목 매출처")
        self.assertEqual(manager, "제목 담당자")

    @patch("nohtus.pages.closing.q")
    def test_business_log_uses_selected_customer_not_item_company(self, mock_q):
        mock_q.return_value = pd.DataFrame(
            [
                {
                    "log_date": "2026-08-18",
                    "created_at": "2026-08-18 09:30:00",
                    "title": "제목 매출처 - 제품A",
                    "customer_name": "선택 매출처",
                    "company": "NOH",
                    "product_name": "제품A",
                    "lot": "LOT-1",
                    "exp_date": "2027-01-01",
                    "qty": 3,
                    "order_memo": "",
                }
            ]
        )

        rows = _scheduled_outbound_business_log("2026-08-18", self.customers)

        self.assertEqual(rows[0]["사업장"], "NOH")
        self.assertEqual(rows[0]["거래처(매출처/입고처)"], "선택 매출처")
        self.assertEqual(rows[0]["담당자"], "선택 담당자")


if __name__ == "__main__":
    unittest.main()
