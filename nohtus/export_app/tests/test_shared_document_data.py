from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import patch

from nohtus.export_app.services.document_service import _aggregate_packed, _build_shipment_product_rows
from nohtus.export_app.services import export_service
from nohtus.export_app.services.shared_document_view_service import default_document_period, format_case_option


class SharedDocumentDataTests(unittest.TestCase):
    @patch('nohtus.export_app.services.export_service.now_text', return_value='2026-08-10 12:00:00')
    @patch('nohtus.export_app.services.export_service.db.execute')
    def test_updates_actual_ship_date(self, execute, _now_text) -> None:
        export_service.update_actual_ship_date(17, '2026-08-15')

        sql, params = execute.call_args.args
        self.assertIn('SET actual_ship_date=?,updated_at=?', sql)
        self.assertEqual(('2026-08-15', '2026-08-10 12:00:00', 17), params)

    def test_rejects_empty_actual_ship_date(self) -> None:
        with self.assertRaisesRegex(ValueError, '출고일을 입력하세요'):
            export_service.update_actual_ship_date(17, '  ')

    def test_default_document_period_is_one_week(self) -> None:
        self.assertEqual(
            (date(2026, 7, 31), date(2026, 8, 7)),
            default_document_period(date(2026, 8, 7)),
        )

    def test_formats_case_selector_with_shipping_details(self) -> None:
        case = {
            'country': '일본',
            'buyer': 'ABC Trading',
            'transport_mode': '항공',
            'export_no': 'EXP-2026-001',
            'product_names': '제품 A, 제품 B, 제품 C',
        }

        self.assertEqual(
            '일본 · ABC Trading · 항공 · EXP-2026-001 · 제품 A, 제품 B 외 1품목',
            format_case_option(case),
        )

    def test_uses_order_data_when_product_has_not_arrived(self) -> None:
        orders = [
            {'id': 1, 'product_name': '주문 제품 A', 'quantity': 100, 'unit': 'BOX'},
        ]

        rows = _build_shipment_product_rows(orders, [])

        self.assertEqual([{
            'business_unit': '',
            'product_name': '주문 제품 A',
            'lot_no': '',
            'expiry_date': '',
            'unit': 'BOX',
            'requested_qty': 100.0,
        }], rows)

    def test_uses_received_product_data_instead_of_order_data(self) -> None:
        orders = [
            {'id': 1, 'product_name': '주문명', 'quantity': 100, 'unit': 'BOX'},
        ]
        actual = [{
            'order_item_id': 1,
            'business_unit': '노투스팜',
            'product_name': '실제 입고 제품명',
            'lot_no': 'LOT-01',
            'expiry_date': '2028-12-31',
            'unit': 'BOX',
            'requested_qty': 100,
        }]

        rows = _build_shipment_product_rows(orders, actual)

        self.assertEqual(1, len(rows))
        self.assertEqual('실제 입고 제품명', rows[0]['product_name'])
        self.assertEqual('노투스팜', rows[0]['business_unit'])
        self.assertEqual('LOT-01', rows[0]['lot_no'])
        self.assertEqual('2028-12-31', rows[0]['expiry_date'])
        self.assertEqual(100.0, rows[0]['requested_qty'])

    def test_partial_arrival_fills_only_outstanding_quantity_from_order(self) -> None:
        orders = [
            {'id': 1, 'product_name': '주문 제품 A', 'quantity': 100, 'unit': 'EA'},
            {'id': 2, 'product_name': '주문 제품 B', 'quantity': 50, 'unit': 'BOX'},
        ]
        actual = [{
            'order_item_id': 1,
            'business_unit': '노투스',
            'product_name': '실제 제품 A',
            'lot_no': 'LOT-A',
            'expiry_date': '2029-01-01',
            'unit': 'EA',
            'requested_qty': 40,
        }]

        rows = _build_shipment_product_rows(orders, actual)
        by_name = {row['product_name']: row for row in rows}

        self.assertEqual({'실제 제품 A', '주문 제품 A', '주문 제품 B'}, set(by_name))
        self.assertEqual(40.0, by_name['실제 제품 A']['requested_qty'])
        self.assertEqual(60.0, by_name['주문 제품 A']['requested_qty'])
        self.assertEqual(50.0, by_name['주문 제품 B']['requested_qty'])
        self.assertEqual(150.0, sum(row['requested_qty'] for row in rows))

    def test_converts_internal_ea_to_document_box_quantity(self) -> None:
        packed_rows = [
            {
                'id': 1, 'box_no': 1, 'business_unit': 'NOH', 'product_name': '제품 A',
                'lot_no': 'LOT-1', 'expiry_date': '2028-12-31', 'requested_qty': 1000,
                'unit': 'BOX', 'ea_per_document_unit': 50,
            },
            {
                'id': 2, 'box_no': 1, 'business_unit': 'NOH', 'product_name': '제품 A',
                'lot_no': 'LOT-1', 'expiry_date': '2028-12-31', 'requested_qty': 1500,
                'unit': 'BOX', 'ea_per_document_unit': 50,
            },
        ]
        boxes = {1: {'weight_kg': 10, 'length_cm': 20, 'width_cm': 30, 'height_cm': 40}}

        result = _aggregate_packed(packed_rows, boxes)

        self.assertEqual(1, len(result))
        self.assertEqual(50.0, result[0]['requested_qty'])
        self.assertEqual('BOX', result[0]['unit'])



if __name__ == '__main__':
    unittest.main()
