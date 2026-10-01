import ast
import unittest
from pathlib import Path


APPLICATION_PATH = Path(__file__).parents[1] / "nohtus" / "pages" / "outbound_entry.py"


class ApplicationOutboundEntrypointTests(unittest.TestCase):
    """nohtus.streamlit_patch_lock 도입 전에는 이 진입점이 st.* 위젯 슬롯을
    직접 캡처/복구해서 "수출대기 patch가 일반 출고지시로 새는 것"을 막았다.
    지금은 patch가 스레드-로컬 스택으로 세션마다 격리되므로 그 방어가 필요
    없어졌을 뿐 아니라, st.* 슬롯을 여기서 다시 건드리면 오히려
    streamlit_patch_lock이 설치해 둔 디스패처를 지워버려 patch 자체가
    먹통이 되는 회귀를 낳는다(2026-09-16). 그래서 이 진입점은 화면 모드
    플래그 정리만 책임진다."""

    def test_page_outbound_only_clears_screen_mode_and_delegates(self):
        tree = ast.parse(APPLICATION_PATH.read_text(encoding="utf-8"))
        page = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "page_outbound"
        )
        source = ast.unparse(page)
        self.assertIn("st.session_state.pop('_outbound_screen_mode', None)", source)
        self.assertIn("return _page_outbound()", source)
        # st.* 위젯 슬롯을 직접 건드리던 예전 패턴이 되살아나지 않았는지 고정한다.
        self.assertNotIn("setattr(st,", source)
        self.assertNotIn("_OUTBOUND_NATIVE_WIDGETS", source)
        self.assertNotIn("_BASE_TEXT_INPUT", source)


if __name__ == "__main__":
    unittest.main()
