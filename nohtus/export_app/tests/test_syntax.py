from __future__ import annotations

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PythonSyntaxTests(unittest.TestCase):
    def test_all_python_files_parse(self) -> None:
        failures: list[str] = []
        for path in sorted(ROOT.rglob('*.py')):
            if any(part in {'.git', '.venv', 'venv'} for part in path.parts):
                continue
            try:
                ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
            except SyntaxError as exc:
                failures.append(f'{path.relative_to(ROOT)}:{exc.lineno}: {exc.msg}')
        self.assertEqual([], failures, '\n'.join(failures))

    def test_legacy_pages_directory_has_no_python_pages(self) -> None:
        pages_dir = ROOT / 'pages'
        legacy_pages = sorted(
            str(path.relative_to(ROOT))
            for path in pages_dir.rglob('*.py')
        ) if pages_dir.exists() else []
        self.assertEqual([], legacy_pages)

    def test_views_use_compatible_dialog_decorator(self) -> None:
        direct_dialogs = [
            str(path.relative_to(ROOT))
            for path in sorted((ROOT / 'views').glob('*.py'))
            if '@st.dialog(' in path.read_text(encoding='utf-8')
        ]
        self.assertEqual([], direct_dialogs)

    def test_calculation_logic_stays_out_of_views(self) -> None:
        forbidden_functions = {
            'find_product_name_mismatches',
            'intake_progress',
            'order_state',
            'product_name_similarity',
            'safe_number',
            'save_historical',
            'historical_items',
            'box_items',
            'quantity_text',
            'filter_and_sort_cases',
            'order_products_summary',
            'packing_summary',
        }
        violations: list[str] = []
        for path in sorted((ROOT / 'views').glob('*.py')):
            tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in forbidden_functions:
                    violations.append(f'{path.relative_to(ROOT)}:{node.lineno}: {node.name}')
        self.assertEqual([], violations, '\n'.join(violations))

    def test_calculation_service_modules_exist(self) -> None:
        expected = {
            'case_merge_service.py',
            'dashboard_view_service.py',
            'order_edit_service.py',
            'packing_view_service.py',
            'shared_document_view_service.py',
            'shipment_intake_view_service.py',
            'statistics_view_service.py',
        }
        existing = {path.name for path in (ROOT / 'services').glob('*.py')}
        self.assertTrue(expected.issubset(existing), sorted(expected - existing))


if __name__ == '__main__':
    unittest.main()
