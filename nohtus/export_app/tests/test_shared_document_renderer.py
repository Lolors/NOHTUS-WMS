from datetime import date
import unittest

from nohtus.export_app.components.shared_document_renderer import _pdf_document_title, _print_title_script


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

    def test_print_script_temporarily_changes_parent_document_title(self):
        script = _print_title_script('Japan_ABC Buyer_AIR_2026-08-14')

        self.assertIn('function printFinalDocument()', script)
        self.assertIn('window.parent.document', script)
        self.assertIn('hostDocument.title = requestedTitle', script)
        self.assertIn("window.addEventListener('afterprint', restoreTitle", script)


if __name__ == '__main__':
    unittest.main()
