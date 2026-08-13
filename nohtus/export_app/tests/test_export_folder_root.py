from pathlib import Path
import unittest
from unittest.mock import patch

from nohtus.export_app.services import folder_service


class ExportFolderRootTests(unittest.TestCase):
    def test_usb_root_starts_directly_with_country_folders(self) -> None:
        usb_root = Path("E:/")
        with (
            patch.object(folder_service.db, "get_setting", return_value=""),
            patch.object(folder_service.usb_storage_service, "find_export_usb", return_value=usb_root),
        ):
            self.assertEqual(folder_service._configured_storage_path(), usb_root)

    def test_help_example_no_longer_adds_export_management_folder(self) -> None:
        source = Path("nohtus/export_app/views/내_폴더.py").read_text(encoding="utf-8")

        self.assertNotIn("'''수출관리", source)
        self.assertIn("'''필리핀", source)
