import unittest
from unittest.mock import patch

import pandas as pd

from nohtus.export_app.services import folder_service
from nohtus.export_app.views.실출고_입력 import (
    inventory_selection_source,
    remaining_shipment_ids,
    selected_shipment_ids,
)


class ShipmentIntakeInventorySafetyTests(unittest.TestCase):
    def test_stock_rows_show_location_to_distinguish_real_inventory(self):
        stock = pd.DataFrame([
            {
                'id': 1, 'company': '노투스팜', 'location': 'A-01',
                'product_name': '제품A', 'lot': 'LOT-1', 'exp_date': '2029-05-28',
                'qty': 160, 'warehouse_name': '',
            },
            {
                'id': 2, 'company': '노투스팜', 'location': 'B-02',
                'product_name': '제품A', 'lot': 'LOT-1', 'exp_date': '2029-05-28',
                'qty': 160, 'warehouse_name': '',
            },
        ])

        result = inventory_selection_source([], stock)

        self.assertEqual(result['로케이션'].tolist(), ['A-01', 'B-02'])
        self.assertEqual(result['_inventory_id'].tolist(), [1, 2])

    def test_folder_permission_error_is_returned_instead_of_raised(self):
        with patch.object(folder_service, 'sync_case_folder', side_effect=PermissionError('denied')):
            folder, error = folder_service.try_sync_case_folder(7)

        self.assertIsNone(folder)
        self.assertIn('denied', error)

    def test_selected_shipment_ids_returns_only_checked_valid_ids(self):
        edited = pd.DataFrame([
            {'선택': True, '_shipment_id': 11},
            {'선택': False, '_shipment_id': 12},
            {'선택': True, '_shipment_id': None},
        ])

        self.assertEqual(selected_shipment_ids(edited), [11])

    def test_remaining_shipment_ids_checks_delete_result(self):
        rows = [{'id': 12}]
        export_db = remaining_shipment_ids.__globals__['export_db']
        with patch.object(export_db, 'rows', return_value=rows) as query:
            result = remaining_shipment_ids(3, 4, [11, 12])

        self.assertEqual(result, [12])
        self.assertEqual(query.call_args.args[1], (3, 4, 11, 12))


if __name__ == '__main__':
    unittest.main()
