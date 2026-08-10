import ast
import unittest
from pathlib import Path


APPLICATION_PATH = Path(__file__).parents[1] / "nohtus" / "application.py"


class ApplicationOutboundEntrypointTests(unittest.TestCase):
    def test_native_widgets_are_captured_before_page_imports(self):
        tree = ast.parse(APPLICATION_PATH.read_text(encoding="utf-8"))
        capture_index = next(
            idx
            for idx, node in enumerate(tree.body)
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "_OUTBOUND_NATIVE_WIDGETS"
                for target in node.targets
            )
        )
        outbound_import_index = next(
            idx
            for idx, node in enumerate(tree.body)
            if isinstance(node, ast.ImportFrom)
            and node.module == "nohtus.pages.outbound_date_fix"
        )
        self.assertLess(capture_index, outbound_import_index)

    def test_outbound_entrypoint_restores_native_widgets_and_clears_export_mode(self):
        tree = ast.parse(APPLICATION_PATH.read_text(encoding="utf-8"))
        page = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "page_outbound"
        )
        source = ast.unparse(page)
        self.assertIn("st.session_state.pop('_outbound_screen_mode', None)", source)
        self.assertIn("for name, widget in _OUTBOUND_NATIVE_WIDGETS.items()", source)
        self.assertIn("setattr(st, name, widget)", source)
        self.assertIn("return _page_outbound()", source)
        self.assertIn("for name, widget in previous_widgets.items()", source)


if __name__ == "__main__":
    unittest.main()
