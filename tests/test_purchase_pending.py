"""실제 SQLite 임시 DB에서 매입대기/완료의 재고와 매칭 원자성 검증."""
import json
from contextlib import closing
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from nohtus import db
from nohtus.services import purchase_pending as service
from nohtus.services.inventory import add_inventory
from nohtus.pages.location_map import _map_search_product_groups
from nohtus.services.location_map_legacy import _loc_group_from_df


def create_test_db(path):
    with closing(sqlite3.connect(path)) as con:
        con.executescript('''
        CREATE TABLE products(id INTEGER PRIMARY KEY, standard_name TEXT, warehouse_name TEXT,
            product_code TEXT, aliases TEXT, erp_nohtuspharm_name TEXT, erp_nohtus_name TEXT,
            erp_noh_name TEXT, erp_noh_code TEXT, bidata_name TEXT, image_path TEXT,
            is_material INTEGER DEFAULT 0, material_type TEXT);
        CREATE TABLE inventory(id INTEGER PRIMARY KEY, company TEXT, product_name TEXT, warehouse_name TEXT,
            lot TEXT, exp_date TEXT, location TEXT, qty INTEGER, updated_at TEXT,
            location_range_cells TEXT, location_range_end TEXT, is_shippable INTEGER DEFAULT 1);
        CREATE UNIQUE INDEX inventory_key ON inventory(company,product_name,warehouse_name,lot,exp_date,location);
        CREATE TABLE transactions(id INTEGER PRIMARY KEY, created_at TEXT,actor TEXT,tx_type TEXT,
            product_name TEXT,warehouse_name TEXT,lot TEXT,exp_date TEXT,from_company TEXT,from_location TEXT,
            to_company TEXT,to_location TEXT,qty INTEGER,memo TEXT,final_stock INTEGER);
        ''')


class PurchasePendingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'test.db'
        create_test_db(self.path)
        self.db_patch = patch.object(db, 'DB_PATH', self.path)
        self.db_patch.start()
        self.actor_patch = patch.object(service, '_current_actor', return_value='tester')
        self.actor_patch.start()
        self.log_actor_patch = patch('nohtus.services.inventory._current_actor', return_value='tester')
        self.log_actor_patch.start()

    def tearDown(self):
        self.log_actor_patch.stop()
        self.actor_patch.stop()
        self.db_patch.stop()
        self.temp.cleanup()

    def register(self, **kwargs):
        data = dict(product='제품A', lot='LOT1', exp='2028-01-01', location='A1-01-01', qty=12,
                    inbound_date='2026-09-30', supplier='매입처A', memo='보관',
                    location_range_cells=['A1-02-01'])
        data.update(kwargs)
        return service.register_pending(**data)

    def read(self, sql, args=()):
        with db.connect() as con:
            return con.execute(sql,args).fetchall()

    def test_empty_read_does_not_create_pending_table(self):
        self.assertTrue(service.pending_rows().empty)
        self.assertEqual(self.read("SELECT name FROM sqlite_master WHERE name='purchase_pending'"), [])

    def test_cancel_excludes_only_selected_row_and_keeps_audit_without_stock_changes(self):
        selected=self.register()
        other=self.register()
        add_inventory('NOH','제품A','ERP','LOT1','2028-01-01','REC',5)
        before_stock=self.read('SELECT * FROM inventory')
        before_history=self.read('SELECT * FROM transactions')
        before_products=self.read('SELECT * FROM products')
        service.cancel_pending(selected)
        self.assertEqual(service.pending_rows()['id'].tolist(),[other])
        self.assertEqual(service.map_pending_rows()['id'].tolist(),[-other])
        self.assertEqual(self.read('SELECT pending_id,cancelled_by FROM purchase_pending_cancellations'),[(selected,'tester')])
        self.assertEqual(self.read('SELECT COUNT(*) FROM purchase_pending'),[(2,)])
        self.assertEqual(self.read('SELECT * FROM inventory'),before_stock)
        self.assertEqual(self.read('SELECT * FROM transactions'),before_history)
        self.assertEqual(self.read('SELECT * FROM products'),before_products)
        with self.assertRaises(ValueError):
            service.cancel_pending(selected)
        with self.assertRaises(ValueError):
            service.complete_pending(selected,'NOH','ERP')

    def test_completed_row_cannot_be_cancelled(self):
        selected=self.register()
        service.complete_pending(selected,'NOH','ERP')
        with self.assertRaises(ValueError):
            service.cancel_pending(selected)
        self.assertEqual(self.read('SELECT SUM(qty) FROM inventory'),[(12,)])

    def test_cancel_and_complete_race_has_one_winner(self):
        selected=self.register()
        def perform(action):
            try:
                if action=='cancel': service.cancel_pending(selected)
                else: service.complete_pending(selected,'NOH','ERP')
                return action
            except ValueError:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes=list(pool.map(perform,['cancel','complete']))
        winners=[x for x in outcomes if x]
        self.assertEqual(len(winners),1)
        self.assertTrue(service.pending_rows().empty)
        self.assertEqual(self.read('SELECT COALESCE(SUM(qty),0) FROM inventory')[0][0],12 if winners[0]=='complete' else 0)

    def test_catalog_search_loads_company_specific_paired_name_and_code(self):
        self.register()
        with db.connect() as con:
            con.execute("UPDATE products SET erp_nohtuspharm_name='팜 ERP',product_code='P001',erp_noh_name='NOH ERP',erp_noh_code='N002',aliases='별칭' WHERE standard_name='제품A'")
        for company, term, erp, code in [('NOH','N002','NOH ERP','N002'),('노투스팜','별칭','팜 ERP','P001')]:
            found=service.pending_product_catalog(company,term)
            self.assertEqual(len(found),1)
            self.assertEqual((found.iloc[0]['erp_name'],found.iloc[0]['product_code']),(erp,code))
        self.assertTrue(service.pending_product_catalog('NOH','P001').empty)
        self.assertTrue(service.pending_product_catalog(None).empty)

    def test_selected_matching_row_preserves_duplicate_erp_codes(self):
        selected=self.register()
        with db.connect() as con:
            con.execute("UPDATE products SET erp_noh_name='같은 ERP',erp_noh_code='N001'")
            con.execute("INSERT INTO products(standard_name,erp_noh_name,erp_noh_code) VALUES('제품A','같은 ERP','N002')")
        found=service.pending_product_catalog('NOH','N002').iloc[0]
        service.complete_pending(selected,'NOH','같은 ERP','N002',standard_name='제품A',mapping_id=int(found['id']))
        self.assertEqual(self.read('SELECT erp_noh_code FROM products ORDER BY id'), [('N001',),('N002',)])

    def test_changed_selected_mapping_is_rejected_without_completing(self):
        selected=self.register()
        with db.connect() as con:
            con.execute("UPDATE products SET erp_noh_name='ERP',erp_noh_code='N001'")
        found=service.pending_product_catalog('NOH').iloc[0]
        with self.assertRaisesRegex(ValueError,'제품코드가 변경'):
            service.complete_pending(selected,'NOH','ERP','N002',mapping_id=int(found['id']))
        self.assertEqual(len(service.pending_rows()),1)
        self.assertEqual(self.read('SELECT COUNT(*) FROM inventory'),[(0,)])

    def test_pending_creates_standard_only_and_not_inventory_or_history(self):
        self.register()
        self.assertEqual(self.read('SELECT count(*) FROM inventory')[0][0], 0)
        self.assertEqual(self.read('SELECT count(*) FROM transactions')[0][0], 0)
        self.assertEqual(self.read('SELECT standard_name,erp_nohtuspharm_name,erp_nohtus_name,erp_noh_name,bidata_name FROM products'),
                         [('제품A','','','','')])
        self.assertEqual(len(service.pending_rows()), 1)

    def test_each_company_completion_preserves_details_and_registers_once(self):
        for company in ['노투스팜','노투스','NOH','비자료']:
            pending_id=self.register()
            inv_id=service.complete_pending(pending_id, company, company+' ERP')
            self.assertEqual(self.read('SELECT company,product_name,warehouse_name,lot,exp_date,location,qty FROM inventory WHERE id=?',(inv_id,)),
                             [(company,'제품A',company+' ERP','LOT1','2028-01-01','A1-01-01',12)])
            with self.assertRaisesRegex(ValueError,'이미'):
                service.complete_pending(pending_id, company, company+' ERP')
        self.assertTrue(service.pending_rows().empty)
        self.assertEqual(self.read('SELECT SUM(qty) FROM inventory')[0][0],48)
        self.assertEqual(self.read('SELECT COUNT(*),SUM(qty) FROM transactions')[0],(4,48))
        self.assertEqual(self.read('SELECT DISTINCT final_stock FROM transactions'),[(12,)])

    def test_double_submit_and_concurrent_completion(self):
        pending_id=self.register(request_token='one-submit')
        self.assertEqual(self.register(request_token='one-submit'),pending_id)
        def complete(_):
            try:
                service.complete_pending(pending_id,'NOH','ERP A')
                return True
            except ValueError:
                return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(complete,range(2))),[False,True])
        self.assertEqual(self.read('SELECT SUM(qty) FROM inventory')[0][0],12)

    def test_invalid_inputs_leave_pending_and_stock_untouched(self):
        pending_id=self.register()
        for company,erp in [('등록대기','ERP'),('NOH','')]:
            with self.assertRaises(ValueError):
                service.complete_pending(pending_id,company,erp)
        self.assertEqual(len(service.pending_rows()),1)
        self.assertEqual(self.read('SELECT COUNT(*) FROM inventory')[0][0],0)
        for qty in [0,-1,1.5,float('nan')]:
            with self.assertRaises(ValueError):
                self.register(qty=qty)

    def test_failure_rolls_back_mapping_inventory_and_status(self):
        pending_id=self.register()
        with patch.object(service,'insert_transaction_log',side_effect=RuntimeError('test failure')):
            with self.assertRaises(RuntimeError):
                service.complete_pending(pending_id,'노투스','새 ERP')
        self.assertEqual(self.read('SELECT erp_nohtus_name FROM products'),[('',)])
        self.assertEqual(self.read('SELECT COUNT(*) FROM inventory')[0][0],0)
        self.assertEqual(len(service.pending_rows()),1)

    def test_existing_erp_mapping_not_overwritten_and_stock_merges_ranges(self):
        first=self.register()
        service.complete_pending(first,'NOH','기존 ERP','C1')
        second=self.register(location_range_cells=['A1-03-01'])
        service.complete_pending(second,'NOH','기존 ERP')
        self.assertEqual(self.read('SELECT qty FROM inventory'),[(24,)])
        cells=json.loads(self.read('SELECT location_range_cells FROM inventory')[0][0])
        self.assertEqual(set(cells),{'A1-01-01','A1-02-01','A1-03-01'})
        third=self.register()
        service.complete_pending(third,'NOH','다른 ERP')
        self.assertEqual(set(self.read('SELECT erp_noh_name FROM products')),{('기존 ERP',),('다른 ERP',)})
        self.assertEqual(self.read("SELECT erp_noh_code FROM products WHERE erp_noh_name='기존 ERP'"),[('C1',)])

    def test_pending_occupies_map_but_not_stock_total_and_disappears_after_completion(self):
        pending_id=self.register()
        add_inventory('NOH','제품A','ERP A','LOT1','2028-01-01','A1-01-01',5)
        pending=service.map_pending_rows()
        locations=_loc_group_from_df(pending)
        self.assertEqual(set(locations),{'A1-01-01','A1-02-01'})
        self.assertTrue(locations['A1-01-01'][0]['is_purchase_pending'])
        self.assertLess(locations['A1-01-01'][0]['id'],0)
        with db.connect() as con:
            stock=pd.read_sql_query('SELECT * FROM inventory',con)
        groups=_map_search_product_groups('제품A',pd.concat([stock,pending],ignore_index=True))
        self.assertEqual(groups[0]['total_qty'],5)
        self.assertEqual(groups[0]['pending_rows']['qty'].sum(),12)
        self.assertEqual(_map_search_product_groups('제품A',pending)[0]['total_qty'],0)
        service.complete_pending(pending_id,'NOH','ERP A')
        self.assertTrue(service.map_pending_rows().empty)
        self.assertEqual(self.read('SELECT SUM(qty) FROM inventory')[0][0],17)

    def test_edited_name_applies_only_to_selected_pending_and_new_stock(self):
        selected = self.register()
        other = self.register()
        add_inventory('NOH', '제품A', '기존 ERP', 'LOT1', '2028-01-01', 'A1-01-01', 5)
        service.complete_pending(selected, 'NOH', '수정 ERP', standard_name='수정 제품')
        self.assertEqual(self.read('SELECT product_name,status FROM purchase_pending WHERE id=?', (selected,)), [('수정 제품','completed')])
        self.assertEqual(self.read('SELECT product_name,status FROM purchase_pending WHERE id=?', (other,)), [('제품A','pending')])
        self.assertEqual(set(self.read('SELECT product_name,qty FROM inventory')), {('제품A',5),('수정 제품',12)})
        tx = self.read('SELECT product_name,memo FROM transactions ORDER BY id DESC LIMIT 1')[0]
        self.assertEqual(tx[0], '수정 제품')
        self.assertIn('대기 등록명: 제품A', tx[1])

    def test_renamed_completion_failure_rolls_back_everything(self):
        selected = self.register()
        with patch.object(service,'insert_transaction_log',side_effect=RuntimeError('test failure')):
            with self.assertRaises(RuntimeError):
                service.complete_pending(selected,'NOH','새 ERP',standard_name='수정 제품')
        self.assertEqual(self.read('SELECT product_name,status FROM purchase_pending'), [('제품A','pending')])
        self.assertEqual(self.read("SELECT COUNT(*) FROM products WHERE standard_name='수정 제품'"), [(0,)])
        self.assertEqual(self.read('SELECT COUNT(*) FROM inventory'), [(0,)])
        with self.assertRaisesRegex(ValueError,'표준제품명'):
            service.complete_pending(selected,'NOH','새 ERP',standard_name='  ')

    def test_renaming_to_existing_product_merges_stock_without_changing_other_mapping(self):
        first = self.register(product='기존 제품')
        service.complete_pending(first,'NOH','기존 ERP')
        selected = self.register()
        service.complete_pending(selected,'NOH','기존 ERP',standard_name='기존 제품')
        self.assertEqual(self.read('SELECT product_name,qty FROM inventory'), [('기존 제품',24)])
        selected = self.register()
        with self.assertRaisesRegex(ValueError,'다른 표준제품명'):
            service.complete_pending(selected,'NOH','기존 ERP',standard_name='충돌 제품')
        self.assertEqual(self.read('SELECT product_name,status FROM purchase_pending WHERE id=?',(selected,)), [('제품A','pending')])


if __name__ == '__main__':
    unittest.main()
