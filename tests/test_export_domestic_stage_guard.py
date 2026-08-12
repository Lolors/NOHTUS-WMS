import unittest
from pathlib import Path
from unittest.mock import patch

from nohtus.export_app.services import export_service


class ExportDomesticStageGuardTests(unittest.TestCase):
    def test_intake_query_excludes_domestic_delivery(self):
        source = Path(export_service.__file__).read_text(encoding='utf-8')
        intake_sql = source[source.index('def _cached_intake_editable_cases'):source.index('def intake_editable_cases')]
        self.assertNotIn("'국내배송'", intake_sql)

    def test_return_to_packing_complete_changes_stage_and_status(self):
        domestic = {'case_type': 'current', 'status': '완료', 'stage': '국내배송'}
        with (
            patch.object(export_service.db, 'row', return_value=domestic),
            patch.object(export_service.db, 'execute') as execute,
            patch.object(export_service, 'now_text', return_value='2026-08-12 12:00:00'),
        ):
            export_service.return_domestic_to_packing_complete(7)
        execute.assert_called_once_with(
            "UPDATE export_cases SET stage='패킹 완료',status='진행중',updated_at=? WHERE id=?",
            ('2026-08-12 12:00:00', 7),
        )

    def test_return_rejects_non_domestic_case(self):
        packing = {'case_type': 'current', 'status': '진행중', 'stage': '패킹 완료'}
        with patch.object(export_service.db, 'row', return_value=packing):
            with self.assertRaisesRegex(ValueError, '국내배송 단계'):
                export_service.return_domestic_to_packing_complete(7)

    def test_shared_documents_replaces_ship_date_controls_with_return_button(self):
        source = Path('nohtus/export_app/views/공유문서.py').read_text(encoding='utf-8')
        self.assertNotIn("'출고일 저장'", source)
        self.assertNotIn("'출고일'", source)
        self.assertIn("'패킹완료 단계로 되돌리기'", source)
        self.assertIn("str(case['case_type'] or '').strip() != 'historical'", source)
        self.assertIn("is_domestic_delivery and st.button", source)

    def test_packing_explicitly_excludes_domestic_delivery(self):
        source = Path('nohtus/export_app/views/박스_패킹_edit.py').read_text(encoding='utf-8')
        self.assertIn("if str(case['stage'] or '').strip() != '국내배송'", source)


if __name__ == '__main__':
    unittest.main()
