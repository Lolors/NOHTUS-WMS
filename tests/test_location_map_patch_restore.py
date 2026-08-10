import unittest
from unittest.mock import patch

import streamlit as st

import nohtus.pages.location_map as location_map_page
import nohtus.pages.location_map_business as location_map_business


class LocationMapPatchRestoreTests(unittest.TestCase):
    """로케이션맵 화면은 st.text_input/st.button/st.markdown을 전역으로 임시
    교체한 뒤 _page_map() 실행 후 복원한다. 이 patch가 전역 위젯을 바꾸는
    만큼, 새면 로케이션맵 이후 화면 전체의 입력/버튼/마크다운이 깨진다."""

    def setUp(self):
        self._orig_text_input = st.text_input
        self._orig_button = st.button
        self._orig_markdown = st.markdown
        self._orig_search_results = location_map_page.page_map_search_results
        self._orig_product_groups = location_map_page._map_search_product_groups

    def tearDown(self):
        st.text_input = self._orig_text_input
        st.button = self._orig_button
        st.markdown = self._orig_markdown
        location_map_page.page_map_search_results = self._orig_search_results
        location_map_page._map_search_product_groups = self._orig_product_groups

    def _assert_all_patches_restored(self):
        self.assertIs(st.text_input, self._orig_text_input)
        self.assertIs(st.button, self._orig_button)
        self.assertIs(st.markdown, self._orig_markdown)
        self.assertIs(location_map_page.page_map_search_results, self._orig_search_results)
        self.assertIs(location_map_page._map_search_product_groups, self._orig_product_groups)

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
            captured["text_input_during_render"] = st.text_input
            captured["button_during_render"] = st.button
            captured["markdown_during_render"] = st.markdown

        with patch.object(location_map_business, "_page_map", side_effect=capture_widgets):
            location_map_business.page_map()

        self.assertNotEqual(captured["text_input_during_render"], self._orig_text_input)
        self.assertNotEqual(captured["button_during_render"], self._orig_button)
        self.assertNotEqual(captured["markdown_during_render"], self._orig_markdown)
        self._assert_all_patches_restored()


if __name__ == "__main__":
    unittest.main()
