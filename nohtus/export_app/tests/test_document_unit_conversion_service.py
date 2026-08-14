from __future__ import annotations

import unittest
from unittest.mock import patch

from nohtus.export_app.services import document_unit_conversion_service
from nohtus.export_app.services import order_service


class DocumentUnitConversionServiceTests(unittest.TestCase):
    @patch.object(document_unit_conversion_service.db, 'executemany')
    def test_saves_document_unit_and_ea_factor(self, executemany) -> None:
        document_unit_conversion_service.save_case_conversions(
            7,
            [{'_id': 11, '문서 단위': 'box', '1 문서단위당 EA': 50}],
        )

        sql, values = executemany.call_args.args
        self.assertIn('document_unit=?', sql)
        self.assertEqual([('BOX', 50.0, 11, 7)], values)

    @patch.object(document_unit_conversion_service.db, 'executemany')
    def test_rejects_non_positive_factor(self, executemany) -> None:
        with self.assertRaisesRegex(ValueError, '0보다 커야'):
            document_unit_conversion_service.save_case_conversions(
                7,
                [{'_id': 11, '문서 단위': 'BOX', '1 문서단위당 EA': 0}],
            )

        executemany.assert_not_called()

    @patch.object(order_service, 'list_for_case')
    def test_order_editor_keeps_box_quantity_and_conversion_factor(self, list_for_case) -> None:
        list_for_case.return_value = [{
            'id': 11,
            'product_name': '제품 A',
            'document_quantity': 50,
            'quantity': 2500,
            'unit': 'EA',
            'document_unit': 'BOX',
            'ea_per_document_unit': 50,
            'purchase_price': 100,
        }]

        frame = order_service.get_order_items_dataframe(7)

        self.assertEqual(50, frame.loc[0, '수량'])
        self.assertEqual('BOX', frame.loc[0, '단위'])
        self.assertEqual(50, frame.loc[0, '1단위당 EA'])


if __name__ == '__main__':
    unittest.main()
