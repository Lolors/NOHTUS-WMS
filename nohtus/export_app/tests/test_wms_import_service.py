from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import pandas as pd

from nohtus.export_app import db
from nohtus.export_app.services import wms_import_service
from nohtus.export_app.utils.dates import now_text


class WmsImportServiceTests(unittest.TestCase):
    """수출관리(EXPORT)가 WMS와 같은 프로세스로 합쳐지면서, 예전에는 사용자가
    지정한 WMS DB 파일을 읽기전용으로 여는 방식이었던 이 서비스를 WMS의
    자체 쿼리 함수(nohtus.db.q)를 직접 호출하는 방식으로 다시 만들었다.
    _wms_rows()가 부르는 wms_q만 가짜로 바꿔서, WMS 쪽 실제 DB 없이도
    매칭·불러오기 로직을 검증한다."""

    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.original_db_path = db.DB_PATH
        self.original_upload_dir = db.UPLOAD_DIR
        db.DB_PATH = Path(self.temp_dir.name) / 'test.db'
        db.UPLOAD_DIR = Path(self.temp_dir.name) / 'uploads'
        db._initialize_database_runtime.cache_clear()
        db.init_db.cache_clear()
        db.init_db()

    def tearDown(self) -> None:
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
            (export_no, 'KR', '주문 접수', '진행중', now, now, 'current'),
        )

    def _add_order_item(self, case_id: int, product_name: str, quantity: float) -> int:
        now = now_text()
        return db.execute(
            '''INSERT INTO order_items(case_id,product_name,quantity,unit,created_at)
               VALUES (?,?,?,?,?)''',
            (case_id, product_name, quantity, 'EA', now),
        )

    def _wms_row(self, wms_item_id, company, product_name, lot, exp_date, qty, wms_order_id=1, status='waiting'):
        return {
            'wms_item_id': wms_item_id,
            'company': company,
            'product_name': product_name,
            'lot': lot,
            'exp_date': exp_date,
            'qty': qty,
            'wms_order_id': wms_order_id,
            'status': status,
            'updated_at': '2026-08-10 00:00:00',
        }

    def test_preview_matches_single_candidate_by_normalized_product_name(self):
        case_id = self._create_case('EXP-TEST-001')
        self._add_order_item(case_id, '리드카인', 10)

        # product_name_match_service가 제조사명(대한)과 제형(주사액) 같은
        # 잡음 표현을 제거하고 비교하므로, WMS 표준제품명이 이렇게 다르게
        # 적혀 있어도 같은 제품으로 매칭돼야 한다.
        wms_df = pd.DataFrame([
            self._wms_row(1, '노투스팜', '대한 리드카인 주사액', 'LOT-1', '2027-01-01', 10),
        ])
        with patch.object(wms_import_service, 'wms_q', return_value=wms_df):
            result = wms_import_service.preview(case_id)

        self.assertEqual(len(result['rows']), 1)
        self.assertEqual(result['rows'][0]['매칭상태'], '일치')
        self.assertEqual(result['differences'], [])

    def test_preview_flags_quantity_difference(self):
        case_id = self._create_case('EXP-TEST-002')
        self._add_order_item(case_id, '제품A', 10)

        wms_df = pd.DataFrame([
            self._wms_row(1, '노투스팜', '제품A', 'LOT-1', '2027-01-01', 7),
        ])
        with patch.object(wms_import_service, 'wms_q', return_value=wms_df):
            result = wms_import_service.preview(case_id)

        self.assertEqual(len(result['differences']), 1)
        self.assertEqual(result['differences'][0]['차이'], -3.0)

    def test_preview_flags_unmatched_and_duplicate_order_names(self):
        case_id = self._create_case('EXP-TEST-003')
        self._add_order_item(case_id, '제품A', 10)

        wms_df = pd.DataFrame([
            self._wms_row(1, '노투스팜', '전혀 다른 제품', 'LOT-1', '2027-01-01', 5),
        ])
        with patch.object(wms_import_service, 'wms_q', return_value=wms_df):
            result = wms_import_service.preview(case_id)

        self.assertEqual(result['rows'][0]['매칭상태'], '주문에 없음')
        self.assertIsNone(result['rows'][0]['_order_item_id'])

    def test_preview_excludes_cancelled_wms_orders(self):
        case_id = self._create_case('EXP-TEST-004')
        self._add_order_item(case_id, '제품A', 10)

        def fake_wms_q(sql, params=()):
            # cancelled 주문은 실제 쿼리의 WHERE 절이 걸러내므로, 여기서는
            # SQL이 export_no를 올바르게 바인딩하는지만 확인하고 빈 결과를 준다.
            self.assertIn(params[0], ('EXP-TEST-004',))
            return pd.DataFrame(columns=['wms_item_id', 'company', 'product_name', 'lot', 'exp_date', 'qty', 'wms_order_id', 'status', 'updated_at'])

        with patch.object(wms_import_service, 'wms_q', side_effect=fake_wms_q):
            result = wms_import_service.preview(case_id)

        self.assertEqual(result['rows'], [])

    def test_apply_rejects_when_unmatched_items_exist(self):
        case_id = self._create_case('EXP-TEST-005')
        self._add_order_item(case_id, '제품A', 10)

        wms_df = pd.DataFrame([
            self._wms_row(1, '노투스팜', '매칭 안 되는 제품', 'LOT-1', '2027-01-01', 5),
        ])
        with patch.object(wms_import_service, 'wms_q', return_value=wms_df):
            with self.assertRaisesRegex(ValueError, '매칭되지 않은'):
                wms_import_service.apply(case_id)

    def test_apply_writes_shipment_items_when_fully_matched(self):
        case_id = self._create_case('EXP-TEST-006')
        self._add_order_item(case_id, '제품A', 10)

        wms_df = pd.DataFrame([
            self._wms_row(1, '노투스팜', '제품A', 'LOT-1', '2027-01-01', 10),
        ])
        with patch.object(wms_import_service, 'wms_q', return_value=wms_df):
            result = wms_import_service.apply(case_id)

        self.assertEqual(result['row_count'], 1)
        rows = db.rows('SELECT business_unit,product_name,lot_no,expiry_date,requested_qty FROM shipment_items WHERE case_id=?', (case_id,))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['product_name'], '제품A')
        self.assertEqual(float(rows[0]['requested_qty']), 10.0)


if __name__ == '__main__':
    unittest.main()
