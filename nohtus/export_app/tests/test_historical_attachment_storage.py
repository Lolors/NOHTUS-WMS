import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nohtus.export_app.services import folder_service


class HistoricalAttachmentStorageTests(unittest.TestCase):
    def test_uploaded_bytes_are_written_directly_to_case_category_folder(self):
        with tempfile.TemporaryDirectory() as temporary:
            category = Path(temporary) / '01 출고제품 사진'
            category.mkdir()
            with (
                patch.object(folder_service, 'category_folder', return_value=category),
                patch.object(folder_service.db, 'execute') as execute,
            ):
                saved = folder_service.save_uploaded_file(
                    7, 'photo.jpg', b'image-bytes', '출고사진'
                )

            self.assertEqual(saved, category / 'photo.jpg')
            self.assertEqual(saved.read_bytes(), b'image-bytes')
            self.assertIn('file_name', execute.call_args.args[0])

    def test_multiple_files_with_same_name_are_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            category = Path(temporary) / '04 기타'
            category.mkdir()
            with (
                patch.object(folder_service, 'category_folder', return_value=category),
                patch.object(folder_service.db, 'execute'),
            ):
                first = folder_service.save_uploaded_file(7, 'doc.pdf', b'one', '기타')
                second = folder_service.save_uploaded_file(7, 'doc.pdf', b'two', '기타')

            self.assertEqual(first.name, 'doc.pdf')
            self.assertEqual(second.name, 'doc_2.pdf')
            self.assertEqual(second.read_bytes(), b'two')

    def test_unknown_category_is_rejected(self):
        with self.assertRaisesRegex(ValueError, '지원하지 않는'):
            folder_service.save_uploaded_file(7, 'doc.pdf', b'data', '잘못된폴더')


if __name__ == '__main__':
    unittest.main()
