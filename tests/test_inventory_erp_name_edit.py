import sqlite3
from contextlib import contextmanager
from unittest.mock import patch
import pytest
from nohtus.pages import stocktake as page

@pytest.fixture
def db(tmp_path):
    path=tmp_path/'test.db'
    @contextmanager
    def connect():
        c=sqlite3.connect(path)
        try:
            with c:yield c
        finally:c.close()
    with connect() as c:
        c.executescript("""
        CREATE TABLE products(id INTEGER PRIMARY KEY,standard_name TEXT,warehouse_name TEXT,erp_nohtuspharm_name TEXT,product_code TEXT);
        CREATE TABLE inventory(id INTEGER PRIMARY KEY,company TEXT,product_name TEXT,warehouse_name TEXT,lot TEXT,exp_date TEXT,location TEXT,qty INTEGER,updated_at TEXT);
        CREATE TABLE transactions(id INTEGER PRIMARY KEY,created_at TEXT,actor TEXT,tx_type TEXT,product_name TEXT,warehouse_name TEXT,lot TEXT,exp_date TEXT,from_company TEXT,from_location TEXT,to_company TEXT,to_location TEXT,qty INTEGER,memo TEXT,final_stock INTEGER);
        CREATE TABLE customer_return_receipts(id INTEGER PRIMARY KEY,inventory_id INTEGER,transaction_id INTEGER,warehouse_name TEXT,status TEXT);
        CREATE TABLE export_waiting_items(id INTEGER PRIMARY KEY,source_inventory_id INTEGER,waiting_inventory_id INTEGER,warehouse_name TEXT,confirmed INTEGER);
        INSERT INTO products VALUES(1,'히야론','히야론','Wonderfit','P1');
        INSERT INTO inventory VALUES(1,'노투스팜','히야론','Wonderfit','L1','2028-01-01','REC',7,'');
        INSERT INTO inventory VALUES(2,'노투스팜','히야론','Wonderfit','L1','2028-01-01','A1-01-01',8,'');
        INSERT INTO customer_return_receipts VALUES(1,1,NULL,'Wonderfit','received');
        """)
    with patch.object(page,'connect',connect):yield connect

def test_changes_only_selected_name_and_preserves_mappings(db):
    with db() as c:before=c.execute('SELECT id,company,product_name,lot,exp_date,location,qty FROM inventory ORDER BY id').fetchall()
    page._update_selected_inventory_erp_name(1,'히야론','Wonderfit')
    with db() as c:
        assert c.execute('SELECT id,company,product_name,lot,exp_date,location,qty FROM inventory ORDER BY id').fetchall()==before
        assert c.execute('SELECT warehouse_name FROM inventory ORDER BY id').fetchall()==[('히야론',),('Wonderfit',)]
        assert c.execute('SELECT erp_nohtuspharm_name FROM products ORDER BY id').fetchall()==[('Wonderfit',),('히야론',)]
        assert c.execute('SELECT product_code FROM products WHERE id=1').fetchone()==('P1',)
        assert c.execute('SELECT warehouse_name FROM customer_return_receipts').fetchone()==('히야론',)
        assert c.execute('SELECT qty,tx_type FROM transactions').fetchone()==(0,'재고정보수정')

def test_stale_name_rejected_and_no_partial_mapping(db):
    with pytest.raises(ValueError):page._update_selected_inventory_erp_name(1,'새 이름','다른 기존명')
    with db() as c:assert c.execute('SELECT COUNT(*) FROM products').fetchone()[0]==1

def test_repeated_save_does_not_duplicate_mapping(db):
    page._update_selected_inventory_erp_name(1,'히야론','Wonderfit')
    page._update_selected_inventory_erp_name(1,'히야론','히야론')
    with db() as c:assert c.execute('SELECT COUNT(*) FROM products').fetchone()[0]==2

def test_linked_export_pair_rejected_atomically(db):
    with db() as c:c.execute("INSERT INTO export_waiting_items VALUES(1,1,2,'Wonderfit',0)")
    with pytest.raises(ValueError):page._update_selected_inventory_erp_name(1,'히야론','Wonderfit')
    with db() as c:assert c.execute('SELECT warehouse_name FROM inventory WHERE id=1').fetchone()==('Wonderfit',)
