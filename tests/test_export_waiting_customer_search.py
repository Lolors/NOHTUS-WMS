import ast
import types
import unittest
from pathlib import Path


PAGE_PATH = Path(__file__).parents[1] / "nohtus" / "pages" / "export_waiting.py"


def _load_nested_function(name, namespace):
    tree = ast.parse(PAGE_PATH.read_text(encoding="utf-8"))
    function = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == name
    )
    module = ast.Module(body=[function], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, PAGE_PATH, "exec"), namespace)
    return namespace[name]


class ExportWaitingCustomerSearchTests(unittest.TestCase):
    def test_customer_query_is_enabled_only_while_editing(self):
        session_state = {}
        calls = []
        empty_result = object()
        query_result = object()
        namespace = {
            "st": types.SimpleNamespace(session_state=session_state),
            "pd": types.SimpleNamespace(DataFrame=lambda: empty_result),
            "original_q": lambda sql, params=(): calls.append((sql, params)) or query_result,
        }
        patched_q = _load_nested_function("patched_q", namespace)

        self.assertIs(patched_q("SELECT * FROM customers"), empty_result)
        self.assertEqual(calls, [])

        session_state["export_editing_order_id"] = 7
        self.assertIs(patched_q("SELECT * FROM customers"), query_result)
        self.assertEqual(calls, [("SELECT * FROM customers", ())])

    def test_customer_search_input_is_enabled_only_while_editing(self):
        session_state = {}
        calls = []
        namespace = {
            "st": types.SimpleNamespace(session_state=session_state),
            "original_text_input": lambda label, *args, **kwargs: calls.append(
                (label, args, kwargs)
            ) or "searched customer",
            "_export_title": lambda: "title",
        }
        patched_text_input = _load_nested_function("patched_text_input", namespace)

        self.assertEqual(
            patched_text_input("매출처 검색", key="out_customer_term"),
            "",
        )
        self.assertEqual(calls, [])

        session_state["export_editing_order_id"] = 7
        self.assertEqual(
            patched_text_input("매출처 검색", key="out_customer_term"),
            "searched customer",
        )
        self.assertEqual(calls[0][0], "매출처 검색")
        self.assertEqual(calls[0][2]["key"], "out_customer_term")


if __name__ == "__main__":
    unittest.main()
