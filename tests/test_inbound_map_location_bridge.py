import types
import unittest
from unittest.mock import patch

import nohtus.services.inbound_bridge_runtime as bridge


class FakeStreamlit(types.SimpleNamespace):
    """입고 도면 클릭 브리지가 쓰는 st.session_state/st.query_params만 흉내낸다."""

    def __init__(self, session_state=None, query_params=None):
        super().__init__(session_state=dict(session_state or {}), query_params=dict(query_params or {}))


class InboundJsLocChangedTests(unittest.TestCase):
    """도면 iframe이 숨김 입력칸(_inbound_js_loc_buffer)에 써 넣은 값을
    _pending_inbound_loc으로 옮기는 첫 단계를 검증한다."""

    def test_buffer_value_becomes_pending_location(self):
        fake_st = FakeStreamlit(session_state={"_inbound_js_loc_buffer": "A1-01-02"})
        with patch.object(bridge, "st", fake_st):
            bridge._inbound_js_loc_changed()
        self.assertEqual(fake_st.session_state["_pending_inbound_loc"], "A1-01-02")

    def test_blank_buffer_does_not_set_pending_location(self):
        fake_st = FakeStreamlit(session_state={"_inbound_js_loc_buffer": "   "})
        with patch.object(bridge, "st", fake_st):
            bridge._inbound_js_loc_changed()
        self.assertNotIn("_pending_inbound_loc", fake_st.session_state)

    def test_blank_buffer_does_not_overwrite_existing_pending_location(self):
        fake_st = FakeStreamlit(session_state={
            "_inbound_js_loc_buffer": "",
            "_pending_inbound_loc": "B1-02",
        })
        with patch.object(bridge, "st", fake_st):
            bridge._inbound_js_loc_changed()
        self.assertEqual(fake_st.session_state["_pending_inbound_loc"], "B1-02")


class ApplyInboundLocationPendingTests(unittest.TestCase):
    """클릭된 위치가 실제로 입고 위치 콤보박스 기본값(area/line/level)과
    선택값으로 반영되는지, 그리고 소비된 pending 값이 남지 않는지 검증한다."""

    def test_full_location_is_parsed_into_area_line_level(self):
        fake_st = FakeStreamlit(session_state={"_pending_inbound_loc": "A1-01-02"})
        with patch.object(bridge, "st", fake_st):
            bridge._apply_inbound_location_pending()

        self.assertEqual(
            fake_st.session_state["_inbound_picker_defaults"],
            {"area": "A1", "line": "01", "level": "02"},
        )
        self.assertEqual(fake_st.session_state["_inbound_selected_loc"], "A1-01-02")
        self.assertEqual(fake_st.session_state["_inbound_picker_token"], 1)
        self.assertNotIn("_pending_inbound_loc", fake_st.session_state)

    def test_area_only_location_leaves_line_and_level_blank(self):
        fake_st = FakeStreamlit(session_state={"_pending_inbound_loc": "REC"})
        with patch.object(bridge, "st", fake_st):
            bridge._apply_inbound_location_pending()

        self.assertEqual(
            fake_st.session_state["_inbound_picker_defaults"],
            {"area": "REC", "line": "", "level": ""},
        )
        self.assertEqual(fake_st.session_state["_inbound_selected_loc"], "REC")

    def test_q_special_location_bypasses_area_line_level_parsing(self):
        for special in ("Q", "Q1", "Q2"):
            with self.subTest(special=special):
                fake_st = FakeStreamlit(session_state={"_pending_inbound_loc": special})
                with patch.object(bridge, "st", fake_st):
                    bridge._apply_inbound_location_pending()
                self.assertEqual(
                    fake_st.session_state["_inbound_picker_defaults"],
                    {"area": "Q", "line": "", "level": ""},
                )
                self.assertEqual(fake_st.session_state["_inbound_selected_loc"], "Q")

    def test_picker_token_increments_on_each_applied_click(self):
        fake_st = FakeStreamlit()
        with patch.object(bridge, "st", fake_st):
            fake_st.session_state["_pending_inbound_loc"] = "A1-01"
            bridge._apply_inbound_location_pending()
            self.assertEqual(fake_st.session_state["_inbound_picker_token"], 1)

            fake_st.session_state["_pending_inbound_loc"] = "B2-03"
            bridge._apply_inbound_location_pending()
            self.assertEqual(fake_st.session_state["_inbound_picker_token"], 2)

    def test_no_pending_location_and_no_query_param_is_a_no_op(self):
        fake_st = FakeStreamlit()
        with patch.object(bridge, "st", fake_st):
            bridge._apply_inbound_location_pending()
        self.assertEqual(fake_st.session_state, {})

    def test_falls_back_to_inbound_loc_query_param_when_no_session_pending(self):
        fake_st = FakeStreamlit(query_params={"inbound_loc": "B2-03"})
        with patch.object(bridge, "st", fake_st):
            bridge._apply_inbound_location_pending()

        self.assertEqual(
            fake_st.session_state["_inbound_picker_defaults"],
            {"area": "B2", "line": "03", "level": ""},
        )
        self.assertNotIn("inbound_loc", fake_st.query_params)

    def test_session_pending_takes_priority_over_query_param(self):
        fake_st = FakeStreamlit(
            session_state={"_pending_inbound_loc": "A1-01"},
            query_params={"inbound_loc": "C1-05"},
        )
        with patch.object(bridge, "st", fake_st):
            bridge._apply_inbound_location_pending()

        self.assertEqual(fake_st.session_state["_inbound_selected_loc"], "A1-01")
        self.assertEqual(fake_st.query_params.get("inbound_loc"), "C1-05")


if __name__ == "__main__":
    unittest.main()
