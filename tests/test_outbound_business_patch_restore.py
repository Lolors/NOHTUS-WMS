import unittest
from unittest.mock import patch

import streamlit as st

import nohtus.pages.outbound as outbound_page
import nohtus.pages.outbound_business as outbound_business


class OutboundBusinessPatchRestoreTests(unittest.TestCase):
    """일반 출고지시 화면은 st.markdown/caption/text_input/checkbox/data_editor
    5개와 outbound_page의 3개 헬퍼 함수를 임시로 바꾼다. 이 지점은 2026-08-10에
    실제로 수출대기 patch가 새어 나가 거래처 검색창이 사라지는 회귀가 발생했던
    곳이라, 정상/예외 경로 복원과 export_waiting 모드 분기를 모두 검증한다."""

    def setUp(self):
        st.session_state.pop("_outbound_screen_mode", None)
        self._orig_renderer = outbound_page._render_last_sale_importer
        self._orig_save_with_customer = outbound_page._save_outbound_cart_with_customer
        self._orig_inventory_query = outbound_page._inventory_query_for_outbound
        self._orig_manual_pick_rows = outbound_page._manual_pick_rows
        self._orig_markdown = st.markdown
        self._orig_caption = st.caption
        self._orig_text_input = st.text_input
        self._orig_checkbox = st.checkbox
        self._orig_data_editor = st.data_editor

    def tearDown(self):
        st.session_state.pop("_outbound_screen_mode", None)
        outbound_page._render_last_sale_importer = self._orig_renderer
        outbound_page._save_outbound_cart_with_customer = self._orig_save_with_customer
        outbound_page._inventory_query_for_outbound = self._orig_inventory_query
        outbound_page._manual_pick_rows = self._orig_manual_pick_rows
        st.markdown = self._orig_markdown
        st.caption = self._orig_caption
        st.text_input = self._orig_text_input
        st.checkbox = self._orig_checkbox
        st.data_editor = self._orig_data_editor

    def _assert_all_patches_restored(self):
        self.assertIs(outbound_page._render_last_sale_importer, self._orig_renderer)
        self.assertIs(outbound_page._save_outbound_cart_with_customer, self._orig_save_with_customer)
        self.assertIs(outbound_page._inventory_query_for_outbound, self._orig_inventory_query)
        self.assertIs(outbound_page._manual_pick_rows, self._orig_manual_pick_rows)
        self.assertIs(st.markdown, self._orig_markdown)
        self.assertIs(st.caption, self._orig_caption)
        self.assertIs(st.text_input, self._orig_text_input)
        self.assertIs(st.checkbox, self._orig_checkbox)
        self.assertIs(st.data_editor, self._orig_data_editor)

    def test_restores_patches_after_successful_render(self):
        with patch.object(outbound_page, "page_outbound", return_value="rendered") as mock_render:
            result = outbound_business.page_outbound()

        mock_render.assert_called_once()
        self.assertEqual(result, "rendered")
        self._assert_all_patches_restored()

    def test_restores_patches_when_render_raises(self):
        with patch.object(outbound_page, "page_outbound", side_effect=RuntimeError("boom")):
            with self.assertRaisesRegex(RuntimeError, "boom"):
                outbound_business.page_outbound()

        self._assert_all_patches_restored()

    def test_widgets_are_patched_only_during_render(self):
        captured = {}

        def capture_widgets():
            captured["text_input"] = st.text_input
            captured["markdown"] = st.markdown
            captured["checkbox"] = st.checkbox
            captured["data_editor"] = st.data_editor
            captured["caption"] = st.caption
            return "rendered"

        with patch.object(outbound_page, "page_outbound", side_effect=capture_widgets):
            outbound_business.page_outbound()

        self.assertNotEqual(captured["text_input"], self._orig_text_input)
        self.assertNotEqual(captured["markdown"], self._orig_markdown)
        self.assertNotEqual(captured["checkbox"], self._orig_checkbox)
        self.assertNotEqual(captured["data_editor"], self._orig_data_editor)
        self.assertNotEqual(captured["caption"], self._orig_caption)
        self._assert_all_patches_restored()

    def test_export_waiting_mode_renders_with_base_widgets_but_restores_previous(self):
        """2026-08-10 회귀 재현: 수출대기 monkey patch가 이미 걸려 있는 상태(previous)에서
        일반 출고지시가 열리면, 렌더링은 항상 원본(BASE) 위젯을 써야 하고 previous(수출대기용
        패치)로 새면 안 된다. 끝난 뒤에는 (BASE가 아니라) 진입 당시 걸려 있던 previous 위젯으로
        되돌아가야 한다."""

        def fake_export_waiting_text_input(label, *args, **kwargs):
            return "should-not-leak"

        st.text_input = fake_export_waiting_text_input
        st.session_state["_outbound_screen_mode"] = "export_waiting"

        base_calls = []

        def fake_base_text_input(label, *args, **kwargs):
            base_calls.append(label)
            return "from-base"

        def call_through_patched_text_input():
            # st.text_input은 이제 outbound_business의 patched_text_input이다.
            # key가 없는 일반 호출은 곧바로 original_text_input으로 위임된다.
            result = st.text_input("아무 라벨")
            self.assertEqual(result, "from-base")
            return "rendered"

        with patch.object(outbound_business, "_BASE_TEXT_INPUT", fake_base_text_input):
            with patch.object(outbound_page, "page_outbound", side_effect=call_through_patched_text_input):
                outbound_business.page_outbound()

        self.assertEqual(base_calls, ["아무 라벨"])
        self.assertIs(st.text_input, fake_export_waiting_text_input)

        st.text_input = self._orig_text_input


if __name__ == "__main__":
    unittest.main()
