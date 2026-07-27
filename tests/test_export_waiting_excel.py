import unittest
from io import BytesIO

import pandas as pd

from nohtus.services.export_waiting_excel import (
    build_export_waiting_erp_sales_rows,
    export_waiting_erp_sales_excel_bytes,
    safe_export_no_for_filename,
)


class ExportWaitingExcelTests(unittest.TestCase):
    def test_rows_use_company_specific_erp_names_and_sum_lots(self):
        items = pd.DataFrame(
            [
                {"사업장": "NOH", "제품명": "표준 A", "수량": 3, "LOT": "L1"},
                {"사업장": "NOH", "제품명": "표준 A", "수량": 7, "LOT": "L2"},
                {"사업장": "노투스팜", "제품명": "표준 A", "수량": 5, "LOT": "L3"},
                {"사업장": "비자료", "제품명": "표준 A", "수량": 2, "LOT": "L4"},
            ]
        )
        product_map = {
            ("NOH", "표준 A"): "NOH ERP A",
            ("노투스팜", "표준 A"): "팜 ERP A",
            ("비자료", "표준 A"): "비자료 A",
        }

        result = build_export_waiting_erp_sales_rows(items, product_map)

        self.assertEqual(len(result), 3)
        noh = result[result["사업장"] == "NOH"].iloc[0]
        pharm = result[result["사업장"] == "노투스팜"].iloc[0]
        bidata = result[result["사업장"] == "비자료"].iloc[0]
        self.assertEqual(noh["ERP명"], "NOH ERP A")
        self.assertEqual(int(noh["수량"]), 10)
        self.assertEqual(pharm["ERP명"], "팜 ERP A")
        self.assertEqual(int(pharm["수량"]), 5)
        self.assertEqual(bidata["ERP명"], "비자료 A")
        self.assertEqual(int(bidata["수량"]), 2)

    def test_missing_mapping_is_blank_and_marked_for_review(self):
        items = pd.DataFrame([{"사업장": "NOH", "제품명": "표준 B", "수량": 4}])

        result = build_export_waiting_erp_sales_rows(items, {})

        self.assertEqual(result.iloc[0]["ERP명"], "")
        self.assertEqual(result.iloc[0]["매칭상태"], "확인필요")

    def test_excel_contains_expected_columns_and_numeric_quantity(self):
        rows = pd.DataFrame(
            [{"사업장": "NOH", "표준제품명": "표준 A", "ERP명": "ERP A", "수량": 12, "매칭상태": "매칭완료"}]
        )

        workbook = export_waiting_erp_sales_excel_bytes(rows)
        restored = pd.read_excel(BytesIO(workbook), sheet_name="ERP매출입력용")

        self.assertEqual(list(restored.columns), ["사업장", "표준제품명", "ERP명", "수량", "매칭상태"])
        self.assertEqual(int(restored.iloc[0]["수량"]), 12)

    def test_export_number_is_safe_for_windows_filename(self):
        self.assertEqual(safe_export_no_for_filename("EXP/26:01"), "EXP_26_01")


if __name__ == "__main__":
    unittest.main()
