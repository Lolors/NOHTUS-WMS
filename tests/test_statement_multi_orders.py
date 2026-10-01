"""합산 명세서 저장, 배분, 반품과 기존 자료 호환 검증."""
from datetime import date
from pathlib import Path
import gc
import tempfile
import unittest
import pandas as pd
from test_statement_partial_returns import (
    module, item, select, repo, history, edit, initialize_database, PurchaseService, return_info,
)
from unittest.mock import patch
from services.statement_links import (linked_order_ids, encode_order_ids, receipts_for_order,
    validate_links, assert_order_not_shared, reassign_receipt_source)
from ui.pages import statement_register_substitution as register
from infrastructure.database import connect


def headers():
    return pd.DataFrame([dict(명세서ID="S1", 발주ID="O1", 거래처명="병원", 명세서번호="1",
        명세서일자="2026-09-16", 운송비=100, 연결발주ID=encode_order_ids(["O1","O2","O3"]))])


def orders():
    return pd.DataFrame([dict(발주ID=f"O{i}", 거래처명="병원", 발주일시=f"2026-09-{day}") for i,day in [(1,8),(2,15),(3,16)]])


def order_items():
    return pd.DataFrame([dict(발주ID=f"O{i}", 제품코드="P1", 정식제품명="제품A", 규격="규격", 단위="개", 수량=10) for i in range(1,4)])


def receipts():
    return pd.DataFrame([dict(item(sequence=i,qty=i,amount=i*1000),입고발주ID=f"O{i}") for i in range(1,4)])


class MultiOrderTests(unittest.TestCase):
    def test_legacy_owner_and_number(self):
        self.assertEqual(linked_order_ids({"발주ID":"O1"}),["O1"])
        self.assertEqual(len(receipts_for_order(pd.DataFrame([dict(명세서ID="S1",발주ID="O1")]),pd.DataFrame([item()]),"O1")),1)
        self.assertEqual(register._next_statement_number(pd.DataFrame(),"O1"),1)
        self.assertEqual(register._next_statement_number(headers(),"O3"),2)

    def test_source_quantities_and_remaining(self):
        rows=register._selection_rows(module(),order_items(),headers(),receipts(),"O1+O2+O3")
        self.assertEqual(rows["입고발주ID"].tolist(),["O1","O2","O3"])
        self.assertEqual(rows["남은수량"].tolist(),[9,8,7])
        for i in range(1,4):
            self.assertEqual(receipts_for_order(headers(),receipts(),f"O{i}")["입고수량"].sum(),i)

    def test_return_affects_only_assigned_order(self):
        purchase=module()
        history._process_returns(purchase,["S1"],receipts(),pd.DataFrame([select(sequence=2,qty=1)]))
        saved=purchase.save_table.call_args.args[1]
        self.assertEqual([int(receipts_for_order(headers(),saved,f"O{i}")["입고수량"].sum()) for i in range(1,4)],[1,1,3])

    def test_validation(self):
        self.assertEqual(validate_links(["O1","O2","O3"],orders(),"병원",receipts()),["O1","O2","O3"])
        for ids,vendor in [([],"병원"),(["O1"],"병원"),(["O1","O2","O3"],"다른 병원"),(["O1","O2","O3","missing"],"병원")]:
            with self.assertRaises(ValueError):
                validate_links(ids,orders(),vendor,receipts())

    def test_reassign_updates_original_and_rejects_unmatched(self):
        row=dict(item(),입고발주ID="O2",_original_order_id="O1")
        changed=reassign_receipt_source(row,order_items())
        self.assertEqual(changed["원발주제품코드"],"P1")
        self.assertEqual(changed["발주수량"],10)
        with self.assertRaises(ValueError):
            reassign_receipt_source(dict(row,제품코드="missing",정식제품명="없음"),order_items())

    def test_atomic_roundtrip_and_rollback(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);initialize_database(folder)
            prices=pd.DataFrame(columns=repo.PRICE_HISTORY_COLUMNS)
            repo.save_statement_bundle(folder,headers(),receipts(),prices)
            before=repo.load_all(folder)
            self.assertEqual(len(before[0]),1)
            self.assertEqual(before[0]["운송비"].sum(),100)
            self.assertEqual(linked_order_ids(before[0].iloc[0]),["O1","O2","O3"])
            self.assertEqual(before[1]["입고발주ID"].tolist(),["O1","O2","O3"])
            with patch.object(repo,"replace_price_history",side_effect=RuntimeError("test rollback")):
                with self.assertRaises(RuntimeError):
                    repo.save_statement_bundle(folder,headers().assign(운송비=999),receipts().assign(입고수량=999),prices)
            after=repo.load_all(folder)
            for a,b in zip(before,after):pd.testing.assert_frame_equal(a,b)
            conn=connect(folder)
            try:
                for oid in ["O1","O2","O3"]:
                    with self.assertRaises(ValueError):assert_order_not_shared(conn,oid)
                assert_order_not_shared(conn,"unrelated")
            finally:conn.close()
            gc.collect()

    def test_edit_existing_statement_to_three_orders(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);initialize_database(folder)
            service=PurchaseService(folder);purchase=module(service.save_table)
            purchase.save_statement_bundle=service.save_statement_bundle
            statement=headers().assign(연결발주ID="")
            repo.save_statement_bundle(folder,statement,pd.DataFrame([item()]),pd.DataFrame(columns=repo.PRICE_HISTORY_COLUMNS))
            sh,it,prices,_=service.load_all()
            edited=receipts()
            edited["반품수량"]=[0,1,0]
            edit._save_statement_edit(purchase,"S1",sh,it,prices,"1",date(2026,9,16),100,"",edited,linked_orders=["O1","O2","O3"])
            saved=service.load_all()
            self.assertEqual(linked_order_ids(saved[0].iloc[0]),["O1","O2","O3"])
            self.assertEqual(saved[1]["입고수량"].tolist(),[1,1,3])
            self.assertEqual(return_info(saved[1].iloc[1]["가격적용여부"])[1],1)
            gc.collect()
