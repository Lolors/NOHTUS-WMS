import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from contextlib import contextmanager
import pandas as pd
from nohtus.services import inventory
from nohtus.pages import own_product_status, history

class CompanyCorrectionMoveTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'test.db'
        @contextmanager
        def connect():
            con=sqlite3.connect(self.path)
            try:
                with con: yield con
            finally:con.close()
        self.connect=connect
        with connect() as con:
            con.executescript('''CREATE TABLE inventory(id INTEGER PRIMARY KEY,company TEXT,product_name TEXT,warehouse_name TEXT,lot TEXT,exp_date TEXT,location TEXT,qty INTEGER,updated_at TEXT,location_range_cells TEXT);
            CREATE TABLE transactions(id INTEGER PRIMARY KEY,created_at TEXT,actor TEXT,tx_type TEXT,product_name TEXT,warehouse_name TEXT,lot TEXT,exp_date TEXT,from_company TEXT,from_location TEXT,to_company TEXT,to_location TEXT,qty INTEGER,memo TEXT,final_stock INTEGER);
            INSERT INTO inventory VALUES(1,'비자료','바이리쥬 2ml','바이리쥬 2ml','L1','2028-01-01','A1-01-01',5,'',NULL);''')
        def query(sql,params=()):
            with connect() as con:return pd.read_sql_query(sql,con,params=params)
        self.patches=[patch.object(inventory,'connect',connect),patch.object(inventory,'product_mapping_name_for',return_value='바이리쥬 2ml'),patch.object(inventory,'_current_actor',return_value='test'),patch.object(own_product_status,'q',query)]
        for p in self.patches:p.start()
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()
    def delta(self):return own_product_status._today_delta_map()[('노투스팜','바이리쥬 2ml')]
    def test_correction_moves_stock_and_records_history_but_excludes_delta(self):
        inventory.move_inventory(1,'노투스팜','A1-02-01',5,'소속 오류',company_correction=True)
        with self.connect() as con:
            self.assertEqual(con.execute('SELECT qty FROM inventory ORDER BY id').fetchall(),[(0,),(5,)])
            self.assertEqual(con.execute('SELECT tx_type,qty,final_stock,memo FROM transactions').fetchone(),('사업장정정',5,5,'소속 오류'))
        self.assertEqual(self.delta(),0)
        self.assertEqual(inventory._transaction_stock_delta('사업장정정',5,'비자료','노투스팜'),5)
    def test_normal_move_still_counts(self):
        inventory.move_inventory(1,'노투스팜','A1-02-01',5)
        self.assertEqual(self.delta(),5)
    def test_same_company_correction_is_rejected_without_writes(self):
        with self.assertRaises(ValueError):inventory.move_inventory(1,'비자료','A1-02-01',5,company_correction=True)
        with self.connect() as con:
            self.assertEqual(con.execute('SELECT qty FROM inventory').fetchone()[0],5)
            self.assertEqual(con.execute('SELECT count(*) FROM transactions').fetchone()[0],0)
    def test_history_reversal_recognizes_correction(self):
        inventory.move_inventory(1,'노투스팜','A1-02-01',5,company_correction=True)
        with self.connect() as con:
            con.row_factory=sqlite3.Row
            tx=dict(con.execute('SELECT * FROM transactions').fetchone())
            con.row_factory=None
            with patch.object(history,'_resolved_inventory_warehouse_name',return_value='바이리쥬 2ml'):
                history._reverse_transaction(con.cursor(),tx)
            self.assertEqual(con.execute('SELECT qty FROM inventory ORDER BY id').fetchall(),[(5,),(0,)])
    def test_linked_export_move_receives_correction_flag(self):
        with patch('nohtus.services.export_waiting_move.move_linked_stock') as linked:
            inventory.move_inventory(1,'노투스팜','P',5,export_order_id=10,company_correction=True)
            self.assertTrue(linked.call_args.kwargs['company_correction'])

if __name__=='__main__':unittest.main()
