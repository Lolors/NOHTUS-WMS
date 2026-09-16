import unittest
from unittest.mock import patch

import streamlit as st

import nohtus.pages.outbound as outbound_page
import nohtus.pages.outbound_business as outbound_business
import nohtus.streamlit_patch_lock as patch_lock_module
from nohtus.streamlit_patch_lock import current, patched


class OutboundBusinessPatchRestoreTests(unittest.TestCase):
    """일반 출고지시 화면은 st.markdown/caption/text_input/checkbox/data_editor
    5개와 outbound_page의 3개 헬퍼 함수를 임시로 바꾼다. 이 지점은 2026-08-10에
    실제로 수출대기 patch가 새어 나가 거래처 검색창이 사라지는 회귀가 발생했던
    곳이라, 정상/예외 경로 복원과 export_waiting 모드 분기를 모두 검증한다."""

    def setUp(self):
        st.session_state.pop("_outbound_screen_mode", None)
        self._orig_renderer = current(outbound_page, "_render_last_sale_importer")
        self._orig_save_with_customer = current(outbound_page, "_save_outbound_cart_with_customer")
        self._orig_inventory_query = current(outbound_page, "_inventory_query_for_outbound")
        self._orig_markdown = current(st, "markdown")
        self._orig_caption = current(st, "caption")
        self._orig_text_input = current(st, "text_input")
        self._orig_checkbox = current(st, "checkbox")
        self._orig_data_editor = current(st, "data_editor")

    def tearDown(self):
        st.session_state.pop("_outbound_screen_mode", None)

    def _assert_all_patches_restored(self):
        self.assertIs(current(outbound_page, "_render_last_sale_importer"), self._orig_renderer)
        self.assertIs(current(outbound_page, "_save_outbound_cart_with_customer"), self._orig_save_with_customer)
        self.assertIs(current(outbound_page, "_inventory_query_for_outbound"), self._orig_inventory_query)
        self.assertIs(current(st, "markdown"), self._orig_markdown)
        self.assertIs(current(st, "caption"), self._orig_caption)
        self.assertIs(current(st, "text_input"), self._orig_text_input)
        self.assertIs(current(st, "checkbox"), self._orig_checkbox)
        self.assertIs(current(st, "data_editor"), self._orig_data_editor)

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
            captured["text_input"] = current(st, "text_input")
            captured["markdown"] = current(st, "markdown")
            captured["checkbox"] = current(st, "checkbox")
            captured["data_editor"] = current(st, "data_editor")
            captured["caption"] = current(st, "caption")
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
        """2026-08-10 회귀 재현: 수출대기 patch가 이미 걸려 있는 상태(previous)에서
        일반 출고지시가 열리면, 렌더링은 항상 원본(true_original) 위젯을 써야 하고
        previous(수출대기용 패치)로 새면 안 된다. 끝난 뒤에는 (원본이 아니라) 진입
        당시 걸려 있던 previous 위젯으로 되돌아가야 한다."""

        def fake_export_waiting_text_input(label, *args, **kwargs):
            return "should-not-leak"

        base_calls = []

        def fake_base_text_input(label, *args, **kwargs):
            base_calls.append(label)
            return "from-base"

        st.session_state["_outbound_screen_mode"] = "export_waiting"

        def call_through_patched_text_input():
            # st.text_input은 이제 outbound_business의 patched_text_input이다.
            # key가 없는 일반 호출은 곧바로 original_text_input(=true_original)으로 위임된다.
            result = st.text_input("아무 라벨")
            self.assertEqual(result, "from-base")
            return "rendered"

        # true_original(st, "text_input")이 캐싱해 둔 "진짜 원본"을 테스트 동안만
        # 가짜 함수로 바꿔서, is_export_waiting 분기가 실제로 true_original을
        # 참조하는지 확인한다.
        patch_lock_module._install(st, "text_input")
        true_original_key = (id(st), "text_input")

        with patch.dict(patch_lock_module._TRUE_ORIGINALS, {true_original_key: fake_base_text_input}):
            # 바깥쪽(export_waiting 화면)이 이미 걸어둔 patch를 흉내낸다.
            with patched({(st, "text_input"): fake_export_waiting_text_input}):
                with patch.object(outbound_page, "page_outbound", side_effect=call_through_patched_text_input):
                    outbound_business.page_outbound()
                # 안쪽 렌더링이 끝난 뒤에도 바깥쪽 patch는 그대로 살아있어야 한다(새지 않음).
                self.assertIs(current(st, "text_input"), fake_export_waiting_text_input)

        self.assertEqual(base_calls, ["아무 라벨"])


if __name__ == "__main__":
    unittest.main()
