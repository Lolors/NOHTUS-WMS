import unittest

import pandas as pd

from nohtus.pages.closing import _closing_customer_name


class ClosingExportCustomerNameTests(unittest.TestCase):
    def test_export_waiting_customer_keeps_spaces_in_full_title(self):
        row = pd.Series({
            '출고지시서ID': -7,
            '출고지시서제목': '미국-글로우필 메디앤톡-해상',
        })

        self.assertEqual(
            _closing_customer_name(row, pd.DataFrame()),
            '미국-글로우필 메디앤톡-해상',
        )

    def test_regular_outbound_still_infers_registered_customer(self):
        row = pd.Series({
            '출고지시서ID': 7,
            '출고지시서제목': '글로우필 메디앤톡 제품A 외 2품목',
        })
        customers = pd.DataFrame([
            {'customer_name': '글로우필 메디앤톡', 'manager': '담당자'},
        ])

        self.assertEqual(
            _closing_customer_name(row, customers),
            '글로우필 메디앤톡',
        )

    def test_regular_outbound_uses_full_stored_customer_before_title_guess(self):
        row = pd.Series({
            '출고지시서ID': 8,
            '출고지시서제목': '미국-글로우필 메디앤톡 제품A 외 2품목',
            '저장매출처': '미국-글로우필 메디앤톡',
        })

        self.assertEqual(
            _closing_customer_name(row, pd.DataFrame()),
            '미국-글로우필 메디앤톡',
        )


if __name__ == '__main__':
    unittest.main()
