import unittest
from types import SimpleNamespace

from nohtus.pages.saved_outbound_business_v4 import _order_customer_summary


class SavedOutboundSelectedCustomerTests(unittest.TestCase):
    def test_selected_customer_wins_over_product_company_and_title(self):
        order = SimpleNamespace(
            customer_name="선택 매출처",
            title="다른 매출처 - 제품A",
            company="NOH",
        )

        self.assertEqual(_order_customer_summary(order), "선택 매출처")

    def test_legacy_blank_customer_falls_back_to_title(self):
        order = SimpleNamespace(
            customer_name="",
            title="과거 매출처 - 제품A 외 1품목",
            company="노투스팜",
        )

        self.assertEqual(_order_customer_summary(order), "과거 매출처")


if __name__ == "__main__":
    unittest.main()
