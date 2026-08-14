from __future__ import annotations

import unittest
from unittest.mock import patch

from nohtus.export_app.services import document_unit_conversion_service


class DocumentUnitConversionServiceTests(unittest.TestCase):
    @patch.object(document_unit_conversion_service.db, 'executemany')
    def test_saves_document_unit_and_ea_factor(self, executemany) -> None:
        document_unit_conversion_service.save_case_conversions(
            7,
            [{'_id': 11, '문서 단위': 'box', '1 문서단위당 EA': 50}],
        )

        sql, values = executemany.call_args.args
        self.assertIn('document_unit=?', sql)
        self.assertEqual([('BOX', 50.0, 11, 7)], values)

    @patch.object(document_unit_conversion_service.db, 'executemany')
    def test_rejects_non_positive_factor(self, executemany) -> None:
        with self.assertRaisesRegex(ValueError, '0보다 커야'):
            document_unit_conversion_service.save_case_conversions(
                7,
                [{'_id': 11, '문서 단위': 'BOX', '1 문서단위당 EA': 0}],
            )

        executemany.assert_not_called()


if __name__ == '__main__':
    unittest.main()
