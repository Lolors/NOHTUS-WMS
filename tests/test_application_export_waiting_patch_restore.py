import unittest
from unittest.mock import patch

import nohtus.application as application
import nohtus.pages.export_waiting as export_waiting_page
import nohtus.pages.outbound as outbound_page
import nohtus.services.export_waiting as export_waiting_service


class ApplicationExportWaitingPatchRestoreTests(unittest.TestCase):
    """수출대기 화면 진입 시 application.page_export_waiting()이 출고지시
    모듈에 임시로 심는 monkey patch를 정상/예외 경로 모두에서 원상복구하는지 검증한다.
    복원이 새면 다음 일반 출고지시 진입 시 거래처 검색 등이 깨진다."""

    def setUp(self):
        self._orig_page_outbound_renderer = export_waiting_page._page_outbound
        self._orig_find_unmatched = export_waiting_page._find_unmatched_p_item
        self._orig_take_p = export_waiting_service._take_p
        self._orig_customer_payload = getattr(outbound_page, "_current_customer_payload", None)
        self._orig_manual_pick_rows = getattr(outbound_page, "_manual_pick_rows", None)
        self._orig_last_sale_text = getattr(outbound_page, "_last_sale_text", None)
        self._orig_days_ago_label = getattr(outbound_page, "_days_ago_label", None)

    def tearDown(self):
        export_waiting_page._page_outbound = self._orig_page_outbound_renderer
        export_waiting_page._find_unmatched_p_item = self._orig_find_unmatched
        export_waiting_service._take_p = self._orig_take_p
        if self._orig_customer_payload is not None:
            outbound_page._current_customer_payload = self._orig_customer_payload
        if self._orig_manual_pick_rows is not None:
            outbound_page._manual_pick_rows = self._orig_manual_pick_rows
        if self._orig_last_sale_text is not None:
            outbound_page._last_sale_text = self._orig_last_sale_text
        if self._orig_days_ago_label is not None:
            outbound_page._days_ago_label = self._orig_days_ago_label

    def _assert_all_patches_restored(self):
        self.assertIs(export_waiting_page._page_outbound, self._orig_page_outbound_renderer)
        self.assertIs(export_waiting_page._find_unmatched_p_item, self._orig_find_unmatched)
        self.assertIs(export_waiting_service._take_p, self._orig_take_p)
        if self._orig_customer_payload is not None:
            self.assertIs(outbound_page._current_customer_payload, self._orig_customer_payload)
        if self._orig_manual_pick_rows is not None:
            self.assertIs(outbound_page._manual_pick_rows, self._orig_manual_pick_rows)
        if self._orig_last_sale_text is not None:
            self.assertIs(outbound_page._last_sale_text, self._orig_last_sale_text)
        if self._orig_days_ago_label is not None:
            self.assertIs(outbound_page._days_ago_label, self._orig_days_ago_label)

    def test_restores_patches_after_successful_render(self):
        with patch.object(application, "_page_export_waiting", return_value="rendered") as mock_render:
            result = application.page_export_waiting()

        mock_render.assert_called_once()
        self.assertEqual(result, "rendered")
        self._assert_all_patches_restored()

    def test_restores_patches_when_render_raises(self):
        with patch.object(application, "_page_export_waiting", side_effect=RuntimeError("boom")):
            with self.assertRaisesRegex(RuntimeError, "boom"):
                application.page_export_waiting()

        self._assert_all_patches_restored()

    def test_take_p_is_patched_only_during_render(self):
        captured = {}

        def capture_take_p(*_args, **_kwargs):
            captured["take_p_during_render"] = export_waiting_service._take_p
            return "rendered"

        with patch.object(application, "_page_export_waiting", side_effect=capture_take_p):
            application.page_export_waiting()

        self.assertNotEqual(captured["take_p_during_render"], self._orig_take_p)
        self.assertIs(export_waiting_service._take_p, self._orig_take_p)


if __name__ == "__main__":
    unittest.main()
