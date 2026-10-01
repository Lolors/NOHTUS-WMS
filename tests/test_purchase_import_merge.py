import sqlite3
import unittest
import pandas as pd
from test_purchase_history_single_composition import (
    ImportPurchaseHistoryCompositionTests as Fixture, UploadedFile, purchase_page,
)


def row(day="2026-09-01", **values):
    result=dict(매입일자=day,거래처명="매입처",제품명="LUNA EYES",규격="2ml",수량=5,실단가=16000,비고="")
    result.update(values)
    return result


class PurchaseMergeTests(unittest.TestCase):
    setUp=Fixture.setUp
    tearDown=Fixture.tearDown

    def upload(self, rows, token, company="NOH"):
        return purchase_page._import_purchase_history(UploadedFile(token.encode()),company,reader=lambda payload,company:pd.DataFrame(rows))

    def saved(self):
        with sqlite3.connect(self.db_path) as con:
            return con.execute("SELECT business_name,purchase_date,supplier_name,quantity FROM purchase_history ORDER BY id").fetchall()

    def test_rolling_overlap_preserves_older_history(self):
        self.upload([row("2025-01-01"),row("2026-08-01"),row()],"first")
        result=self.upload([row("2026-08-01"),row(),row("2026-09-17")],"second")
        self.assertEqual((result["inserted"],result["duplicates"]),(1,2))
        self.assertEqual(len(self.saved()),4)
        self.assertEqual(self.saved()[0][1],"2025-01-01")
        duplicate=self.upload([row()],"second")
        self.assertTrue(duplicate["file_duplicate"])
        self.assertEqual(len(self.saved()),4)

    def test_identical_legitimate_rows_keep_their_count(self):
        self.upload([row(),row()],"first")
        result=self.upload([row(),row(),row()],"second")
        self.assertEqual((result["inserted"],result["duplicates"]),(1,2))
        self.assertEqual(len(self.saved()),3)
        result=self.upload([row(),row()],"third")
        self.assertEqual(result["inserted"],0)
        self.assertEqual(len(self.saved()),3)

    def test_document_and_lot_distinguish_equal_amount_transactions(self):
        self.upload([row(번호=1,제조번호="A")],"first")
        result=self.upload([row(번호=1.0,제조번호="A"),row(번호=2,제조번호="A"),row(번호=1,제조번호="B")],"second")
        self.assertEqual((result["inserted"],result["duplicates"]),(2,1))

    def test_legacy_rows_are_adopted_without_duplication(self):
        self.upload([row()],"old-format")
        result=self.upload([row(번호=5,제품코드=606)],"new-format")
        self.assertEqual((result["inserted"],result["duplicates"]),(0,1))
        result=self.upload([row(번호=5,제품코드=606)],"another-file")
        self.assertEqual(result["inserted"],0)

    def test_different_companies_are_independent(self):
        self.upload([row()],"same",company="NOH")
        result=self.upload([row()],"same",company="노투스")
        self.assertEqual(result["inserted"],1)
        self.assertEqual(len(self.saved()),2)

    def test_invalid_file_and_failed_insert_preserve_history(self):
        self.upload([row("2020-01-01")],"first")
        with self.assertRaises(ValueError):self.upload([dict(잘못된컬럼="x")],"bad")
        self.assertEqual(len(self.saved()),1)
        with sqlite3.connect(self.db_path) as con:
            con.execute("CREATE TRIGGER fail_import BEFORE INSERT ON purchase_history WHEN NEW.supplier_name='FAIL' BEGIN SELECT RAISE(ABORT, 'test'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.upload([row(),row(거래처명="FAIL")],"failed")
        self.assertEqual(len(self.saved()),1)
        with sqlite3.connect(self.db_path) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM purchase_uploads").fetchone()[0],1)
