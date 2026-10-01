from contextlib import contextmanager, closing
from datetime import date
from pathlib import Path
import json
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor

from nohtus.services import customer_returns as returns
from nohtus.services import inventory


class CustomerReturnTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.wms=self.root/'wms.db';self.purchase=self.root/'purchase_order.db'
        @contextmanager
        def connect():
            con=sqlite3.connect(self.wms,timeout=10)
            try:
                with con:yield con
            finally:con.close()
        self.connect=connect
        with connect() as con:
            con.executescript('''
            CREATE TABLE inventory(id INTEGER PRIMARY KEY,company TEXT,product_name TEXT,warehouse_name TEXT,lot TEXT,exp_date TEXT,location TEXT,qty INTEGER,updated_at TEXT,location_range_cells TEXT,location_range_end TEXT);
            CREATE TABLE products(id INTEGER PRIMARY KEY,standard_name TEXT,erp_nohtuspharm_name TEXT,product_code TEXT,erp_nohtus_name TEXT,erp_noh_name TEXT,bidata_name TEXT);
            CREATE TABLE outbound_orders(id INTEGER PRIMARY KEY,order_date TEXT,title TEXT,customer_name TEXT,status TEXT);
            CREATE TABLE outbound_order_items(id INTEGER PRIMARY KEY,order_id INTEGER,company TEXT,product_name TEXT,lot TEXT,exp_date TEXT,qty INTEGER);
            CREATE TABLE transactions(id INTEGER PRIMARY KEY,created_at TEXT,actor TEXT,tx_type TEXT,product_name TEXT,warehouse_name TEXT,lot TEXT,exp_date TEXT,from_company TEXT,from_location TEXT,to_company TEXT,to_location TEXT,qty INTEGER,memo TEXT,final_stock INTEGER);
            INSERT INTO products VALUES(1,'델가다 (5EA)','델가다 5V','P1','노투스 델가다','NOH 델가다','비자료 델가다');
            INSERT INTO inventory VALUES(1,'노투스팜','델가다 (5EA)','델가다 5V','LOT1','2028-01-01','A1-01-01',20,'',NULL,NULL);
            INSERT INTO outbound_orders VALUES(1,'2026-09-01','고객A 출고','고객A','저장됨');
            INSERT INTO outbound_order_items VALUES(1,1,'노투스팜','델가다 (5EA)','LOT1','2028-01-01',10);
            ''')
        with closing(sqlite3.connect(self.purchase)) as con:
            con.executescript('''
            CREATE TABLE statements(statement_id TEXT,statement_date TEXT,statement_number TEXT,vendor_name TEXT);
            CREATE TABLE statement_items(statement_id TEXT,sequence INTEGER,product_code TEXT,product_name TEXT,packaging_unit TEXT,lot_number TEXT,expiry_date TEXT,apply_price TEXT);
            INSERT INTO statements VALUES('S1','2026-09-01','N1','고객A');
            INSERT INTO statement_items VALUES('S1',1,'P1','델가다 5V','박스','LOT1','2028-01-01','반품:4:400:2026-10-01');
            ''')
            con.commit()
        self.patches=[patch.object(returns,'connect',connect),patch.object(returns,'purchase_db_path',return_value=self.purchase),patch.object(returns,'_current_actor',return_value='test'),patch.object(inventory,'_current_actor',return_value='test')]
        for p in self.patches:p.start()
        # Commit seed purchase records before read-only source queries.
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.tmp.cleanup()
    def source(self,kind='outbound'):
        return returns.outbound_sources()[0] if kind=='outbound' else returns.statement_sources()[0]
    def receive(self,qty=3,token='one',kind='outbound',**kw):
        s=self.source(kind)
        data=dict(kind=kind,key=s['source_key'],fingerprint=s['fingerprint'],source_qty=qty,location='A1-01-01',request_token=token,product_name='델가다 (5EA)')
        data.update(kw)
        return returns.receive_return(**data)
    def stock(self):
        with self.connect() as con:return con.execute('SELECT SUM(qty) FROM inventory').fetchone()[0]
    def test_search_read_only_and_customer_product_filter(self):
        self.assertEqual(len(returns.outbound_sources(customer='고객A',product='델가다',start='2026-01-01',end='2026-12-31')),1)
        self.assertEqual(returns.outbound_sources(customer='다른 고객'),[])
        self.source('statement')
        with self.connect() as con:self.assertFalse(returns._exists(con))
    def test_outbound_partial_receipt_and_exact_inventory_identity(self):
        id=self.receive(3)
        self.assertEqual(self.stock(),23)
        self.assertEqual(self.source()['remaining_qty'],7)
        with self.connect() as con:
            self.assertEqual(con.execute('SELECT tx_type,to_company,lot,exp_date,qty,final_stock FROM transactions').fetchone(),('반품입고','노투스팜','LOT1','2028-01-01',3,23))
            self.assertEqual(con.execute('SELECT qty FROM outbound_order_items').fetchone()[0],10)
    def test_idempotent_double_submit(self):
        self.assertEqual(self.receive(3),self.receive(3))
        self.assertEqual(self.stock(),23)
        self.assertEqual(len(returns.receipt_history()),1)
    def test_overreturn_rejected(self):
        self.receive(8)
        with self.assertRaises(ValueError):self.receive(3,token='two')
        self.assertEqual(self.stock(),28)
    def test_cancelled_source_rejected(self):
        source=self.source()
        with self.connect() as con:con.execute("UPDATE outbound_orders SET status='취소됨'")
        with self.assertRaises(ValueError):returns.receive_return(kind='outbound',key=source['source_key'],fingerprint=source['fingerprint'],source_qty=1,location='REC',request_token='bad')
        self.assertEqual(self.stock(),20)
    def test_statement_receipt_and_partial_limit(self):
        self.receive(3,kind='statement',outbound_key=self.source()['source_key'])
        self.assertEqual(self.source('statement')['remaining_qty'],1)
        self.assertEqual(self.source()['remaining_qty'],7)
        with self.assertRaises(ValueError):self.receive(2,token='two',kind='statement')
        self.assertEqual(self.stock(),23)
    def test_both_routes_share_original_outbound_cap(self):
        self.receive(8)
        with self.assertRaises(ValueError):self.receive(3,token='two',kind='statement',outbound_key=self.source()['source_key'])
    def test_unit_conversion_and_no_fractional_wms_stock(self):
        self.receive(4,kind='statement',factor='0.5')
        self.assertEqual(self.stock(),22)
        with self.assertRaises(ValueError):self.receive(1,token='two',kind='statement',factor='0.5')
    def test_source_fingerprint_change_rejected(self):
        source=self.source('statement')
        with closing(sqlite3.connect(self.purchase)) as con:con.execute("UPDATE statement_items SET lot_number='OTHER'");con.commit()
        with self.assertRaises(ValueError):returns.receive_return(kind='statement',key=source['source_key'],fingerprint=source['fingerprint'],source_qty=1,location='REC',request_token='bad',product_name='델가다 (5EA)')
    def test_cancel_receipt_reverses_stock_and_reopens_source(self):
        id=self.receive(3);returns.cancel_return(id)
        self.assertEqual(self.stock(),20);self.assertEqual(self.source()['remaining_qty'],10)
        with self.assertRaises(ValueError):returns.cancel_return(id)
        with self.connect() as con:self.assertEqual(con.execute('SELECT qty FROM transactions ORDER BY id').fetchall(),[(3,),(-3,)])
    def test_cannot_cancel_after_stock_consumed(self):
        id=self.receive(3)
        with self.connect() as con:con.execute('UPDATE inventory SET qty=0')
        with self.assertRaises(ValueError):returns.cancel_return(id)
    def test_order_and_history_guards(self):
        id=self.receive(3)
        with self.connect() as con:
            with self.assertRaises(ValueError):returns.assert_order_editable(con.cursor(),1)
            tx=con.execute('SELECT transaction_id FROM customer_return_receipts').fetchone()[0]
            returns.assert_history_editable(con.cursor(),[tx])
        returns.cancel_return(id)
        with self.connect() as con:returns.assert_order_editable(con.cursor(),1)
    def test_failure_rolls_back_stock_and_receipt(self):
        with patch.object(returns,'insert_transaction_log',side_effect=RuntimeError('failed')):
            with self.assertRaises(RuntimeError):self.receive(3)
        self.assertEqual(self.stock(),20);self.assertEqual(returns.receipt_history(),[])
    def test_concurrent_receipts_do_not_exceed_source(self):
        def run(token):
            try:return self.receive(6,token=token)
            except ValueError:return None
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run,['a','b']))
        self.assertEqual(sum(r is not None for r in results),1);self.assertEqual(self.stock(),26)
    def test_invalid_quantity_and_location_rejected(self):
        for value in [0,-1,1.5,'NaN']:
            with self.assertRaises(ValueError):self.receive(value)
        with self.assertRaises(ValueError):self.receive(1,location='INVALID')
        self.assertEqual(self.stock(),20)

    def test_purchase_amounts_and_source_marker_are_unchanged(self):
        with closing(sqlite3.connect(self.purchase)) as con:
            before=con.execute('SELECT * FROM statement_items').fetchall()
        self.receive(2,kind='statement')
        with closing(sqlite3.connect(self.purchase)) as con:
            self.assertEqual(con.execute('SELECT * FROM statement_items').fetchall(),before)
    def test_statement_edit_cannot_erase_received_return(self):
        import pandas as pd
        import nohtus.db
        self.receive(2,kind='statement')
        frame=pd.DataFrame([{'명세서ID':'S1','순번':1,'제품코드':'P1','정식제품명':'델가다 5V','단위':'박스','제조번호':'LOT1','유통기한':'2028-01-01','가격적용여부':'반품:4:400:time'}])
        with patch.object(nohtus.db,'DB_PATH',self.wms):
            returns.validate_statement_replacement(self.root,frame)
            changed=frame.copy();changed.at[0,'가격적용여부']='반품:1:100:time'
            with self.assertRaises(ValueError):returns.validate_statement_replacement(self.root,changed)
            changed=frame.copy();changed.at[0,'제조번호']='LOT2'
            with self.assertRaises(ValueError):returns.validate_statement_replacement(self.root,changed)
            with self.assertRaises(ValueError):returns.validate_statement_replacement(self.root,frame.iloc[0:0])
    def test_statement_cannot_link_another_customer(self):
        s=self.source()
        with self.connect() as con:con.execute("UPDATE outbound_orders SET customer_name='다른 고객'")
        with self.assertRaises(ValueError):self.receive(2,kind='statement',outbound_key=s['source_key'])
    def test_own_product_delta_includes_return_and_cancellation(self):
        import pandas as pd
        from nohtus.pages import own_product_status
        def query(sql,params=()):
            with self.connect() as con:return pd.read_sql_query(sql,con,params=params)
        with patch.object(own_product_status,'q',query):
            id=self.receive(3)
            self.assertEqual(own_product_status._today_delta_map()[('노투스팜','델가다 (5EA)')],3)
            returns.cancel_return(id)
            self.assertEqual(own_product_status._today_delta_map()[('노투스팜','델가다 (5EA)')],0)
    def test_ui_outbound_entry_and_cancellation(self):
        from streamlit.testing.v1 import AppTest
        from nohtus.pages import customer_returns as page
        with patch.object(page,'can_access_page',return_value=True):
            app=AppTest.from_string('from nohtus.pages.customer_returns import page_customer_returns\npage_customer_returns()').run()
            self.assertFalse(app.exception)
            next(w for w in app.selectbox if w.label=='반품할 내역').select(self.source()['source_key']).run()
            self.assertFalse(app.exception)
            app.number_input[0].set_value(3)
            next(b for b in app.button if b.label=='반품 목록에 담기').click().run()
            next(b for b in app.button if b.label=='반품 입고 완료').click().run()
            self.assertFalse(app.exception);self.assertEqual(self.stock(),23)
            app.radio[0].set_value('반품 입고 내역').run()
            self.assertEqual(list(app.dataframe[0].value.columns)[:2],['선택','번호'])
            editor=next(k for k in app.session_state.filtered_state if k.startswith('return_history_selection_'))
            app.session_state[editor]={'edited_rows':{0:{'선택':True}},'added_rows':[],'deleted_rows':[]}
            next(b for b in app.button if b.label=='선택 반품 입고 취소').click().run()
            self.assertFalse(app.exception);self.assertEqual(self.stock(),20)
    def test_ui_statement_order_selection_and_mapping(self):
        from streamlit.testing.v1 import AppTest
        from nohtus.pages import customer_returns as page
        with patch.object(page,'can_access_page',return_value=True):
            code="import streamlit as st\nfrom nohtus.pages.customer_returns import page_customer_returns\nst.session_state.setdefault('_customer_return_mode','거래명세서 반품')\npage_customer_returns()"
            app=AppTest.from_string(code).run()
            next(w for w in app.selectbox if w.label=='반품할 주문').select('statement:S1').run()
            self.assertFalse(app.exception)
            table=app.dataframe[0].value
            self.assertEqual(table['WMS 표준제품명'].iloc[0],'델가다 5V')
            self.assertEqual(table['연결 제품명'].iloc[0],'델가다 5V')
            self.assertNotIn('입고 제품명',table.columns)
            editor=next(k for k in app.session_state.filtered_state if k.startswith('return_order_editor_'))
            app.session_state[editor]={'edited_rows':{0:{'선택':True,'연결 제품명':'팜 반품제품','입고수량':2}},'added_rows':[],'deleted_rows':[]}
            next(b for b in app.button if b.label=='선택 제품 장바구니에 담기').click().run()
            self.assertFalse(app.exception)
            self.assertEqual(len(app.session_state['_customer_return_cart']),1)
            self.assertEqual(self.stock(),20)
            next(b for b in app.button if b.label=='반품 입고 완료').click().run()
            self.assertFalse(app.exception);self.assertEqual(self.stock(),22)
            with self.connect() as con:
                self.assertEqual(con.execute("SELECT erp_nohtuspharm_name FROM products WHERE standard_name='델가다 5V'").fetchone()[0],'팜 반품제품')

    def test_viewer_cannot_open_entry(self):
        from streamlit.testing.v1 import AppTest
        from nohtus.pages import customer_returns as page
        with patch.object(page,'can_access_page',return_value=False):
            app=AppTest.from_string('from nohtus.pages.customer_returns import page_customer_returns\npage_customer_returns()').run()
            self.assertTrue(app.warning);self.assertFalse(app.button)

    def test_statement_button_switches_mode_without_stock_write(self):
        from streamlit.testing.v1 import AppTest
        code="import streamlit as st\nfrom nohtus.pages.customer_returns import open_statement_return\nst.button('WMS 반품 입고',on_click=open_statement_return,args=('S1',))"
        app=AppTest.from_string(code).run()
        app.button[0].click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['page'],'반품 입고')
        self.assertEqual(app.session_state['_top_app_mode'],'wms')
        self.assertEqual(app.session_state['_customer_return_statement'],'S1')
        self.assertFalse(app.session_state['app_mode_switch'])
        self.assertEqual(self.stock(),20)


    def test_destination_companies_and_cancellation(self):
        for company,name in [('노투스','노투스 델가다'),('NOH','NOH 델가다'),('비자료','비자료 델가다')]:
            for kind in ['outbound','statement']:
                with self.subTest(company=company,kind=kind):
                    receipt=self.receive(2,token=company+kind,company=company,kind=kind)
                    row=returns.receipt_history()[0]
                    self.assertEqual((row['company'],row['warehouse_name']),(company,name))
                    with self.connect() as con:
                        self.assertEqual(con.execute("SELECT qty FROM inventory WHERE company='노투스팜'").fetchone()[0],20)
                        self.assertEqual(con.execute('SELECT to_company,qty FROM transactions ORDER BY id DESC LIMIT 1').fetchone(),(company,2))
                    returns.cancel_return(receipt)
                    self.assertEqual(self.stock(),20)
                    with self.connect() as con:
                        self.assertEqual(con.execute('SELECT to_company,qty FROM transactions ORDER BY id DESC LIMIT 1').fetchone(),(company,-2))
    def test_company_validation_and_idempotency(self):
        for company in ['등록대기','없는 사업장',None]:
            with self.assertRaises(ValueError):self.receive(company=company)
        self.assertEqual(self.stock(),20)
        self.receive(company='비자료')
        with self.assertRaises(ValueError):self.receive(company='노투스팜')
        self.assertEqual(self.stock(),23)
    def test_partial_returns_share_cap_across_companies(self):
        self.receive(6,company='비자료')
        with self.assertRaises(ValueError):self.receive(5,token='two',company='NOH')
        self.receive(4,token='three',company='노투스')
        self.assertEqual(self.source()['remaining_qty'],0)
    def test_selected_company_mapping_required(self):
        with self.connect() as con:con.execute("UPDATE products SET bidata_name=''")
        with self.assertRaisesRegex(ValueError,'비자료'):self.receive(company='비자료')
        self.assertEqual(self.stock(),20)
    def test_ui_default_and_changed_destination(self):
        from streamlit.testing.v1 import AppTest
        from nohtus.pages import customer_returns as page
        with patch.object(page,'can_access_page',return_value=True):
            app=AppTest.from_string('from nohtus.pages.customer_returns import page_customer_returns\npage_customer_returns()').run()
            next(w for w in app.selectbox if w.label=='반품할 내역').select(self.source()['source_key']).run()
            company=next(w for w in app.selectbox if w.label=='반품 입고 사업장')
            self.assertEqual(company.value,'노투스팜')
            company.select('비자료').run()
            app.number_input[0].set_value(2)
            next(b for b in app.button if b.label=='반품 목록에 담기').click().run()
            next(b for b in app.button if b.label=='반품 입고 완료').click().run()
            self.assertFalse(app.exception)
            self.assertEqual(returns.receipt_history()[0]['company'],'비자료')
            app.radio[0].set_value('반품 입고 내역').run()
            self.assertEqual(app.dataframe[0].value['입고 사업장'].iloc[0],'비자료')


    def basket_item(self,qty=2,token='basket',kind='outbound',company='노투스팜'):
        source=self.source(kind)
        return dict(kind=kind,key=source['source_key'],fingerprint=source['fingerprint'],source_qty=qty,request_token=token,product_name='델가다 (5EA)',company=company)
    def test_basket_shared_fields_mixed_routes_and_retry(self):
        items=[self.basket_item(),self.basket_item(token='other',kind='statement',company='비자료')]
        ids=returns.receive_returns(items,location='REC',receipt_date=date.today(),memo='공통 메모')
        self.assertEqual(len(ids),2)
        self.assertEqual(returns.receive_returns(items,location='REC',receipt_date=date.today(),memo='공통 메모'),ids)
        self.assertEqual(self.stock(),24)
        for row in returns.receipt_history():
            self.assertEqual((row['location'],row['receipt_date'],row['memo']),('REC',date.today().isoformat(),'공통 메모'))
    def test_basket_failure_rolls_back_all_rows(self):
        items=[self.basket_item(6),self.basket_item(5,token='other',company='비자료')]
        with self.assertRaises(ValueError):returns.receive_returns(items,location='REC')
        self.assertEqual(self.stock(),20)
        self.assertEqual(returns.receipt_history(),[])
        with self.connect() as con:self.assertEqual(con.execute('SELECT COUNT(*) FROM transactions').fetchone()[0],0)
    def test_basket_duplicate_tokens_and_empty_rejected(self):
        for items in [[],[self.basket_item(),self.basket_item()]]:
            with self.assertRaises(ValueError):returns.receive_returns(items,location='REC')
        self.assertEqual(self.stock(),20)
    def test_ui_cart_add_replace_remove_and_common_fields(self):
        from streamlit.testing.v1 import AppTest
        from nohtus.pages import customer_returns as page
        with patch.object(page,'can_access_page',return_value=True):
            app=AppTest.from_string('from nohtus.pages.customer_returns import page_customer_returns\npage_customer_returns()').run()
            next(w for w in app.selectbox if w.label=='반품할 내역').select(self.source()['source_key']).run()
            app.number_input[0].set_value(2)
            next(b for b in app.button if b.label=='반품 목록에 담기').click().run()
            self.assertEqual(self.stock(),20)
            app.number_input[0].set_value(3)
            next(b for b in app.button if b.label=='반품 목록에 담기').click().run()
            self.assertEqual(len(app.session_state['_customer_return_cart']),1)
            next(w for w in app.selectbox if w.label=='반품 입고 사업장').select('비자료').run()
            next(b for b in app.button if b.label=='반품 목록에 담기').click().run()
            self.assertEqual(len(app.session_state['_customer_return_cart']),2)
            token=app.session_state['_customer_return_cart'][1]['item']['request_token']
            app.multiselect[0].set_value([token]).run()
            next(b for b in app.button if b.label=='선택 제품 빼기').click().run()
            self.assertEqual(len(app.session_state['_customer_return_cart']),1)
            next(w for w in app.text_input if w.label=='제품 검색').set_value('검색결과없음').run()
            next(w for w in app.text_input if w.label=='반품 사유 / 메모').set_value('함께 입고')
            next(b for b in app.button if b.label=='반품 입고 완료').click().run()
            self.assertFalse(app.exception)
            self.assertEqual(self.stock(),23)
            self.assertEqual(returns.receipt_history()[0]['memo'],'함께 입고')
            self.assertEqual(app.session_state['_customer_return_cart'],[])


    def test_order_grouping_uses_item_order_and_only_returns(self):
        with closing(sqlite3.connect(self.purchase)) as con:
            con.executescript("""
                ALTER TABLE statements ADD COLUMN order_id TEXT;
                ALTER TABLE statement_items ADD COLUMN source_order_id TEXT;
                CREATE TABLE orders(order_id TEXT,ordered_at TEXT);
                INSERT INTO orders VALUES('O1','2026-08-01'),('O2','2026-08-02');
                UPDATE statements SET order_id='O1';
                INSERT INTO statement_items VALUES('S1',2,'P2','제품2','EA','L2','2028-02-01','반품:2:20:time','O2');
                INSERT INTO statement_items VALUES('S1',3,'P3','반품아님','EA','L3','2028-02-01','', 'O1');
            """)
        rows=returns.statement_sources()
        self.assertEqual([(r['purchase_order_id'],r['purchase_order_date']) for r in rows],[('O1','2026-08-01'),('O2','2026-08-02')])
    def test_mapping_update_preserves_other_company_and_codes(self):
        item=self.basket_item(kind='statement')
        item.update(mapping_name='수정 팜 제품명',mapping_before=['델가다 5V'])
        returns.receive_returns([item],location='REC')
        with self.connect() as con:
            self.assertEqual(con.execute('SELECT erp_nohtuspharm_name,erp_nohtus_name,product_code FROM products WHERE id=1').fetchone(),('수정 팜 제품명','노투스 델가다','P1'))
            self.assertEqual(con.execute('SELECT warehouse_name FROM inventory WHERE id=1').fetchone()[0],'델가다 5V')
        self.assertEqual(returns.receipt_history()[0]['warehouse_name'],'수정 팜 제품명')
    def test_mapping_changes_roll_back_with_invalid_basket(self):
        item=self.basket_item(kind='statement');item.update(mapping_name='새 이름',mapping_before=['델가다 5V'])
        bad=self.basket_item(qty=99,token='bad')
        with self.assertRaises(ValueError):returns.receive_returns([item,bad],location='REC')
        with self.connect() as con:self.assertEqual(con.execute('SELECT erp_nohtuspharm_name FROM products WHERE id=1').fetchone()[0],'델가다 5V')
        self.assertEqual(self.stock(),20)
    def test_mapping_conflicts_rejected(self):
        first=self.basket_item(kind='statement');first.update(mapping_name='새 이름',mapping_before=['델가다 5V'])
        second=dict(first,request_token='two',mapping_name='다른 이름')
        with self.assertRaises(ValueError):returns.receive_returns([first,second],location='REC')
        with self.connect() as con:con.execute("UPDATE products SET erp_nohtuspharm_name='다른 사람이 수정'")
        with self.assertRaises(ValueError):returns.receive_returns([first],location='REC')
        self.assertEqual(self.stock(),20)
    def test_checked_rows_use_statement_quantity_without_outbound_link(self):
        from nohtus.pages import customer_returns as page
        sources=[self.source('statement')]
        records=page._statement_table_rows(sources,'노투스팜')
        with self.assertRaises(ValueError):page._prepare_statement_selection(sources,records,'노투스팜')
        records[0].update({'선택':True,'WMS 표준제품명':'델가다 (5EA)','연결 제품명':'델가다 5V','입고수량':2})
        outbound=self.source()
        prepared=page._prepare_statement_selection(sources,records,'노투스팜')
        self.assertIsNone(prepared[0]['item']['outbound_key'])
        self.assertEqual(prepared[0]['item']['factor'],'1')
        self.assertEqual(prepared[0]['qty'],2)
        self.assertEqual(prepared[0]['item']['mapping_before'],['델가다 5V'])


    def test_new_mapping_initializes_standard_warehouse_name(self):
        with self.connect() as con:con.execute('ALTER TABLE products ADD COLUMN warehouse_name TEXT')
        item=self.basket_item(kind='statement',company='비자료')
        item.update(product_name='신규 입고명',mapping_name='비자료 신규명',mapping_before=[])
        returns.receive_returns([item],location='REC')
        with self.connect() as con:
            self.assertEqual(con.execute("SELECT warehouse_name,bidata_name FROM products WHERE standard_name='신규 입고명'").fetchone(),('신규 입고명','비자료 신규명'))
    def test_multi_row_check_selection_preserves_unchecked_mapping(self):
        from nohtus.pages import customer_returns as page
        first=self.source('statement');second=dict(first,source_key='second',product_name='체크 안 한 제품')
        records=page._statement_table_rows([first,second],'노투스팜')
        records[0].update({'선택':True,'연결 제품명':'팜 연결명'})
        prepared=page._prepare_statement_selection([first,second],records,'노투스팜')
        self.assertEqual(len(prepared),1)
        returns.receive_returns([r['item'] for r in prepared],location='REC')
        with self.connect() as con:self.assertIsNone(con.execute("SELECT id FROM products WHERE standard_name='체크 안 한 제품'").fetchone())


    def test_ui_select_all_clear_preserves_edits_without_outbound_lookup(self):
        from streamlit.testing.v1 import AppTest
        from nohtus.pages import customer_returns as page
        with closing(sqlite3.connect(self.purchase)) as con:
            con.execute("INSERT INTO statement_items VALUES('S1',2,'P2','제품2','EA','L2','2028-02-01','반품:2:20:time')");con.commit()
        with patch.object(page,'can_access_page',return_value=True),patch.object(returns,'outbound_sources',side_effect=AssertionError('Must not query WMS outbound')):
            code="import streamlit as st\nfrom nohtus.pages.customer_returns import page_customer_returns\nst.session_state.setdefault('_customer_return_mode','거래명세서 반품')\npage_customer_returns()"
            app=AppTest.from_string(code).run()
            next(w for w in app.selectbox if w.label=='반품할 주문').select('statement:S1').run()
            self.assertFalse(app.exception)
            self.assertNotIn('환산계수',app.dataframe[0].value.columns)
            self.assertNotIn('원출고',app.dataframe[0].value.columns)
            editor=next(k for k in app.session_state.filtered_state if k.startswith('return_order_editor_'))
            app.session_state[editor]={'edited_rows':{0:{'연결 제품명':'변경된 이름','입고수량':1}},'added_rows':[],'deleted_rows':[]}
            next(b for b in app.button if b.label=='모두 선택').click().run()
            self.assertTrue(app.dataframe[0].value['선택'].all())
            self.assertEqual(app.dataframe[0].value['연결 제품명'].iloc[0],'변경된 이름')
            next(b for b in app.button if b.label=='선택 해제').click().run()
            self.assertFalse(app.dataframe[0].value['선택'].any())
            next(b for b in app.button if b.label=='모두 선택').click().run()
            next(b for b in app.button if b.label=='선택 제품 장바구니에 담기').click().run()
            self.assertFalse(app.exception)
            cart=app.session_state['_customer_return_cart']
            self.assertEqual(len(cart),2)
            self.assertEqual([r['qty'] for r in cart],[1,2])
            next(b for b in app.button if b.label=='반품 입고 완료').click().run()
            self.assertFalse(app.exception);self.assertEqual(self.stock(),23)


    def test_bulk_cancel_atomic_success_and_failure(self):
        first=self.receive(2,token='one')
        second=self.receive(3,token='two',company='비자료')
        with self.connect() as con:con.execute("UPDATE inventory SET qty=0 WHERE company='비자료'")
        with self.assertRaises(ValueError):returns.cancel_returns([first,second])
        self.assertTrue(all(r['status']=='received' for r in returns.receipt_history()))
        with self.connect() as con:
            self.assertEqual(con.execute("SELECT qty FROM inventory WHERE company='노투스팜'").fetchone()[0],22)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM transactions WHERE tx_type='반품입고취소'").fetchone()[0],0)
            con.execute("UPDATE inventory SET qty=3 WHERE company='비자료'")
        returns.cancel_returns([first,second])
        self.assertEqual(self.stock(),20)
        self.assertTrue(all(r['status']=='cancelled' for r in returns.receipt_history()))
        self.assertEqual(self.source()['remaining_qty'],10)


    def test_history_delete_return_with_reversal(self):
        from nohtus.pages import history
        self.receive(3)
        tx=returns.receipt_history()[0]['transaction_id']
        with patch.object(history,'connect',self.connect):self.assertEqual(history._delete_transaction_ids([tx]),1)
        self.assertEqual(self.stock(),20)
        self.assertEqual(self.source()['remaining_qty'],10)
        self.assertEqual(returns.receipt_history()[0]['status'],'cancelled')
        self.assertIsNone(returns.receipt_history()[0]['transaction_id'])
    def test_history_log_only_preserves_stock_and_receipt_state(self):
        from nohtus.pages import history
        receipt=self.receive(3)
        with patch.object(history,'connect',self.connect):
            history._delete_transaction_ids_without_reversal([returns.receipt_history()[0]['transaction_id']])
            self.assertEqual(self.stock(),23)
            self.assertEqual(self.source()['remaining_qty'],7)
            returns.cancel_return(receipt)
            history._delete_transaction_ids_without_reversal([returns.receipt_history()[0]['cancel_transaction_id']])
        self.assertEqual(self.stock(),20)
        self.assertEqual(returns.receipt_history()[0]['status'],'cancelled')
        self.assertIsNone(returns.receipt_history()[0]['cancel_transaction_id'])
    def test_history_reverse_cancel_restores_receipt(self):
        from nohtus.pages import history
        receipt=self.receive(3);returns.cancel_return(receipt)
        with patch.object(history,'connect',self.connect):history._delete_transaction_ids([returns.receipt_history()[0]['cancel_transaction_id']])
        self.assertEqual(self.stock(),23)
        self.assertEqual(returns.receipt_history()[0]['status'],'received')
        self.assertEqual(self.source()['remaining_qty'],7)
        returns.cancel_return(receipt)
        self.assertEqual(self.stock(),20)
    def test_history_reverse_pair_and_reject_original_alone(self):
        from nohtus.pages import history
        receipt=self.receive(3);returns.cancel_return(receipt)
        row=returns.receipt_history()[0]
        with patch.object(history,'connect',self.connect):
            with self.assertRaises(ValueError):history._delete_transaction_ids([row['transaction_id']])
            self.assertEqual(history._delete_transaction_ids([row['transaction_id'],row['cancel_transaction_id']]),2)
        self.assertEqual(self.stock(),20)
        self.assertEqual(self.source()['remaining_qty'],10)
    def test_history_reverse_cancel_cannot_exceed_return_cap(self):
        from nohtus.pages import history
        receipt=self.receive(8);returns.cancel_return(receipt)
        cancel_tx=returns.receipt_history()[0]['cancel_transaction_id']
        self.receive(8,token='again')
        with patch.object(history,'connect',self.connect):
            with self.assertRaises(ValueError):history._delete_transaction_ids([cancel_tx])
        self.assertEqual(self.stock(),28)
    def test_history_reverse_return_failure_rolls_back_ledger(self):
        from nohtus.pages import history
        self.receive(3);tx=returns.receipt_history()[0]['transaction_id']
        with self.connect() as con:con.execute('UPDATE inventory SET qty=0')
        with patch.object(history,'connect',self.connect):
            with self.assertRaises(ValueError):history._delete_transaction_ids([tx])
        self.assertEqual(returns.receipt_history()[0]['status'],'received')
        self.assertEqual(returns.receipt_history()[0]['transaction_id'],tx)


    def test_history_negative_reversal_is_blocked(self):
        from nohtus.pages import history
        self.receive(3);tx=returns.receipt_history()[0]['transaction_id']
        with self.connect() as con:con.execute('UPDATE inventory SET qty=1')
        with patch.object(history,'connect',self.connect):
            with self.assertRaises(ValueError):history._delete_transaction_ids([tx])
        self.assertEqual(self.stock(),1)
        self.assertEqual(returns.receipt_history()[0]['status'],'received')
        self.assertEqual(returns.receipt_history()[0]['transaction_id'],tx)
    def test_history_reversal_cannot_create_negative_stock_row(self):
        from nohtus.pages import history
        self.receive(3);tx=returns.receipt_history()[0]['transaction_id']
        with self.connect() as con:con.execute('DELETE FROM inventory')
        with patch.object(history,'connect',self.connect):
            with self.assertRaises(ValueError):history._delete_transaction_ids([tx])
        with self.connect() as con:self.assertEqual(con.execute('SELECT COUNT(*) FROM inventory').fetchone()[0],0)
        self.assertEqual(returns.receipt_history()[0]['status'],'received')

if __name__=='__main__':unittest.main()
