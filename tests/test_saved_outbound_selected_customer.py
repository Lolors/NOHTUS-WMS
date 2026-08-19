import unittest
from types import SimpleNamespace

from nohtus.pages.saved_outbound_business_v4 import _order_customer_summary


class SavedOutboundSelectedCustomerTests(unittest.TestCase):
    def test_selected_customer_company_wins_over_product_company_and_name(self):
        order = SimpleNamespace(
            customer_name="선택 매출처",
            customer_company="노투스팜",
            title="다른 매출처 - 제품A",
            company="NOH",
        )

        self.assertEqual(_order_customer_summary(order), "노투스팜")

    def test_blank_customer_company_does_not_use_name_or_product_company(self):
        order = SimpleNamespace(
            customer_name="과거 매출처",
            customer_company="",
            title="과거 매출처 - 제품A 외 1품목",
            company="노투스팜",
        )

        self.assertEqual(_order_customer_summary(order), "-")


if __name__ == "__main__":
    unittest.main()
