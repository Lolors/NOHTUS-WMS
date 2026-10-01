from pathlib import Path
import unittest

from nohtus.pages.expiry_alerts import PERIOD_OPTIONS, WAREHOUSE_OPTIONS


class ExpiryAlertsMobileStyleTests(unittest.TestCase):
    def test_filters_match_mobile_app_options(self):
        self.assertEqual(
            [("창고 전체", "all"), ("용인창고", "yongin"), ("화성창고", "hwaseong")],
            WAREHOUSE_OPTIONS,
        )
        self.assertEqual(
            [("3개월 이내", "3m"), ("6개월 이내", "6m"), ("1년 이내", "1y")],
            PERIOD_OPTIONS,
        )

    def test_reuses_mobile_api_query_logic_instead_of_duplicating_it(self):
        source = Path("nohtus/pages/expiry_alerts.py").read_text(encoding="utf-8")
        self.assertIn("from nohtus.mobile_api import queries as mobile_queries", source)
        self.assertIn("mobile_queries.expiry_inventory(", source)


if __name__ == "__main__":
    unittest.main()
