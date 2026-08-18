import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from nohtus.export_app.components.delivery_method_input import COURIER_OPTIONS
from nohtus.export_app.components.editors import historical_order_editor


class HistoricalOrderAndDeliveryOptionTests(unittest.TestCase):
    def test_dhl_is_available_as_a_courier(self):
        self.assertIn('DHL', COURIER_OPTIONS)

    def test_historical_blank_row_does_not_require_product_before_cell_edit(self):
        source = Path('nohtus/export_app/components/editors.py').read_text(encoding='utf-8')
        start = source.index('def historical_order_editor')
        end = source.index('def historical_box_editor', start)
        historical_editor = source[start:end]
        self.assertIn("'제품명': st.column_config.TextColumn('제품명')", historical_editor)
        self.assertNotIn("TextColumn('제품명', required=True)", historical_editor)

    def test_historical_text_columns_are_forced_to_string_dtype(self):
        source = pd.DataFrame([{
            '출고처': None, '제품명': '', '제조번호': None, '유효기간': None,
            '수량': 1.0, '단위': 'EA', '매입가': 0.0, 'CTN 번호': 1,
        }])
        with patch('nohtus.export_app.components.editors.st.data_editor', side_effect=lambda frame, **_: frame):
            edited = historical_order_editor(source, key='test-editor')

        for column in ('출고처', '제품명', '제조번호', '유효기간'):
            self.assertEqual(str(edited[column].dtype), 'string')
            self.assertEqual(edited.at[0, column], '')

    def test_no_domestic_info_keeps_document_attachments_available(self):
        source = Path('nohtus/export_app/views/수출_주문_입력_및_수정.py').read_text(encoding='utf-8')
        checkbox = source.index("'정보없음'")
        attachments = source.index('historical_attachment_uploads(form_widget_key)', checkbox)
        self.assertGreater(attachments, checkbox)
        self.assertIn("delivery_method = '정보없음'", source[checkbox:attachments])


if __name__ == '__main__':
    unittest.main()
