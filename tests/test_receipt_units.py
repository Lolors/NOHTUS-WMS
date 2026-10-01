from test_statement_partial_returns import (module, item, repo, history, edit, initialize_database, PurchaseService, return_info)
from services.receipt_units import conversion_factor, convert_quantity, order_quantity
from ui.pages import statement_register_substitution as register, orders as order_page
from pathlib import Path
from datetime import date
from types import SimpleNamespace
from tempfile import TemporaryDirectory
import gc
import pandas as pd
import pytest


def converted():
    return dict(item(qty=500,amount=50000), 단위="EA", 원발주단위="BOX", 원발주제품코드="P1", 단위환산계수=100, 매입단가=100, 발주수량=5, 입고발주ID="O1")


def test_conversion_and_invalid_values():
    assert convert_quantity(5,100)==500
    assert convert_quantity(0.5,100)==50
    assert conversion_factor({})==1
    for value in [0,-1,1.5,float("nan")]:
        with pytest.raises(ValueError):convert_quantity(5,value)
    with pytest.raises(ValueError):convert_quantity(.333,100)


def test_partial_returns_use_order_units_for_remaining_and_status():
    sh=pd.DataFrame([dict(명세서ID="S1",발주ID="O1")])
    oi=pd.DataFrame([dict(발주ID="O1",제품코드="P1",정식제품명="제품A",규격="규격",단위="BOX",수량=5)])
    purchase=module()
    receipts=pd.DataFrame([converted()])
    purchase.load_purchase_data=lambda:(sh,receipts,pd.DataFrame(),pd.DataFrame())
    assert order_quantity(receipts.iloc[0])==5
    assert order_page._receipt_status_map(SimpleNamespace(safe_int=int),purchase,oi)["O1"]=="입고완료"
    history._process_returns(purchase,["S1"],receipts,pd.DataFrame([dict(반품=True,명세서ID="S1",순번=1,반품수량=50)]))
    receipts=purchase.save_table.call_args.args[1]
    assert order_quantity(receipts.iloc[0])==5
    assert register._selection_rows(purchase,oi,sh,receipts,"O1").empty
    assert order_page._receipt_status_map(SimpleNamespace(safe_int=int),purchase,oi)["O1"]=="입고완료"


def test_sqlite_and_statement_edit_preserve_factor_unit_and_amount():
    with TemporaryDirectory() as tmp:
        folder=Path(tmp);initialize_database(folder)
        service=PurchaseService(folder);purchase=module(service.save_table)
        purchase.save_statement_bundle=service.save_statement_bundle
        sh=pd.DataFrame([dict(명세서ID="S1",발주ID="O1",거래처명="병원")])
        repo.save_statement_bundle(folder,sh,pd.DataFrame([converted()]),pd.DataFrame(columns=repo.PRICE_HISTORY_COLUMNS))
        sh,it,pr,_=service.load_all()
        assert it.iloc[0]["단위환산계수"]==100
        edit._save_statement_edit(purchase,"S1",sh,it,pr,"1",date.today(),0,"",pd.DataFrame([dict(converted(),반품수량=50)]))
        saved=service.load_all()[1].iloc[0]
        assert saved["단위환산계수"]==100
        assert saved["단위"]=="EA"
        assert saved["입고수량"]==450
        assert saved["상품금액"]==45000
        assert return_info(saved["가격적용여부"])[1]==50
        gc.collect()


@pytest.mark.parametrize("delivered,returned,remaining", [(5,2,0),(5,5,0),(3,2,2),(3,3,2),(3,0,2)])
def test_returns_do_not_reopen_received_order_quantities(delivered,returned,remaining):
    from services.statement_returns import return_marker
    from ui.pages import purchase_enhancements
    sh=pd.DataFrame([dict(명세서ID="S1",발주ID="O1")])
    headers=pd.DataFrame([dict(발주ID="O1",거래처명="병원")])
    oi=pd.DataFrame([dict(발주ID="O1",제품코드="P1",정식제품명="제품A",규격="",단위="EA",수량=5)])
    receipts=pd.DataFrame([dict(item(qty=delivered-returned),가격적용여부=return_marker(returned,returned*1000) if returned else "적용")])
    purchase=module()
    purchase.load_purchase_data=lambda:(sh,receipts,pd.DataFrame(),pd.DataFrame())
    result=register._selection_rows(purchase,oi,sh,receipts,"O1")
    assert (result.empty if remaining==0 else result.iloc[0]["남은수량"]==remaining)
    assert register._open_orders(purchase,headers,oi).empty == (remaining==0)
    assert purchase_enhancements._open_orders(purchase,headers,oi)[0].empty == (remaining==0)
    assert order_page._receipt_status_map(SimpleNamespace(safe_int=int),purchase,oi)["O1"] == ("입고완료" if remaining==0 else "부분입고")
    assert receipts.iloc[0]["입고수량"]==delivered-returned
