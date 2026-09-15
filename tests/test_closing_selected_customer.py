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
                {"customer_name": "선택 매출처", "company": "노투스팜", "manager": "선택 담당자"},
                {"customer_name": "제목 매출처", "company": "노투스", "manager": "제목 담당자"},
            ]
        )

    def test_saved_customer_name_wins_over_title(self):
        customer, manager = _outbound_customer_from_saved_or_title(
            "선택 매출처",
            "제목 매출처 - 제품A",
            self.customers,
            "노투스팜",
        )

        self.assertEqual(customer, "선택 매출처")
        self.assertEqual(manager, "선택 담당자")

    def test_legacy_blank_customer_falls_back_to_title_customer_name(self):
        customer, manager = _outbound_customer_from_saved_or_title(
            "",
            "제목 매출처 - 제품A",
            self.customers,
        )

        self.assertEqual(customer, "제목 매출처")
        self.assertEqual(manager, "제목 담당자")

    @patch("nohtus.pages.closing.q")
    def test_business_log_uses_selected_customer_company_not_item_company(self, mock_q):
        """매출 사업장은 실제로 재고를 뺀 회사(company=NOH)가 아니라, 매출처
        선택 시 정한 사업장(customer_company=노투스팜) 기준이어야 한다 —
        "사업장 구분 없이"로 다른 사업장 재고를 골라도 매출은 선택한
        매출처 사업장으로 잡혀야 하기 때문."""
        mock_q.return_value = pd.DataFrame(
            [
                {
                    "log_date": "2026-08-18",
                    "created_at": "2026-08-18 09:30:00",
                    "title": "제목 매출처 - 제품A",
                    "customer_name": "선택 매출처",
                    "customer_company": "노투스팜",
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

        self.assertEqual(rows[0]["사업장"], "노투스팜")
        self.assertEqual(rows[0]["거래처(매출처/입고처)"], "선택 매출처")
        self.assertEqual(rows[0]["담당자"], "선택 담당자")

    @patch("nohtus.pages.closing.q")
    def test_business_log_falls_back_to_item_company_when_customer_company_blank(self, mock_q):
        """직접입력 매출처 등 customer_company가 비어 있는 옛/특수 지시서는
        실제 재고 사업장으로 되돌아간다."""
        mock_q.return_value = pd.DataFrame(
            [
                {
                    "log_date": "2026-08-18",
                    "created_at": "2026-08-18 09:30:00",
                    "title": "제목 매출처 - 제품A",
                    "customer_name": "선택 매출처",
                    "customer_company": "",
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


if __name__ == "__main__":
    unittest.main()
