from io import BytesIO
import sqlite3
import unittest

import pandas as pd

from nohtus.pages import history, history_business


class HistoryExportBehaviorTests(unittest.TestCase):
    def _rows(self, count=1, *, tx_type="입고", memo="일반 이력"):
        return pd.DataFrame(
            [
                {
                    "id": index + 1,
                    "created_at": "2026-08-24 09:00:00",
                    "actor": "tester",
                    "tx_type": tx_type,
                    "product_name": f"제품-{index + 1}",
                    "warehouse_name": f"ERP-{index + 1}",
                    "lot": "LOT-1",
                    "exp_date": "2027-12-31",
                    "from_company": "노투스",
                    "from_location": "A1-01-01",
                    "to_company": "",
                    "to_location": "",
                    "qty": 1,
                    "final_stock": 10,
                    "memo": memo,
                }
                for index in range(count)
            ]
        )

    def test_history_page_size_is_doubled(self):
        self.assertEqual(history.HISTORY_PAGE_SIZE, 20)

    def test_export_confirmation_is_displayed_as_outbound_instruction(self):
        rows = self._rows(
            tx_type="출고",
            memo="수출확정 / JP-Buyer-항공 / 매출처 / 출고일자: 2026-08-24",
        )

        shown = history._format_history_rows(rows)

        self.assertEqual(shown.iloc[0]["이력유형"], "출고지시")

    def test_displayed_export_confirmation_still_resolves_to_database_row(self):
        con = sqlite3.connect(":memory:")
        try:
            con.execute(
                """CREATE TABLE transactions(
                       id INTEGER PRIMARY KEY, created_at TEXT, tx_type TEXT,
                       product_name TEXT, lot TEXT, exp_date TEXT, memo TEXT
                   )"""
            )
            memo = "수출확정 / JP-Buyer-항공 / 매출처 / 출고일자: 2026-08-24"
            con.execute(
                "INSERT INTO transactions VALUES(1,?,?,?,?,?,?)",
                ("2026-08-24 09:00:00", "출고", "제품-1", "LOT-1", "2027-12-31", memo),
            )
            display_row = pd.Series(
                {
                    "일시": "2026-08-24 09:00:00",
                    "이력유형": "출고지시",
                    "제품명": "제품-1",
                    "LOT": "LOT-1",
                    "유통기한": "2027-12-31",
                    "메모": memo,
                }
            )

            tx_id = history_business._display_row_to_tx_id(con.cursor(), display_row, set())
        finally:
            con.close()

        self.assertEqual(tx_id, 1)

    def test_excel_contains_all_filtered_rows_not_one_page(self):
        shown = history._format_history_rows(self._rows(45))

        excel_bytes = history._history_excel_bytes(shown)
        restored = pd.read_excel(BytesIO(excel_bytes), sheet_name="이력조회")

        self.assertEqual(len(restored), 45)
        self.assertEqual(restored.iloc[0]["제품명"], "제품-1")
        self.assertEqual(restored.iloc[-1]["제품명"], "제품-45")

    def test_export_workflow_noise_prefixes_cover_waiting_and_edit_logs(self):
        self.assertIn("수출대기 등록 /", history.EXPORT_WORKFLOW_HIDDEN_MEMO_PREFIXES)
        self.assertIn("수출대기 수정 /", history.EXPORT_WORKFLOW_HIDDEN_MEMO_PREFIXES)
        self.assertIn("수출확정 수정 /", history.EXPORT_WORKFLOW_HIDDEN_MEMO_PREFIXES)


if __name__ == "__main__":
    unittest.main()
