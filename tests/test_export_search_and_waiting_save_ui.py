from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

import pandas as pd

from nohtus.export_app.services import wms_inventory_picker_service
from nohtus.export_app.views.실출고_입력 import inventory_selection_source


class ExportSearchAndWaitingSaveUiTests(TestCase):
    def test_order_search_has_requested_filters_and_one_month_default(self):
        source = Path('nohtus/export_app/views/주문_검색_및_수정.py').read_text(encoding='utf-8')
        for label in ('기간', '국가', '바이어', '운송방식', '제품명 검색'):
            self.assertIn(f"'{label}'", source)
        self.assertIn('today-timedelta(days=30)', source)
        self.assertIn("buyer_filter!='전체'", source)
        self.assertIn("transport_filter!='전체'", source)

    def test_waiting_menu_and_copy_use_save_wording(self):
        navigation = Path('nohtus/navigation.py').read_text(encoding='utf-8')
        application = Path('nohtus/application.py').read_text(encoding='utf-8')
        view = Path('nohtus/export_app/views/실출고_입력.py').read_text(encoding='utf-8')
        self.assertIn('"수출대기 저장"', navigation)
        self.assertIn('menu == "수출대기 저장"', application)
        self.assertIn("st.title('수출대기 저장')", view)
        self.assertIn("'출고 저장'", view)
        self.assertNotIn('이미 연결된 실재고', view)
        self.assertNotIn('WMS 실재고에서 담기', view)
        self.assertNotIn('이 항목에 담기', view)
        self.assertNotIn('실재고 연결 저장', view)

    def test_existing_and_available_inventory_are_merged_in_one_selection_table(self):
        current = [{
            'source_inventory_id': 1,
            'source_location': 'A1',
            'product_name': '제품A',
            'business_unit': 'NOH',
            'lot_no': 'LOT-1',
            'expiry_date': '2027-01-01',
            'requested_qty': 3,
        }]
        stock = pd.DataFrame([
            {'id': 1, 'company': 'NOH', 'location': 'A1', 'product_name': '제품A', 'lot': 'LOT-1', 'exp_date': '2027-01-01', 'qty': 7},
            {'id': 2, 'company': '노투스', 'location': 'B1', 'product_name': '제품A', 'lot': 'LOT-2', 'exp_date': '2027-02-01', 'qty': 5},
        ])
        result = inventory_selection_source(current, stock)
        self.assertEqual(list(result[['선택', '사업장', '제조번호', '유통기한', '보유수량', '선택수량']].columns), [
            '선택', '사업장', '제조번호', '유통기한', '보유수량', '선택수량'
        ])
        existing = result[result['_inventory_id'] == 1].iloc[0]
        self.assertTrue(existing['선택'])
        self.assertEqual(existing['보유수량'], 10)
        self.assertEqual(existing['선택수량'], 3)

    def test_product_stock_rows_returns_all_lots_for_one_recommended_product(self):
        with patch.object(wms_inventory_picker_service, 'wms_q', return_value=pd.DataFrame()) as query:
            wms_inventory_picker_service.product_stock_rows('제품A')
        sql, params = query.call_args.args
        self.assertIn('product_name=?', sql)
        self.assertNotIn('lot=?', sql)
        self.assertNotIn('exp_date=?', sql)
        self.assertEqual(params, ('제품A',))
