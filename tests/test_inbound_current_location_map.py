import unittest
from pathlib import Path

import inbound_map


class InboundCurrentLocationMapTests(unittest.TestCase):
    def test_inbound_uses_approved_map_and_direct_component_event(self):
        html, css = inbound_map._build_markup_and_css()
        js = inbound_map._build_component_js()
        self.assertIn('data-loc="A1-01"', html)
        self.assertIn('data-special-loc="오른쪽 창고"', html)
        self.assertIn('data-special-loc="지엠메딕"', html)
        # A monotonic per-click counter (not Date.now()) survives remounts and
        # guarantees each click gets a distinct, ordered id.
        self.assertIn(
            "setStateValue('selection', {location: loc, eventId: parentElement.__moveMapClickSeq, target: pickTarget})",
            js,
        )
        # 고정된 배율 대신, 카드 영역(가로+세로)에 맞춰 자동으로 축소하는 함수가 있어야 한다.
        self.assertIn("function fitMapToContainer()", js)
        self.assertNotIn("transform:scale(.627,.596)!important", css)

        source = Path(inbound_map.__file__).read_text(encoding="utf-8")
        self.assertIn("components_v2.component", source)
        self.assertIn('st.session_state["_pending_inbound_loc"] = clicked', source)
        self.assertNotIn("tryParentInbound", source)
        self.assertNotIn("__입고도면선택값", source)

    def test_inbound_map_reflects_saved_layout_not_hardcoded_default(self):
        """저장된 로케이션맵 레이아웃(에디터에서 편집한 값)을 그대로 반영해야 한다.
        메인 로케이션맵과 동일한 함수(_saved_layout_markup)를 사용하는지 확인한다."""
        from nohtus.services.location_map_layout import load_location_map_layout
        from nohtus.services.location_map_new_layout import _saved_layout_markup

        layout = load_location_map_layout()
        self.assertTrue(layout.get("items"), "테스트 전제: 저장된 레이아웃이 있어야 함")
        expected_markup = _saved_layout_markup(layout)
        html, _css = inbound_map._build_markup_and_css()
        self.assertIn(expected_markup, html)


if __name__ == "__main__":
    unittest.main()
