import unittest

from nohtus.config import AREA_CONFIG, SPECIAL_LOCATIONS
from nohtus.services.location_map_new_layout import _NEW_CSS, _map_markup


class LocationMapNewLayoutTests(unittest.TestCase):
    def test_canvas_is_cropped_without_outer_border_or_scrollbars(self):
        self.assertIn(".map-scroll{overflow:hidden!important", _NEW_CSS)
        self.assertIn("width:1482px!important;height:910px!important", _NEW_CSS)
        self.assertIn("border:0!important;border-radius:0!important", _NEW_CSS)

    def test_promo_rack_is_one_standalone_click_target(self):
        markup = _map_markup()
        self.assertEqual(markup.count('data-loc="홍보물랙"'), 1)
        self.assertIn('data-loc="홍보물랙" style="left:18px;top:830px;width:290px', markup)
        self.assertNotIn('data-special-loc="홍보물랙"', markup)
        self.assertNotIn("홍보물랙", SPECIAL_LOCATIONS)
        self.assertIn("홍보물랙", AREA_CONFIG)
        self.assertNotIn("홍보물랙", AREA_CONFIG["N"]["lines"])

    def test_labels_cell_size_and_open_refrigerator_lines(self):
        markup = _map_markup()
        self.assertIn("P<br>-수출대기-", markup)
        self.assertIn("Q<br>-유통기한임박-", markup)
        self.assertIn('left:650px;top:330px;width:83px;height:235px', markup)
        self.assertIn('border-width:0 0 0 1.5px', markup)
        self.assertIn('border-width:0 0 1.5px 0', markup)


if __name__ == "__main__":
    unittest.main()
