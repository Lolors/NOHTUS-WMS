from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nohtus.export_app.services import folder_service


class InternalStorageItemTests(unittest.TestCase):
    def test_visible_items_excludes_all_dot_prefixed_entries(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / '.export_case.json').write_text('{}', encoding='utf-8')
            (root / '.backup').mkdir()
            (root / 'Packing List.xlsx').write_text('data', encoding='utf-8')
            (root / 'photos').mkdir()

            names = [item.name for item in folder_service.visible_items(root)]

        self.assertEqual(['photos', 'Packing List.xlsx'], names)

    def test_write_case_marker_requests_hidden_attribute(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            case = {'id': 7, 'export_no': 'EXP-007'}

            with patch.object(folder_service, 'set_hidden', return_value=True) as set_hidden:
                marker = folder_service.write_case_marker(root, case)

        self.assertEqual(folder_service.CASE_MARKER_NAME, marker.name)
        set_hidden.assert_called_once_with(marker)

    def test_existing_internal_items_are_reprocessed_on_windows(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            marker = root / '.export_case.json'
            backup = root / 'case' / '.backup'
            visible = root / 'case' / 'Invoice.pdf'
            marker.write_text('{}', encoding='utf-8')
            backup.mkdir(parents=True)
            visible.write_text('data', encoding='utf-8')

            with (
                patch.object(folder_service.os, 'name', 'nt'),
                patch.object(folder_service, 'set_hidden', return_value=True) as set_hidden,
            ):
                count = folder_service.hide_existing_internal_items(root)

        self.assertEqual(2, count)
        self.assertEqual({marker, backup}, {call.args[0] for call in set_hidden.call_args_list})


if __name__ == '__main__':
    unittest.main()
