"""purchase_history_single.py가 몽키패치 대신 파라미터 합성으로 바뀐 뒤에도
동일하게 동작하는지 확인하는 특성화 테스트. 원래 이 부분은 st.file_uploader/
purchase_page._import_purchase_history/_read_purchase_excel을 임시로
바꿔치기하는 3중 몽키패치였는데, purchase_history.py의 _import_purchase_history/
_render_import_box에 reader/before_import 파라미터를 추가해 그 자리에서
바로 원하는 동작을 조합하도록 바꿨다. 이 테스트는 그 리팩토링 전 실제
동작(노투스 7행 헤더 + 컬럼명 변환, 재업로드 전 기존 데이터 삭제)을
그대로 고정한다."""

import io
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import nohtus.db as db
from nohtus.pages import purchase_history as purchase_page
from nohtus.pages.purchase_history_single import (
    _read_purchase_excel_for_company,
    _replace_company_purchase_data,
)


def _excel_bytes(df, *, startrow=0):
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, startrow=startrow, sheet_name="Sheet1")
    return buffer.getvalue()


class UploadedFile:
    def __init__(self, payload: bytes, name: str = "upload.xlsx"):
        self._payload = payload
        self.name = name

    def read(self):
        return self._payload

    def seek(self, _pos):
        return None

    def getvalue(self):
        return self._payload


class ReadPurchaseExcelForCompanyTests(unittest.TestCase):
    def test_notus_file_reads_header_from_seventh_row_and_renames_columns(self):
        df = pd.DataFrame({
            "거래일자": ["2026-01-01"],
            "거래처명": ["거래처A"],
            "품목명/규격": ["제품A"],
            "수량": [10],
            "단가": [1000],
        })
        payload = _excel_bytes(df, startrow=6)

        result = _read_purchase_excel_for_company(payload, "노투스")

        self.assertIn("매입일자", result.columns)
        self.assertIn("제품명", result.columns)
        self.assertIn("실단가", result.columns)
        self.assertEqual(result.iloc[0]["매입일자"], "2026-01-01")

    def test_other_company_reads_header_from_first_row_without_renaming(self):
        df = pd.DataFrame({
            "매입일자": ["2026-01-01"],
            "거래처명": ["거래처A"],
            "제품명": ["제품A"],
            "수량": [10],
            "실단가": [1000],
        })
        payload = _excel_bytes(df, startrow=0)

        result = _read_purchase_excel_for_company(payload, "NOH")

        self.assertIn("매입일자", result.columns)
        self.assertIn("제품명", result.columns)
        self.assertEqual(result.iloc[0]["제품명"], "제품A")


class ImportPurchaseHistoryCompositionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self.temp_dir.name) / "wms.db"
        con = sqlite3.connect(self.db_path)
        try:
            con.execute(
                """CREATE TABLE purchase_history(
                    id INTEGER PRIMARY KEY AUTOINCREMENT, business_name TEXT NOT NULL,
                    purchase_date TEXT NOT NULL, supplier_name TEXT NOT NULL,
                    erp_product_name TEXT NOT NULL, specification TEXT, quantity REAL,
                    unit_price REAL, note TEXT, standard_product_name TEXT,
                    source_file TEXT, imported_at TEXT, duplicate_key TEXT UNIQUE
                )"""
            )
            con.execute(
                "CREATE TABLE products(standard_name TEXT, erp_nohtus_name TEXT, erp_noh_name TEXT, aliases TEXT)"
            )
            con.commit()
        finally:
            con.close()

        self.db_path_patcher = patch.object(db, "DB_PATH", self.db_path)
        self.db_path_patcher.start()

    def tearDown(self):
        self.db_path_patcher.stop()
        try:
            self.temp_dir.cleanup()
        except PermissionError:
            pass

    def _purchase_rows(self, company):
        con = sqlite3.connect(self.db_path)
        try:
            return con.execute(
                "SELECT purchase_date, supplier_name FROM purchase_history WHERE business_name=?",
                (company,),
            ).fetchall()
        finally:
            con.close()

    def test_notus_upload_uses_company_reader_and_wipes_existing_rows_first(self):
        con = sqlite3.connect(self.db_path)
        try:
            con.execute(
                "INSERT INTO purchase_history(business_name, purchase_date, supplier_name, erp_product_name, duplicate_key) "
                "VALUES('노투스','2020-01-01','옛거래처','옛제품','old-key')"
            )
            con.commit()
        finally:
            con.close()

        df = pd.DataFrame({
            "거래일자": ["2026-02-01"],
            "거래처명": ["새거래처"],
            "품목명/규격": ["새제품"],
            "수량": [5],
            "단가": [2000],
        })
        payload = _excel_bytes(df, startrow=6)
        uploaded = UploadedFile(payload)

        result = purchase_page._import_purchase_history(
            uploaded,
            "노투스",
            reader=_read_purchase_excel_for_company,
            before_import=_replace_company_purchase_data,
        )

        self.assertEqual(result["inserted"], 1)
        rows = self._purchase_rows("노투스")
        self.assertEqual(rows, [("2026-02-01", "새거래처")])

    def test_default_reader_used_when_none_passed(self):
        df = pd.DataFrame({
            "매입일자": ["2026-03-01"],
            "거래처명": ["거래처B"],
            "제품명": ["제품B"],
            "수량": [3],
            "실단가": [500],
        })
        payload = _excel_bytes(df, startrow=0)
        uploaded = UploadedFile(payload)

        result = purchase_page._import_purchase_history(uploaded, "NOH")

        self.assertEqual(result["inserted"], 1)
        self.assertEqual(self._purchase_rows("NOH"), [("2026-03-01", "거래처B")])


if __name__ == "__main__":
    unittest.main()
