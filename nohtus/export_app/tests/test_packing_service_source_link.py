from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from nohtus.export_app import db
from nohtus.export_app.services import packing_service
from nohtus.export_app.utils.dates import now_text
from nohtus.export_app.views import 박스_패킹_edit as packing_edit_view


class PackingServiceSourceLinkTests(unittest.TestCase):
    """박스에 부분 배정하거나 CTN을 복제할 때, 쪼개져 나온 shipment_items
    행이 source_inventory_id(WMS 실재고 연결)를 잃으면 안 된다.

    이 값이 NULL이 되면 stale_inventory_cleanup_service.reconcile_orphan_waiting_items가
    그 수량을 "더 이상 필요 없는 초과분"으로 착각해, 실제로는 5EA로 정상
    저장돼 있던 WMS 수출대기 수량을 확정 화면을 열 때마다 조용히 1EA 등으로
    깎아버리는 사고로 이어졌다."""

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

    def _create_case_and_order(self) -> tuple[int, int]:
        now = now_text()
        case_id = db.execute(
            '''INSERT INTO export_cases(
                   export_no,country,stage,status,created_at,updated_at,case_type
               ) VALUES (?,?,?,?,?,?,?)''',
            ('EXP-1', 'KR', '주문 접수', '진행중', now, now, 'current'),
        )
        order_id = db.execute(
            '''INSERT INTO order_items(case_id,product_name,quantity,unit,created_at)
               VALUES (?,?,?,?,?)''',
            (case_id, '오메가 PDT 장비', 5, 'EA', now),
        )
        return case_id, order_id

    def test_assign_partial_item_keeps_source_link_on_remainder_row(self) -> None:
        case_id, order_id = self._create_case_and_order()
        now = now_text()
        shipment_id = db.execute(
            '''INSERT INTO shipment_items(
                   case_id,order_item_id,business_unit,location,source_inventory_id,
                   product_name,lot_no,expiry_date,requested_qty,box_no,created_at,updated_at
               ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
            (case_id, order_id, 'NOH', 'P', 42, '오메가 PDT 장비', 'LOT1', '2027-01-01', 5, None, now, now),
        )

        packing_service.assign_partial_item(case_id, shipment_id, box_no=1, quantity=1)

        rows = db.rows(
            'SELECT requested_qty,box_no,source_inventory_id FROM shipment_items WHERE case_id=? ORDER BY id',
            (case_id,),
        )
        self.assertEqual(len(rows), 2)
        packed = next(r for r in rows if r['box_no'] == 1)
        remainder = next(r for r in rows if r['box_no'] is None)
        self.assertEqual(packed['requested_qty'], 1)
        self.assertEqual(packed['source_inventory_id'], 42)
        self.assertEqual(remainder['requested_qty'], 4)
        # 이 값이 None이면 리포트된 버그가 재현된다: 정상 저장된 4EA가
        # WMS 재고 연결에서 보이지 않게 되어, 확정 화면에서 전체 수량이
        # 1EA로 깎여버린다.
        self.assertEqual(remainder['source_inventory_id'], 42)

    def test_clone_box_keeps_source_link_on_cloned_rows(self) -> None:
        case_id, order_id = self._create_case_and_order()
        now = now_text()
        shipment_id = db.execute(
            '''INSERT INTO shipment_items(
                   case_id,order_item_id,business_unit,location,source_inventory_id,
                   product_name,lot_no,expiry_date,requested_qty,box_no,created_at,updated_at
               ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
            (case_id, order_id, 'NOH', 'P', 42, '오메가 PDT 장비', 'LOT1', '2027-01-01', 1, 1, now, now),
        )
        db.execute(
            'INSERT INTO boxes(case_id,box_no,updated_at) VALUES (?,?,?)',
            (case_id, 1, now),
        )

        packing_service.clone_box(case_id, source_box_no=1, clone_count=1)

        cloned = db.row(
            'SELECT source_inventory_id FROM shipment_items WHERE case_id=? AND id<>? ORDER BY id',
            (case_id, shipment_id),
        )
        self.assertIsNotNone(cloned)
        self.assertEqual(cloned['source_inventory_id'], 42)

    def test_assign_repeated_ctns_keeps_source_link_on_every_box(self) -> None:
        """5EA를 CTN당 1개씩 '반복 담기'로 5개 박스에 나눠 담는, 사용자가
        실제로 보고한 시나리오를 그대로 재현한다: 이 버그가 있으면 오메가
        PDT 장비 5EA 중 1EA(첫 박스)만 WMS 재고와 연결된 채로 남고, 나머지
        4EA는 연결이 끊겨 확정 화면에서 전체 수량이 1EA로 보이게 된다."""
        case_id, order_id = self._create_case_and_order()
        now = now_text()
        shipment_id = db.execute(
            '''INSERT INTO shipment_items(
                   case_id,order_item_id,business_unit,location,source_inventory_id,
                   product_name,lot_no,expiry_date,requested_qty,box_no,created_at,updated_at
               ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
            (case_id, order_id, 'NOH', 'P', 42, '오메가 PDT 장비', 'LOT1', '2027-01-01', 5, None, now, now),
        )

        packing_edit_view.assign_repeated_ctns(
            case_id, shipment_id,
            quantity_per_box=1, length_cm=10, width_cm=10, height_cm=10, weight_kg=1,
        )

        rows = db.rows(
            'SELECT requested_qty,box_no,source_inventory_id FROM shipment_items WHERE case_id=? ORDER BY id',
            (case_id,),
        )
        self.assertEqual(len(rows), 5)
        total_qty = sum(int(r['requested_qty'] or 0) for r in rows)
        linked_qty = sum(int(r['requested_qty'] or 0) for r in rows if r['source_inventory_id'] == 42)
        self.assertEqual(total_qty, 5)
        self.assertEqual(linked_qty, 5)


if __name__ == '__main__':
    unittest.main()
