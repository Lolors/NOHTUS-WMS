import unittest
from pathlib import Path
from unittest.mock import patch

import streamlit as st

import nohtus.pages.location_map as location_map_page
import nohtus.pages.location_map_business as location_map_business
from nohtus.streamlit_patch_lock import current


class LocationMapPatchRestoreTests(unittest.TestCase):
    def test_map_page_reduces_main_content_top_padding(self):
        source = Path(location_map_business.__file__).read_text(encoding="utf-8")
        self.assertIn('[data-testid="stMainBlockContainer"]', source)
        self.assertIn('padding-top: 1rem !important;', source)

    def test_search_filter_columns_use_balanced_real_widths(self):
        source = Path(location_map_business.__file__).read_text(encoding="utf-8")
        self.assertIn('st.columns([4.6, 2.55, 2.85], gap="small")', source)
        self.assertNotIn('st.columns([4.6, 2.95, 2.45], gap="small")', source)

    def test_search_filters_are_not_shifted_outside_their_columns(self):
        source = Path(location_map_business.__file__).read_text(encoding="utf-8")
        self.assertNotIn("map-materials-filter-anchor", source)
        self.assertNotIn("transform: translateX(-3rem);", source)

    def test_map_page_hides_stray_caret_but_keeps_input_caret(self):
        source = Path(location_map_business.__file__).read_text(encoding="utf-8")
        self.assertIn("#wms-top-anchor", source)
        self.assertIn("caret-color: transparent !important;", source)
        self.assertIn('[data-testid="stMain"] input', source)
        self.assertIn("caret-color: auto !important;", source)

    """로케이션맵 화면은 st.text_input/st.button 등을 이 스레드(세션)에만 보이는
    patch로 임시 교체한 뒤 _page_map() 실행 후 복원한다(nohtus.streamlit_patch_lock).
    `current(owner, attr)`가 "이 스레드 기준으로 지금 유효한 함수"를 돌려주므로,
    렌더링 전/후에는 patch 이전 값과 같아야 하고 렌더링 중에는 달라야 한다."""

    def setUp(self):
        self._orig_text_input = current(st, "text_input")
        self._orig_button = current(st, "button")
        self._orig_search_results = current(location_map_page, "page_map_search_results")
        self._orig_product_groups = current(location_map_page, "_map_search_product_groups")

    def _assert_all_patches_restored(self):
        self.assertIs(current(st, "text_input"), self._orig_text_input)
        self.assertIs(current(st, "button"), self._orig_button)
        self.assertIs(current(location_map_page, "page_map_search_results"), self._orig_search_results)
        self.assertIs(current(location_map_page, "_map_search_product_groups"), self._orig_product_groups)

    def test_restores_global_widgets_after_successful_render(self):
        with patch.object(location_map_business, "_page_map", return_value=None) as mock_render:
            location_map_business.page_map()

        mock_render.assert_called_once()
        self._assert_all_patches_restored()

    def test_restores_global_widgets_when_render_raises(self):
        with patch.object(location_map_business, "_page_map", side_effect=RuntimeError("boom")):
            with self.assertRaisesRegex(RuntimeError, "boom"):
                location_map_business.page_map()

        self._assert_all_patches_restored()

    def test_widgets_are_patched_only_during_render(self):
        captured = {}

        def capture_widgets():
            captured["text_input_during_render"] = current(st, "text_input")
            captured["button_during_render"] = current(st, "button")

        with patch.object(location_map_business, "_page_map", side_effect=capture_widgets):
            location_map_business.page_map()

        self.assertNotEqual(captured["text_input_during_render"], self._orig_text_input)
        self.assertNotEqual(captured["button_during_render"], self._orig_button)
        self._assert_all_patches_restored()


if __name__ == "__main__":
    unittest.main()
