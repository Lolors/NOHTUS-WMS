from __future__ import annotations

import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from nohtus.export_app import db
from nohtus.export_app.services import export_service
from nohtus.export_app.utils.dates import now_text
from nohtus.services import export_waiting as export_waiting_service


class ReturnDomesticToPackingCompleteGuardTests(unittest.TestCase):
    """국내배송 단계를 패킹완료로 되돌릴 때, WMS 쪽에 실제로 원복할 확정
    재고를 찾지 못하면 단계만 앞서 진행시키지 말고 명확히 알려야 한다.

    실사용 버그: return_confirmed_export_to_waiting이 되돌릴 대상을 못
    찾으면 조용히 0을 반환하는데, 호출부가 그 결과를 무시하고 무조건
    export_cases.stage를 '패킹 완료'로 바꿔버렸다. 그래서 실제로는 확정된
    WMS 재고(이력 조회엔 이미 출고된 것으로 남아 있는)가 하나도 원복되지
    않았는데, 겉보기엔 '되돌리기 성공'으로 보이는 사고가 났다."""

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
        self.wms_connect_patcher = patch.object(
            export_waiting_service, 'connect', lambda: sqlite3.connect(self.wms_db_path)
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

    def _create_case(self, export_no: str) -> int:
        now = now_text()
        return db.execute(
            '''INSERT INTO export_cases(
                   export_no,country,stage,status,created_at,updated_at,case_type
               ) VALUES (?,?,?,?,?,?,?)''',
            (export_no, 'KR', '국내배송', '완료', now, now, 'current'),
        )

    def test_raises_when_wms_has_nothing_to_restore(self) -> None:
        case_id = self._create_case('EXP-DOM-1')
        # WMS 쪽에 이 수출번호에 해당하는 확정 건이 전혀 없다(데이터가
        # 어긋난 상태를 재현) - 되돌리기가 조용히 성공한 것처럼 보이면 안
        # 된다.

        with self.assertRaises(ValueError):
            export_service.return_domestic_to_packing_complete(case_id)

        case = db.row('SELECT stage,status FROM export_cases WHERE id=?', (case_id,))
        self.assertEqual(case['stage'], '국내배송')
        self.assertEqual(case['status'], '완료')

    def test_succeeds_when_wms_has_confirmed_stock_to_restore(self) -> None:
        case_id = self._create_case('EXP-DOM-2')
        now = now_text()
        with sqlite3.connect(self.wms_db_path) as con:
            cur = con.execute(
                '''INSERT INTO export_waiting_orders(
                       export_no,country,buyer,transport_method,title,status,created_at,updated_at
                   ) VALUES (?,?,?,?,?,?,?,?)''',
                ('EXP-DOM-2', 'KR', 'Buyer', '항공', 'KR-Buyer-항공', 'confirmed', now, now),
            )
            order_id = int(cur.lastrowid)
            con.execute(
                '''INSERT INTO export_waiting_items(
                       order_id,source_inventory_id,waiting_inventory_id,company,product_name,
                       warehouse_name,lot,exp_date,source_location,waiting_location,qty,moved_at,
                       confirmed,confirmed_company,confirmed_customer_code,confirmed_customer_name,confirmed_at
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,1,?,?,?,?)''',
                (
                    order_id, 1, None, 'NOH', '제품', '', 'LOT1', '2027-01-01',
                    'T4', 'P', 5, now, 'NOH', 'C1', '매출처', now,
                ),
            )
            con.commit()

        export_service.return_domestic_to_packing_complete(case_id)

        case = db.row('SELECT stage,status FROM export_cases WHERE id=?', (case_id,))
        self.assertEqual(case['stage'], '패킹 완료')


if __name__ == '__main__':
    unittest.main()
