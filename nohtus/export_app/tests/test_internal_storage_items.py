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
                marker = folder_service.write_case_marker(root, case, 'digest-123')

        self.assertEqual(folder_service.CASE_MARKER_NAME, marker.name)
        set_hidden.assert_called_once_with(marker)

    def test_marker_stores_content_fingerprint(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            case = {'id': 7, 'export_no': 'EXP-007'}
            with patch.object(folder_service, 'set_hidden', return_value=True):
                marker = folder_service.write_case_marker(root, case, 'digest-123')

            content = marker.read_text(encoding='utf-8')

        self.assertIn('"content_fingerprint": "digest-123"', content)

    def test_unchanged_case_skips_folder_and_workbook_sync(self):
        with tempfile.TemporaryDirectory() as temporary:
            current = Path(temporary) / 'KR' / 'case'
            current.mkdir(parents=True)
            case = {'id': 7, 'export_no': 'EXP-007'}
            with (
                patch.object(folder_service.db, 'row', return_value=case),
                patch.object(folder_service, 'find_case_folder', return_value=current),
                patch.object(folder_service, 'case_folder_base', return_value=current.parent),
                patch.object(folder_service, 'case_folder_name', return_value='case'),
                patch.object(folder_service, 'unique_folder_path', return_value=current),
                patch.object(folder_service, '_case_folder_is_current', return_value=True),
                patch.object(folder_service, 'sync_case_folder') as sync,
            ):
                folder, changed = folder_service.sync_case_folder_if_changed(7)

        self.assertEqual(current, folder)
        self.assertFalse(changed)
        sync.assert_not_called()

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
