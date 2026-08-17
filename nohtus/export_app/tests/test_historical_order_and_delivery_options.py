import unittest
from pathlib import Path

from nohtus.export_app.components.delivery_method_input import COURIER_OPTIONS


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


if __name__ == '__main__':
    unittest.main()
