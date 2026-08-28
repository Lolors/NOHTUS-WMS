import unittest

from nohtus.config import AREA_CONFIG, SPECIAL_LOCATIONS
from nohtus.services.location_map_new_layout import _NEW_CSS, _map_markup, _saved_layout_markup


class LocationMapNewLayoutTests(unittest.TestCase):
    def test_canvas_is_cropped_without_outer_border_or_scrollbars(self):
        self.assertIn(".map-scroll{overflow:hidden!important", _NEW_CSS)
        self.assertIn("width:1482px!important;height:910px!important", _NEW_CSS)
        self.assertIn("border:0!important;border-radius:0!important", _NEW_CSS)

    def test_promo_rack_is_one_standalone_click_target(self):
        markup = _map_markup()
        self.assertEqual(markup.count('data-loc="다용도랙"'), 1)
        self.assertIn('data-loc="다용도랙" style="left:18px;top:830px;width:290px', markup)
        self.assertNotIn('data-special-loc="다용도랙"', markup)
        self.assertNotIn("다용도랙", SPECIAL_LOCATIONS)
        self.assertIn("다용도랙", AREA_CONFIG)
        self.assertNotIn("다용도랙", AREA_CONFIG["N"]["lines"])

    def test_gray_cart_is_not_an_n_location_or_map_menu_item(self):
        markup = _map_markup()
        self.assertNotIn("회색 카트", SPECIAL_LOCATIONS)
        self.assertNotIn("회색 카트", AREA_CONFIG["N"]["lines"])
        self.assertNotIn('data-special-loc="회색 카트"', markup)

    def test_labels_cell_size_and_open_refrigerator_lines(self):
        markup = _map_markup()
        self.assertIn("P<br>수출대기", markup)
        self.assertIn("Q<br>유통기한임박", markup)
        self.assertNotIn("-수출대기-", markup)
        self.assertNotIn("-유통기한임박-", markup)
        self.assertIn(".map-stage .export{color:#c2410c!important}", _NEW_CSS)
        self.assertIn(".map-stage .expiry{color:#dc2626!important}", _NEW_CSS)

    def test_special_location_menu_is_positioned_as_an_overlay(self):
        markup = _map_markup()
        self.assertIn('data-special-loc="지엠메딕"', markup)
        self.assertIn("position:absolute!important", _NEW_CSS)
        self.assertIn(".map-stage .special-menu.open{display:grid!important", _NEW_CSS)
        self.assertIn('left:650px;top:330px;width:83px;height:235px', markup)
        self.assertIn('left:930px;top:590px;width:330px;height:185px;border-right:0;border-bottom:0', markup)
        self.assertIn('left:1260px;top:590px;width:1px;height:110px;border-width:0 0 0 1.5px', markup)
        self.assertNotIn('top:775px;width:70px;height:1px', markup)
        self.assertNotIn('top:775px;width:110px;height:1px', markup)
        self.assertIn('border-width:0 0 1.5px 0', markup)
        self.assertIn('left:1418px;top:250px;width:64px;height:240px', markup)
        self.assertIn('left:1195px;top:335px;width:210px', markup)
        self.assertIn('z-index:12!important;isolation:isolate', _NEW_CSS)

    def test_partitioned_group_renders_as_one_rack_with_clickable_cells(self):
        items = []
        for order, code in enumerate(('A1-01', 'A1-02', 'A1-03')):
            items.append({
                'code': code, 'label': code, 'x': 100 + order * 60, 'y': 50,
                'width': 60, 'height': 50, 'company': '노투스팜',
                'group_id': 'rack-a1', 'group_style': 'partitioned',
                'group_axis': 'x', 'group_order': order, 'group_count': 3,
            })
        markup = _saved_layout_markup({'items': items, 'company_colors': {}})
        self.assertEqual(markup.count('partitioned-rack group-x'), 3)
        self.assertIn('partitioned-rack group-x group-first', markup)
        self.assertIn('partitioned-rack group-x group-last', markup)
        self.assertEqual(markup.count('data-loc="A1-0'), 3)
        self.assertIn('.partitioned-rack.group-x:not(.group-last){border-right:0}', _NEW_CSS)


if __name__ == "__main__":
    unittest.main()
