import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from nohtus.export_app.services import folder_service
from nohtus.export_app.views.실출고_입력 import (
    distribute_group_quantity,
    inventory_selection_source,
    remaining_shipment_ids,
    saved_inventory_source,
    selected_shipment_ids,
    shipment_ids_from_group,
)


class ShipmentIntakeInventorySafetyTests(unittest.TestCase):
    def test_saved_inventory_deletion_uses_selection_outside_the_form(self):
        source = Path('nohtus/export_app/views/실출고_입력.py').read_text(encoding='utf-8')
        selection = source.index("delete_labels = st.multiselect(")
        form = source.index("with st.form(", selection)
        self.assertLess(selection, form)
        self.assertIn("disabled=not selected_saved_ids", source[selection:form])

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

    def test_same_product_lot_and_expiry_are_shown_as_one_saved_row(self):
        current = [
            {
                'id': 11, 'business_unit': '노투스팜', 'product_name': '제품A',
                'lot_no': 'LOT-1', 'expiry_date': '2029-05-28', 'requested_qty': 2,
            },
            {
                'id': 12, 'business_unit': '노투스팜', 'product_name': '제품A',
                'lot_no': 'LOT-1', 'expiry_date': '2029-05-28', 'requested_qty': 3,
            },
        ]

        result = saved_inventory_source(current)

        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]['_shipment_ids'], '11,12')
        self.assertEqual(result.iloc[0]['선택수량'], 5)

    def test_group_quantity_is_distributed_without_losing_trace_rows(self):
        rows = [
            {'id': 11, 'requested_qty': 2},
            {'id': 12, 'requested_qty': 3},
        ]

        result = distribute_group_quantity(rows, 4)

        self.assertEqual([row['id'] for row in result], [11, 12])
        self.assertEqual([row['requested_qty'] for row in result], [2, 2])
        self.assertEqual(shipment_ids_from_group('11,12'), [11, 12])

    def test_domestic_delivery_folder_failure_is_a_warning_after_save(self):
        source = Path('nohtus/export_app/views/국내배송.py').read_text(encoding='utf-8')

        self.assertIn('folder_service.try_sync_case_folder(case_id)', source)
        self.assertIn("delivery_folder_warning", source)

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
