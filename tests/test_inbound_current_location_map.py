import unittest
from pathlib import Path

import inbound_map


class InboundCurrentLocationMapTests(unittest.TestCase):
    def test_inbound_uses_approved_map_and_direct_component_event(self):
        self.assertIn('data-loc="A1-01"', inbound_map._COMPONENT_HTML)
        self.assertIn('data-special-loc="오른쪽 창고"', inbound_map._COMPONENT_HTML)
        self.assertIn('data-special-loc="지엠메딕"', inbound_map._COMPONENT_HTML)
        self.assertIn("setStateValue('selection', {location: loc, eventId: Date.now()})", inbound_map._COMPONENT_JS)
        self.assertIn("transform:scale(.627,.596)!important", inbound_map._COMPONENT_CSS)

        source = Path(inbound_map.__file__).read_text(encoding="utf-8")
        self.assertIn("components_v2.component", source)
        self.assertIn('st.session_state["_pending_inbound_loc"] = clicked', source)
        self.assertNotIn("tryParentInbound", source)
        self.assertNotIn("__입고도면선택값", source)


if __name__ == "__main__":
    unittest.main()
