import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nohtus import navigation
from nohtus.pages import location_map_editor
from nohtus.services import location_map_layout
from nohtus.services.location_map_layout_seed import initial_layout
from nohtus.services.location_map_new_layout import _NEW_CSS, _saved_layout_markup


class LocationMapEditorIntegrationTests(unittest.TestCase):
    def test_admin_menu_is_under_basic_section_and_shippable_menu_is_removed(self):
        basic = dict(navigation.MENU_SECTIONS)['기초']
        self.assertIn('로케이션맵 편집', basic)
        self.assertIn('로케이션맵 편집', navigation.ADMIN_ONLY_PAGES)
        self.assertNotIn('출고가능 관리', [label for _, labels in navigation.MENU_SECTIONS for label in labels])
        source = (Path(__file__).resolve().parents[1] / 'nohtus' / 'application.py').read_text(encoding='utf-8')
        self.assertIn('elif menu == "로케이션맵 편집":', source)
        self.assertIn('page_location_map_editor()', source)
        self.assertNotIn('page_shippable_inventory', source)
        self.assertNotIn('menu == "출고가능 관리"', source)

    def test_non_admin_cannot_see_or_directly_open_editor(self):
        with patch.object(navigation, 'is_admin', return_value=False):
            self.assertFalse(navigation._is_admin_only_allowed('로케이션맵 편집'))
        with (
            patch.object(location_map_editor, 'is_admin', return_value=False),
            patch.object(location_map_editor.st, 'warning') as warning,
            patch.object(location_map_editor.st, 'title') as title,
        ):
            location_map_editor.page_location_map_editor()
        warning.assert_called_once()
        title.assert_not_called()

    def test_seed_matches_latest_layout_and_c1_has_only_three_locations(self):
        layout = initial_layout()
        codes = {item['code'] for item in layout['items']}
        self.assertEqual(layout['canvas'], {'width': 1482, 'height': 910, 'grid': 10})
        self.assertEqual({code for code in codes if code.startswith('C1-')}, {'C1-01', 'C1-02', 'C1-03'})
        self.assertFalse({'C1-04', 'C1-05', 'C1-06'} & codes)

    def test_saved_json_generates_existing_click_targets_and_styles(self):
        layout = initial_layout()
        c1 = next(item for item in layout['items'] if item['code'] == 'C1-01')
        c1['x'] = 777
        markup = _saved_layout_markup(layout)
        self.assertIn('data-loc="C1-01"', markup)
        self.assertIn('left:777px', markup)
        self.assertIn('class="nw-zone zone farm"', markup)
        self.assertIn('.nw-zone.selected', _NEW_CSS)
        self.assertIn('.dynamic-stock-dot', _NEW_CSS)

    def test_layout_round_trip_keeps_rotation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / 'location_map_layout.json'
            with patch.object(location_map_layout, '_LAYOUT_PATH', path):
                layout = initial_layout()
                layout['items'][0]['rotation'] = 90
                location_map_layout.save_location_map_layout(layout)
                restored = location_map_layout.load_location_map_layout()
        self.assertEqual(restored['items'][0]['rotation'], 90)


if __name__ == '__main__':
    unittest.main()
