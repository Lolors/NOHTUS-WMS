import sqlite3
from types import SimpleNamespace
from unittest.mock import patch
import pandas as pd
from nohtus.pages import location_map as page, location_map_business as business
from nohtus.streamlit_patch_lock import current


def test_business_search_does_not_reintroduce_empty_g_locations():
    with sqlite3.connect(":memory:") as conn:
        conn.execute("CREATE TABLE inventory (location TEXT,qty INTEGER,product_name TEXT)")
        conn.executemany("INSERT INTO inventory VALUES (?,?,?)",[("C1-01-02",14,"바이리쥬"),("G1-01-01",694,"바이리쥬"),("G1-01-02",0,"바이리쥬"),("G1-02-01",0,"바이리쥬"),("G2-01-01",0,"바이리쥬")])
        def render(term,compact=False):
            return current(page,"q")("SELECT * FROM inventory WHERE qty>0")
        with patch.object(business,"st",SimpleNamespace(session_state={business._EXCLUDE_MATERIALS_KEY:False})),patch.object(page,"q",lambda sql,params=():pd.read_sql_query(sql,conn,params=params)),patch.object(business,"_ORIGINAL_MAP_SEARCH_RESULTS",render):
            result=business._page_map_search_results_with_available_filter("바이리쥬")
        assert result["location"].tolist()==["C1-01-02","G1-01-01"]
        assert result["qty"].sum()==708


def test_card_groups_remove_zero_negative_and_invalid_quantities():
    frame=pd.DataFrame([dict(product_name="제품",warehouse_name="ERP",location=f"G1-{i}",qty=qty) for i,qty in enumerate([14,694,0,"0",-1,None,"bad"])])
    group=page._map_search_product_groups("제품",frame)[0]
    assert group["total_qty"]==708
    assert len(group["rows"])==2
