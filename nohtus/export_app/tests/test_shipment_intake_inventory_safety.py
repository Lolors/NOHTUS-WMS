import unittest
from unittest.mock import patch

import pandas as pd

from nohtus.export_app.services import folder_service
from nohtus.export_app.views.실출고_입력 import inventory_selection_source


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


if __name__ == '__main__':
    unittest.main()
