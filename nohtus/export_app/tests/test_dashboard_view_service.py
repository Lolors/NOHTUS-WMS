from __future__ import annotations

from datetime import date, datetime
import unittest
from unittest.mock import patch

import pandas as pd

from nohtus.export_app.services.dashboard_view_service import (
    recent_order_cases,
    sales_registration_statuses,
    stage_bar_colors,
    timeline_bounds,
    timeline_date,
    timeline_date_label,
    timeline_period,
)


class DashboardTimelineTests(unittest.TestCase):
    def test_historical_case_uses_ship_date(self) -> None:
        case = {
            'export_no': 'HIS-2025-001',
            'actual_ship_date': '2025-03-14',
            'created_at': '2026-07-31 12:00:00',
        }
        self.assertEqual('2025-03-14', timeline_date(case))

    def test_current_case_uses_created_date_even_after_shipping(self) -> None:
        case = {
            'export_no': 'EXP-2026-001',
            'actual_ship_date': '2026-07-30',
            'created_at': '2026-06-08 09:30:00',
        }
        self.assertEqual('2026-06-08', timeline_date(case))

    def test_missing_ship_date_falls_back_to_created_date(self) -> None:
        case = {
            'export_no': 'HIS-2026-001',
            'actual_ship_date': '',
            'created_at': '2026-07-05 09:30:00',
        }
        self.assertEqual('2026-07-05', timeline_date(case))

    def test_historical_case_is_a_one_day_bar_on_ship_date(self) -> None:
        case = {
            'export_no': 'HIS-2025-001',
            'actual_ship_date': '2025-03-14',
            'created_at': '2026-07-31 12:00:00',
        }
        self.assertEqual(
            ('2025-03-14', '2025-03-14'),
            timeline_period(case),
        )

    def test_current_case_keeps_registration_to_shipping_period(self) -> None:
        case = {
            'export_no': 'EXP-2026-001',
            'actual_ship_date': '2026-07-30',
            'created_at': '2026-06-08 09:30:00',
        }
        self.assertEqual(
            ('2026-06-08', '2026-07-30'),
            timeline_period(case),
        )

    def test_recent_filter_uses_registration_date(self) -> None:
        cases = [
            {
                'export_no': 'HIS-2024-001',
                'actual_ship_date': '2024-02-01',
                'created_at': '2026-06-29 12:00:00',
            },
            {
                'export_no': 'EXP-2026-001',
                'actual_ship_date': '',
                'created_at': '2026-07-01 12:00:00',
            },
        ]
        result = recent_order_cases(cases, reference=datetime(2026, 7, 31), month_count=1)
        self.assertEqual(['EXP-2026-001'], [case['export_no'] for case in result])

    def test_timeline_date_label(self) -> None:
        self.assertEqual('7월 31일', timeline_date_label('2026-07-31'))

    def test_timeline_bounds_include_today_and_padding(self) -> None:
        rows = [
            {'start_date': '2026-06-08', 'end_date': '2026-06-28'},
            {'start_date': '2026-07-20', 'end_date': '2026-08-02'},
        ]
        self.assertEqual(
            (date(2026, 5, 25), date(2026, 8, 16)),
            timeline_bounds(rows, today=date(2026, 7, 31)),
        )

    def test_timeline_bar_colors_follow_display_stage(self) -> None:
        self.assertEqual(stage_bar_colors('출고 대기'), stage_bar_colors('패킹 대기'))
        self.assertNotEqual(stage_bar_colors('패킹 대기'), stage_bar_colors('패킹 완료'))

    def test_sales_registration_statuses_follow_confirmation_orders(self) -> None:
        orders = pd.DataFrame([
            {'export_no': 'EXP-WAIT', 'status': 'waiting'},
            {'export_no': 'EXP-PART', 'status': 'partial'},
            {'export_no': 'EXP-DONE', 'status': 'confirmed'},
        ])
        with patch(
            'nohtus.export_app.services.dashboard_view_service.export_confirm_service.list_active_orders',
            return_value=orders,
        ):
            result = sales_registration_statuses(
                ['EXP-WAIT', 'EXP-PART', 'EXP-DONE', 'EXP-NONE']
            )

        self.assertEqual('미등록', result['EXP-WAIT'])
        self.assertEqual('등록중', result['EXP-PART'])
        self.assertEqual('등록완료', result['EXP-DONE'])
        self.assertEqual('미등록', result['EXP-NONE'])

    def test_duplicate_links_are_complete_only_when_all_are_confirmed(self) -> None:
        orders = pd.DataFrame([
            {'export_no': 'EXP-MIXED', 'status': 'confirmed'},
            {'export_no': 'EXP-MIXED', 'status': 'waiting'},
            {'export_no': 'EXP-DONE', 'status': 'confirmed'},
            {'export_no': 'EXP-DONE', 'status': 'confirmed'},
        ])
        with patch(
            'nohtus.export_app.services.dashboard_view_service.export_confirm_service.list_active_orders',
            return_value=orders,
        ):
            result = sales_registration_statuses(['EXP-MIXED', 'EXP-DONE'])

        self.assertEqual('등록중', result['EXP-MIXED'])
        self.assertEqual('등록완료', result['EXP-DONE'])


if __name__ == '__main__':
    unittest.main()
