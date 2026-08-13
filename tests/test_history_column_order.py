from pathlib import Path
import ast
import unittest


class HistoryColumnOrderTests(unittest.TestCase):
    def test_user_column_is_last(self) -> None:
        source = Path("nohtus/pages/history.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        wanted = next(
            ast.literal_eval(node.value)
            for node in ast.walk(tree)
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "wanted" for target in node.targets)
            and isinstance(node.value, ast.List)
        )

        self.assertEqual(wanted[-1], "사용자")
