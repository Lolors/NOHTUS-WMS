from pathlib import Path
import unittest

from nohtus.pages.expiry_alerts import COMPANY_OPTIONS, _companies_for_groups


class ExpiryAlertsGroupingTests(unittest.TestCase):
    def test_company_filter_has_two_groups(self):
        self.assertEqual(["노투스팜·NOH·노투스", "비자료"], COMPANY_OPTIONS)
        self.assertEqual(
            ["노투스팜", "NOH", "노투스"],
            _companies_for_groups(["노투스팜·NOH·노투스"]),
        )
        self.assertEqual(["비자료"], _companies_for_groups(["비자료"]))

    def test_gmmedic_location_is_rendered_as_a_separate_section(self):
        source = Path("nohtus/pages/expiry_alerts.py").read_text(encoding="utf-8")
        self.assertIn('locations == "지엠메딕"', source)
        self.assertIn('locations != "지엠메딕"', source)
        self.assertIn('st.markdown("### 일반 로케이션")', source)
        self.assertIn('st.markdown("### 지엠메딕")', source)


if __name__ == "__main__":
    unittest.main()
