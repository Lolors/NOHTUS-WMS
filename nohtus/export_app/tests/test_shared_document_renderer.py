from datetime import date
import unittest

from nohtus.export_app.components.shared_document_renderer import _pdf_document_title


class SharedDocumentRendererTests(unittest.TestCase):
    def test_pdf_title_uses_case_details_and_current_date(self):
        case = {'country': 'Japan', 'buyer': 'ABC Buyer', 'transport_mode': 'AIR'}

        title = _pdf_document_title(case, date(2026, 8, 14))

        self.assertEqual(title, 'Japan_ABC Buyer_AIR_2026-08-14')

    def test_pdf_title_removes_characters_forbidden_in_windows_filenames(self):
        case = {'country': 'Korea/Japan', 'buyer': 'A*B?', 'transport_mode': 'DHL: AIR'}

        title = _pdf_document_title(case, date(2026, 8, 14))

        self.assertEqual(title, 'Korea Japan_A B_DHL AIR_2026-08-14')
        self.assertNotRegex(title, r'[<>:"/\\|?*]')


if __name__ == '__main__':
    unittest.main()
