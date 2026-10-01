"""부분반품, 반품취소 및 직접수정의 수량/금액 보존 회귀 테스트."""
from datetime import date
from pathlib import Path
from types import SimpleNamespace
import sys
import gc
import tempfile
import unittest
from unittest.mock import Mock

import pandas as pd

ROOT = Path(__file__).resolve().parents[1] / 'order_management_src'
for folder in (ROOT, ROOT / 'app_layers'):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

from app_layers.db_migration import initialize_database
from repositories import purchase_repository as repo
from services.purchase_service import PurchaseService
from services.statement_returns import return_info, return_marker, return_values
from ui.pages import statement_history as history, purchase_enhancements as edit
from ui.pages import statement_history_lot_ui


def module(save=None):
    return SimpleNamespace(
        to_int=lambda value: int(float(str(value or 0).replace(',', ''))),
        save_table=save or Mock(),
        STATEMENTS_FILE='purchase_statements.csv', STATEMENT_COLUMNS=repo.STATEMENT_COLUMNS,
        STATEMENT_ITEMS_FILE='purchase_statement_items.csv', STATEMENT_ITEM_COLUMNS=repo.STATEMENT_ITEM_COLUMNS,
        PRICE_HISTORY_FILE='price_history.csv', PRICE_HISTORY_COLUMNS=repo.PRICE_HISTORY_COLUMNS,
    )


def item(sid='S1', sequence=1, qty=10, amount=10000, marker='적용'):
    row = dict.fromkeys(repo.STATEMENT_ITEM_COLUMNS, '')
    row.update({'명세서ID':sid,'순번':sequence,'제품코드':'P1','정식제품명':'제품A','규격':'규격',
                '단위':'개','발주수량':10,'입고수량':qty,'매입단가':1000,'상품금액':amount,
                '가격적용여부':marker,'제조번호':f'LOT-{sequence}','유통기한':'2027-01-01'})
    return row


def select(sid='S1', sequence=1, qty=3):
    return {'반품':True,'명세서ID':sid,'순번':sequence,'반품수량':qty}


class StatementReturnsTests(unittest.TestCase):
    def test_partial_change_cancel_and_lot_isolation(self):
        purchase=module()
        frame=pd.DataFrame([item(),item(sequence=2),item('S2')])
        for target in [3, 6, 1, 10, 0]:
            self.assertEqual(history._process_returns(purchase,['S1'],frame,pd.DataFrame([select(qty=target)])),1)
            updated=purchase.save_table.call_args.args[1]
            self.assertEqual(updated.iloc[0]['입고수량'],10-target)
            self.assertEqual(updated.iloc[0]['상품금액'],(10-target)*1000)
            self.assertEqual(return_info(updated.iloc[0]['가격적용여부'])[1],target)
            pd.testing.assert_frame_equal(updated.iloc[1:],frame.iloc[1:])
            frame=updated

    def test_legacy_full_return_can_be_reduced_or_cancelled(self):
        for target in [4,0]:
            purchase=module()
            frame=pd.DataFrame([item(qty=0,amount=0,marker=return_marker(10,9501))])
            history._process_returns(purchase,['S1'],frame,pd.DataFrame([select(qty=target)]))
            row=purchase.save_table.call_args.args[1].iloc[0]
            self.assertEqual(row['입고수량'],10-target)
            self.assertEqual(row['상품금액']+return_info(row['가격적용여부'])[2],9501)
            if target==0:
                self.assertEqual(row['상품금액'],9501)

    def test_invalid_batch_does_not_save_any_changes(self):
        for invalid in [-1,11,1.5,None,float('nan')]:
            purchase=module()
            frame=pd.DataFrame([item(),item(sequence=2)])
            with self.assertRaises(ValueError):
                history._process_returns(purchase,['S1'],frame,pd.DataFrame([select(),select(sequence=2,qty=invalid)]))
            purchase.save_table.assert_not_called()
            self.assertEqual(frame.iloc[0]['입고수량'],10)

    def test_wrong_statement_and_duplicate_identity_are_rejected(self):
        for rows in [[select('S2')],[select(),select()]]:
            purchase=module()
            with self.assertRaises(ValueError):
                history._process_returns(purchase,['S1'],pd.DataFrame([item(),item('S2')]),pd.DataFrame(rows))
            purchase.save_table.assert_not_called()

    def test_editor_uses_actual_receipt_rows_including_substitutes(self):
        frame=pd.DataFrame([item(sequence=1,qty=7,amount=7000,marker=return_marker(3,3000)),item(sequence=2)])
        result=history._return_editor(pd.DataFrame(),frame,module())
        self.assertEqual(len(result),2)
        self.assertEqual(result.iloc[0]['총 입고수량'],10)
        self.assertEqual(result.iloc[0]['반품수량'],3)
        display=statement_history_lot_ui._statement_display_table(frame,module()).data
        self.assertEqual(display.iloc[0]['상태'],'부분반품')
        self.assertEqual(display.iloc[0]['수량'],7)
        self.assertNotIn('반품수량', display.columns)

    def test_sqlite_roundtrip_edit_return_and_restore(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder)
            initialize_database(folder)
            service=PurchaseService(folder)
            purchase=module(service.save_table)
            statements=pd.DataFrame([dict(zip(repo.STATEMENT_COLUMNS,['S1','O1','거래처','1','2026-09-17',100,'입력','','','']))])
            repo.replace_statements(folder,statements)
            repo.replace_statement_items(folder,pd.DataFrame([item(qty=0,amount=0,marker=return_marker(10,9501)),item('S2')]))
            for returned in [4,0]:
                statements,items,prices,_=service.load_all()
                edited=pd.DataFrame([dict(item(),입고수량=10,반품수량=returned,_original_quantity=10,_original_amount=9501,_original_price=1000)])
                edit._save_statement_edit(purchase,'S1',statements,items,prices,'changed',date(2026,9,17),200,'수정',edited)
                saved_statements,saved_items,_,_=service.load_all()
                row=saved_items[saved_items['명세서ID']=='S1'].iloc[0]
                self.assertEqual(row['입고수량'],10-returned)
                self.assertEqual(row['상품금액']+return_info(row['가격적용여부'])[2],9501)
                self.assertEqual(row['제조번호'],'LOT-1')
                self.assertEqual(saved_statements.iloc[0]['운송비'],200)
                self.assertEqual(saved_items[saved_items['명세서ID']=='S2'].iloc[0]['입고수량'],10)
            gc.collect()

    def test_edit_rejects_excess_return_before_any_save(self):
        purchase=module()
        statements=pd.DataFrame([{'명세서ID':'S1'}])
        with self.assertRaises(ValueError):
            edit._save_statement_edit(purchase,'S1',statements,pd.DataFrame([item()]),pd.DataFrame(columns=['명세서ID']),'1',date.today(),0,'',pd.DataFrame([dict(item(),반품수량=11)]))
        purchase.save_table.assert_not_called()


if __name__ == '__main__':
    unittest.main()
