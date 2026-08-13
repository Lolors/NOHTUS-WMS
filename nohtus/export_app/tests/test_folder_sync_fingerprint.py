from pathlib import Path
import unittest
from unittest.mock import patch

from nohtus.export_app.services import folder_service


class FolderSyncFingerprintTests(unittest.TestCase):
    def test_fingerprint_changes_when_order_content_changes(self) -> None:
        case = {'id': 1, 'export_no': 'EXP-1', 'folder_path': 'ignored'}
        with (
            patch.object(folder_service.db, 'row', return_value=case),
            patch.object(folder_service.db, 'rows', side_effect=[
                [{'id': 1, 'product_name': 'A', 'quantity': 1}], [], [], [],
                [{'id': 1, 'product_name': 'A', 'quantity': 2}], [], [], [],
            ]),
        ):
            first = folder_service.case_content_fingerprint(1)
            second = folder_service.case_content_fingerprint(1)

        self.assertNotEqual(first, second)

    def test_view_reports_regenerated_and_skipped_counts(self) -> None:
        source = Path('nohtus/export_app/views/내_폴더.py').read_text(encoding='utf-8')
        self.assertIn('sync_case_folder_if_changed', source)
        self.assertIn('변경 없음', source)
        self.assertNotIn('force_workbook=True', source)
