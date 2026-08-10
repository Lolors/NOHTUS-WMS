from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from nohtus.export_app import db
from nohtus.export_app.services import export_service, shipment_service, stage_service
from nohtus.export_app.utils.dates import now_text


class StageFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.original_db_path = db.DB_PATH
        self.original_upload_dir = db.UPLOAD_DIR
        db.DB_PATH = Path(self.temp_dir.name) / 'test.db'
        db.UPLOAD_DIR = Path(self.temp_dir.name) / 'uploads'
        db._initialize_database_runtime.cache_clear()
        db.init_db.cache_clear()
        self.backup_patch = patch.object(db, 'backup_to_usb', return_value=None)
        self.backup_patch.start()
        db.init_db()

    def tearDown(self) -> None:
        self.backup_patch.stop()
        db.DB_PATH = self.original_db_path
        db.UPLOAD_DIR = self.original_upload_dir
        db._initialize_database_runtime.cache_clear()
        db.init_db.cache_clear()
        self.temp_dir.cleanup()

    def _create_case(self) -> int:
        now = now_text()
        case_id = db.execute(
            '''INSERT INTO export_cases(
                   export_no,country,stage,status,created_at,updated_at,case_type
               ) VALUES (?,?,?,?,?,?,?)''',
            ('TEST-001', 'KR', '주문 접수', '진행중', now, now, 'current'),
        )
        for product in ('A', 'B'):
            db.execute(
                '''INSERT INTO order_items(case_id,product_name,quantity,unit,created_at)
                   VALUES (?,?,?,?,?)''',
                (case_id, product, 100, 'EA', now),
            )
        return case_id

    def test_each_order_item_must_be_complete_before_packing_complete(self) -> None:
        case_id = self._create_case()
        orders = db.rows('SELECT id,product_name FROM order_items WHERE case_id=? ORDER BY id', (case_id,))
        now = now_text()

        db.execute(
            '''INSERT INTO shipment_items(
                   case_id,order_item_id,product_name,requested_qty,box_no,created_at,updated_at
               ) VALUES (?,?,?,?,?,?,?)''',
            (case_id, orders[0]['id'], 'A', 100, 1, now, now),
        )
        self.assertEqual('패킹 대기', stage_service.sync_case_stage(case_id))

        db.execute(
            '''INSERT INTO shipment_items(
                   case_id,order_item_id,product_name,requested_qty,box_no,created_at,updated_at
               ) VALUES (?,?,?,?,?,?,?)''',
            (case_id, orders[1]['id'], 'B', 100, None, now, now),
        )
        self.assertEqual('패킹 대기', stage_service.sync_case_stage(case_id))

        db.execute(
            'UPDATE shipment_items SET box_no=1 WHERE case_id=? AND order_item_id=?',
            (case_id, orders[1]['id']),
        )
        self.assertEqual('패킹 완료', stage_service.sync_case_stage(case_id))

    def test_domestic_delivery_case_is_editable_for_intake(self) -> None:
        case_id = self._create_case()
        db.execute(
            """UPDATE export_cases
               SET stage='국내배송',status='완료',domestic_method='택배',
                   tracking_no='TRACK-001'
               WHERE id=?""",
            (case_id,),
        )

        editable_ids = {int(case['id']) for case in export_service.intake_editable_cases()}

        self.assertIn(case_id, editable_ids)

    def test_confirmed_export_can_return_to_waiting_without_losing_saved_data(self) -> None:
        case_id = self._create_case()
        now = now_text()
        order = db.row('SELECT id FROM order_items WHERE case_id=? ORDER BY id LIMIT 1', (case_id,))
        db.execute(
            '''INSERT INTO boxes(case_id,box_no,length_cm,width_cm,height_cm,weight_kg,updated_at)
               VALUES (?,?,?,?,?,?,?)''',
            (case_id, 1, 40, 30, 20, 5, now),
        )
        db.execute(
            '''INSERT INTO shipment_items(
                   case_id,order_item_id,product_name,requested_qty,box_no,created_at,updated_at
               ) VALUES (?,?,?,?,?,?,?)''',
            (case_id, order['id'], 'A', 100, 1, now, now),
        )
        db.execute(
            '''UPDATE export_cases
               SET stage='국내배송',status='완료',domestic_method='택배',tracking_no='TRACK-001'
               WHERE id=?''',
            (case_id,),
        )

        export_service.reopen_for_export_waiting(case_id)

        case = db.row(
            'SELECT stage,status,domestic_method,tracking_no FROM export_cases WHERE id=?',
            (case_id,),
        )
        shipment = db.row(
            'SELECT product_name,requested_qty,box_no FROM shipment_items WHERE case_id=?',
            (case_id,),
        )
        self.assertEqual('패킹 대기', case['stage'])
        self.assertEqual('진행중', case['status'])
        self.assertEqual('택배', case['domestic_method'])
        self.assertEqual('TRACK-001', case['tracking_no'])
        self.assertEqual('A', shipment['product_name'])
        self.assertEqual(100, shipment['requested_qty'])
        self.assertEqual(1, shipment['box_no'])

    def test_only_confirmed_current_export_can_return_to_waiting(self) -> None:
        case_id = self._create_case()

        with self.assertRaisesRegex(ValueError, '수출확정된 건만'):
            export_service.reopen_for_export_waiting(case_id)

    def test_editing_packed_intake_reopens_case_and_only_unpacks_selected_order(self) -> None:
        case_id = self._create_case()
        orders = db.rows('SELECT id,product_name FROM order_items WHERE case_id=? ORDER BY id', (case_id,))
        now = now_text()
        for box_no, order in enumerate(orders, start=1):
            db.execute(
                '''INSERT INTO boxes(case_id,box_no,length_cm,width_cm,height_cm,weight_kg,updated_at)
                   VALUES (?,?,?,?,?,?,?)''',
                (case_id, box_no, 40, 30, 20, 5, now),
            )
            db.execute(
                '''INSERT INTO shipment_items(
                       case_id,order_item_id,product_name,lot_no,expiry_date,
                       requested_qty,box_no,created_at,updated_at
                   ) VALUES (?,?,?,?,?,?,?,?,?)''',
                (case_id, order['id'], order['product_name'], 'OLD', '2027-01-01',
                 100, box_no, now, now),
            )
        db.execute(
            """UPDATE export_cases
               SET stage='국내배송',status='완료',domestic_method='택배',
                   tracking_no='TRACK-001'
               WHERE id=?""",
            (case_id,),
        )

        impact = shipment_service.packing_impact_for_order(case_id, int(orders[0]['id']))
        shipment_service.save_for_order(
            case_id,
            int(orders[0]['id']),
            [{
                'business_unit': '본사',
                'product_name': 'A-NEW',
                'lot_no': 'NEW',
                'expiry_date': '2028-02-02',
                'requested_qty': 100,
            }],
        )

        case = db.row(
            'SELECT stage,status,domestic_method,tracking_no FROM export_cases WHERE id=?',
            (case_id,),
        )
        changed = shipment_service.list_linked(case_id, int(orders[0]['id']))
        untouched = shipment_service.list_linked(case_id, int(orders[1]['id']))
        box_numbers = {int(row['box_no']) for row in db.rows('SELECT box_no FROM boxes WHERE case_id=?', (case_id,))}

        self.assertEqual({'packed_row_count': 1, 'affected_box_count': 1}, impact)
        self.assertEqual('패킹 대기', case['stage'])
        self.assertEqual('진행중', case['status'])
        self.assertEqual('택배', case['domestic_method'])
        self.assertEqual('TRACK-001', case['tracking_no'])
        self.assertEqual('A-NEW', changed[0]['product_name'])
        self.assertEqual('NEW', changed[0]['lot_no'])
        self.assertEqual('2028-02-02', changed[0]['expiry_date'])
        self.assertIsNone(changed[0]['box_no'])
        self.assertEqual(2, untouched[0]['box_no'])
        self.assertEqual({2}, box_numbers)


if __name__ == '__main__':
    unittest.main()