from __future__ import annotations

import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from nohtus.export_app import db
from nohtus.export_app.services import stale_inventory_cleanup_service
from nohtus.export_app.utils.dates import now_text
from nohtus.services import export_waiting as export_waiting_service


class ReconcileOrphanWaitingItemsSignatureTests(unittest.TestCase):
    """reconcile_orphan_waiting_items가 shipment_items <-> export_waiting_items를
    원본 inventory id가 아니라 (사업장,제품명,LOT,유통기한) 재고키로 맞춰보게
    바꾼 수정을 검증한다.

    실사용 버그: 박스 분할/복제나 _take_source의 서명 기반 대체 매칭으로
    두 테이블에 기록된 id가 갈라지면(둘 다 같은 재고를 가리키지만 숫자가
    다름), 예전 id 매칭 로직은 정상 저장된 수량을 "저장에서 사라진 초과분"
    으로 오인해 WMS 수출대기 예약을 통째로 삭제해버렸다."""

    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()

        self.original_db_path = db.DB_PATH
        self.original_upload_dir = db.UPLOAD_DIR
        db.DB_PATH = Path(self.temp_dir.name) / 'export.db'
        db.UPLOAD_DIR = Path(self.temp_dir.name) / 'uploads'
        db._initialize_database_runtime.cache_clear()
        db.init_db.cache_clear()
        self.backup_patch = patch.object(db, 'backup_to_usb', return_value=None)
        self.backup_patch.start()
        db.init_db()

        self.wms_db_path = Path(self.temp_dir.name) / 'wms.db'
        with sqlite3.connect(self.wms_db_path) as con:
            con.execute(
                '''CREATE TABLE inventory(
                       id INTEGER PRIMARY KEY AUTOINCREMENT, company TEXT, product_name TEXT,
                       warehouse_name TEXT, lot TEXT, exp_date TEXT, location TEXT,
                       qty INTEGER, updated_at TEXT, is_shippable INTEGER
                   )'''
            )
            con.execute(
                '''CREATE TABLE transactions(
                       id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT, actor TEXT,
                       tx_type TEXT, product_name TEXT, warehouse_name TEXT, lot TEXT,
                       exp_date TEXT, from_company TEXT, from_location TEXT,
                       to_company TEXT, to_location TEXT, qty INTEGER, memo TEXT,
                       final_stock INTEGER
                   )'''
            )
            export_waiting_service.ensure_export_waiting_tables(con.cursor())
            con.commit()
        self.wms_connect_patcher = patch(
            'nohtus.export_app.services.stale_inventory_cleanup_service.wms_connect',
            lambda: sqlite3.connect(self.wms_db_path),
        )
        self.wms_connect_patcher.start()

    def tearDown(self) -> None:
        self.wms_connect_patcher.stop()
        self.backup_patch.stop()
        db.DB_PATH = self.original_db_path
        db.UPLOAD_DIR = self.original_upload_dir
        db._initialize_database_runtime.cache_clear()
        db.init_db.cache_clear()
        self.temp_dir.cleanup()

    def test_signature_match_keeps_qty_when_shipment_and_waiting_ids_diverge(self) -> None:
        now = now_text()
        case_id = db.execute(
            '''INSERT INTO export_cases(
                   export_no,country,stage,status,created_at,updated_at,case_type
               ) VALUES (?,?,?,?,?,?,?)''',
            ('EXP-SIG-1', 'KR', '주문 접수', '진행중', now, now, 'current'),
        )
        order_id = db.execute(
            '''INSERT INTO order_items(case_id,product_name,quantity,unit,created_at)
               VALUES (?,?,?,?,?)''',
            (case_id, '오메가 PDT 장비', 5, 'EA', now),
        )
        # EXPORT 미러: 5EA가 inventory id=999(예: 박스 분할로 갈라진 뒤 남은
        # 값, 또는 픽 당시의 원본 id)로 저장돼 있다.
        db.execute(
            '''INSERT INTO shipment_items(
                   case_id,order_item_id,business_unit,location,source_inventory_id,
                   product_name,lot_no,expiry_date,requested_qty,box_no,created_at,updated_at
               ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
            (case_id, order_id, 'NOH', 'T4', 999, '오메가 PDT 장비', 'LOT1', '2027-01-01', 5, None, now, now),
        )

        with sqlite3.connect(self.wms_db_path) as con:
            wms_now = now_text()
            cur = con.execute(
                '''INSERT INTO export_waiting_orders(
                       export_no,country,buyer,transport_method,title,status,created_at,updated_at
                   ) VALUES (?,?,?,?,?,?,?,?)''',
                ('EXP-SIG-1', 'KR', 'Buyer', '항공', 'KR-Buyer-항공', 'waiting', wms_now, wms_now),
            )
            wms_order_id = int(cur.lastrowid)
            # WMS 쪽은 실제로는 같은 재고(같은 사업장/제품명/LOT/유통기한)지만
            # _take_source의 대체 매칭으로 다른 id(1234)로 기록돼 있다 - 두
            # 테이블의 id가 갈라진 상태를 재현한다.
            con.execute(
                '''INSERT INTO export_waiting_items(
                       order_id,source_inventory_id,waiting_inventory_id,company,product_name,
                       warehouse_name,lot,exp_date,source_location,waiting_location,qty,moved_at,confirmed
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (wms_order_id, 1234, None, 'NOH', '오메가 PDT 장비', '', 'LOT1', '2027-01-01', 'T4', 'P', 5, wms_now, 0),
            )
            con.commit()

        removed = stale_inventory_cleanup_service.reconcile_orphan_waiting_items('EXP-SIG-1')

        # id가 갈라져 있어도 (사업장,제품명,LOT,유통기한) 재고키가 같으므로
        # 아무것도 제거되면 안 된다 - 이 값이 5(전량 삭제)가 되면 리포트된
        # 버그가 재현된다.
        self.assertEqual(removed, 0)
        with sqlite3.connect(self.wms_db_path) as con:
            qty = con.execute(
                "SELECT qty FROM export_waiting_items WHERE order_id=? AND product_name=?",
                (wms_order_id, '오메가 PDT 장비'),
            ).fetchone()
        self.assertIsNotNone(qty)
        self.assertEqual(qty[0], 5)


if __name__ == '__main__':
    unittest.main()
