import unittest

from nohtus.pages.outbound_date_fix import _last_sale_text
from nohtus.services.customer_recent_sales import resolve_customer_last_sale_date


class CustomerRecentSalesCompanyTests(unittest.TestCase):
    def setUp(self):
        self.exact_map = {
            ("동일거래처", "노투스팜"): "2026-07-01",
            ("동일거래처", "NOH"): "2026-07-20",
        }
        self.name_map = {"동일거래처": "2026-07-20"}

    def test_same_customer_name_uses_each_company_date(self):
        self.assertEqual(
            resolve_customer_last_sale_date("동일거래처", "노투스팜", self.exact_map, self.name_map),
            "2026-07-01",
        )
        self.assertEqual(
            resolve_customer_last_sale_date("동일거래처", "NOH", self.exact_map, self.name_map),
            "2026-07-20",
        )

    def test_company_with_no_history_does_not_fall_back_to_other_company(self):
        self.assertEqual(
            resolve_customer_last_sale_date("동일거래처", "노투스", self.exact_map, self.name_map),
            "",
        )
        self.assertEqual(
            _last_sale_text("동일거래처", "노투스", self.exact_map, self.name_map),
            "최근거래 없음",
        )

    def test_companyless_manual_customer_can_use_name_fallback(self):
        self.assertEqual(
            resolve_customer_last_sale_date("동일거래처", "", self.exact_map, self.name_map),
            "2026-07-20",
        )


if __name__ == "__main__":
    unittest.main()
