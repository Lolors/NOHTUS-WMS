import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nohtus.export_app.services import photo_organizer_service


class Uploaded:
    def __init__(self, name: str, content: bytes = b'image'):
        self.name = name
        self._content = content

    def getvalue(self):
        return self._content


class PhotoOrganizerTests(unittest.TestCase):
    def test_names_single_photo_after_ctn(self):
        files = [Uploaded('original.JPG')]
        self.assertEqual(photo_organizer_service.build_photo_names('CTN1', files, ['내부']), ['CTN1.jpg'])

    def test_repeated_tags_receive_sequence_suffixes(self):
        files = [Uploaded('a.jpg'), Uploaded('b.png'), Uploaded('c.webp')]
        names = photo_organizer_service.build_photo_names('CTN2', files, ['내부', '외부', '내부'])
        self.assertEqual(names, ['CTN2_내부.jpg', 'CTN2_외부.png', 'CTN2_내부_1.webp'])

    def test_ctns_are_sorted(self):
        with patch.object(photo_organizer_service.db, 'rows', return_value=[{'box_no': 1}, {'box_no': 3}]):
            self.assertEqual(photo_organizer_service.list_ctn_numbers(7), [1, 3])

    def test_organize_uses_existing_case_folder_name_policy(self):
        case = {'id': 7}
        with tempfile.TemporaryDirectory() as temporary:
            with (
                patch.object(photo_organizer_service.db, 'row', return_value=case),
                patch.object(photo_organizer_service.folder_service, 'case_folder_name', return_value='0903 [Buyer SEA] Product'),
            ):
                destination = photo_organizer_service.organize_photos(
                    7,
                    Path(temporary),
                    {'CTN1': [Uploaded('a.jpg')], '전체': [Uploaded('all.png')]},
                    {'CTN1': ['내부'], '전체': ['내부']},
                )
            self.assertEqual(destination.name, '0903 [Buyer SEA] Product')
            self.assertEqual((destination / 'CTN1.jpg').read_bytes(), b'image')
            self.assertEqual((destination / '전체.png').read_bytes(), b'image')


if __name__ == '__main__':
    unittest.main()
