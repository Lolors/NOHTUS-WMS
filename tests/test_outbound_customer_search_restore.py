import ast
import unittest
from pathlib import Path


PAGE_PATH = Path(__file__).parents[1] / "nohtus" / "pages" / "outbound_business.py"


class OutboundCustomerSearchRestoreTests(unittest.TestCase):
    def test_regular_outbound_uses_widgets_available_at_screen_entry(self):
        tree = ast.parse(PAGE_PATH.read_text(encoding="utf-8"))
        page = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "page_outbound"
        )
        assignments = {
            target.id: ast.unparse(node.value)
            for node in ast.walk(page)
            if isinstance(node, ast.Assign)
            for target in node.targets
            if isinstance(target, ast.Name)
            and target.id in {
                "original_text_input",
                "original_checkbox",
                "original_data_editor",
                "original_markdown",
                "original_caption",
            }
        }

        self.assertEqual(
            assignments["original_text_input"],
            "_BASE_TEXT_INPUT if is_export_waiting else previous_text_input",
        )
        self.assertEqual(
            assignments["original_checkbox"],
            "_BASE_CHECKBOX if is_export_waiting else previous_checkbox",
        )
        self.assertEqual(
            assignments["original_data_editor"],
            "_BASE_DATA_EDITOR if is_export_waiting else previous_data_editor",
        )
        self.assertEqual(
            assignments["original_markdown"],
            "_BASE_MARKDOWN if is_export_waiting else previous_markdown",
        )
        self.assertEqual(
            assignments["original_caption"],
            "_BASE_CAPTION if is_export_waiting else previous_caption",
        )


if __name__ == "__main__":
    unittest.main()
