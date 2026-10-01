"""Customer returns: atomic inventory receipt with source limits and an audit trail."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from contextlib import closing
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from nohtus.config import AREA_CONFIG, COMPANIES, PROJECT_ROOT, SPECIAL_LOCATIONS
from nohtus.db import connect
from nohtus.locations import make_location
from nohtus.services.inbound import _mapping_column_for_company
from nohtus.services.inventory import _current_actor, insert_transaction_log

TABLE = 'customer_return_receipts'
COMPANY = '노투스팜'


def purchase_db_path():
    return Path(os.environ.get('NOHTUS_PURCHASE_DB_PATH') or PROJECT_ROOT / 'order_management_src/data/purchase_order.db')


def _text(value):
    return str(value or '').strip()


def _positive(value, label='수량'):
    try:
        number = Decimal(str(value))
        if not number.is_finite() or number <= 0:
            raise ValueError
        return number
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f'{label}은 0보다 큰 숫자여야 합니다.')


def _qty(value):
    number = _positive(value)
    if number != number.to_integral_value():
        raise ValueError('입고수량은 정수여야 합니다.')
    return int(number)


def _rows(con, sql, params=()):
    cur = con.execute(sql, params)
    names = [d[0] for d in cur.description]
    return [dict(zip(names, row)) for row in cur.fetchall()]


def _exists(con):
    return bool(con.execute("SELECT 1 FROM sqlite_master WHERE name=? AND type='table'", (TABLE,)).fetchone())


def _ensure(con):
    con.execute(f'''CREATE TABLE IF NOT EXISTS {TABLE} (
        id INTEGER PRIMARY KEY, request_token TEXT NOT NULL UNIQUE,
        source_kind TEXT NOT NULL, source_key TEXT NOT NULL, source_fingerprint TEXT NOT NULL,
        source_snapshot TEXT NOT NULL, outbound_key TEXT, outbound_order_id INTEGER,
        statement_id TEXT, statement_sequence INTEGER,
        product_name TEXT NOT NULL, lot TEXT NOT NULL, exp_date TEXT NOT NULL,
        source_qty INTEGER NOT NULL, conversion_factor TEXT NOT NULL, qty INTEGER NOT NULL CHECK(qty>0),
        company TEXT NOT NULL, warehouse_name TEXT NOT NULL, location TEXT NOT NULL,
        inventory_id INTEGER NOT NULL, transaction_id INTEGER, receipt_date TEXT NOT NULL,
        memo TEXT NOT NULL, created_at TEXT NOT NULL, actor TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'received', cancelled_at TEXT, cancel_transaction_id INTEGER
    )''')
    con.execute(f'CREATE INDEX IF NOT EXISTS customer_return_source ON {TABLE}(source_kind,source_key,status)')
    con.execute(f'CREATE INDEX IF NOT EXISTS customer_return_outbound ON {TABLE}(outbound_key,status)')


def _hash(parts):
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def outbound_sources(con=None, *, customer='', product='', start=None, end=None):
    if con is None:
        with connect() as db:
            return outbound_sources(db, customer=customer, product=product, start=start, end=end)
    columns = {r[1] for r in con.execute('PRAGMA table_info(outbound_orders)')}
    customer_sql = "COALESCE(NULLIF(TRIM(o.customer_name),''),o.title)" if 'customer_name' in columns else 'o.title'
    rows = _rows(con, f'''SELECT o.id AS order_id,o.order_date,o.title,{customer_sql} AS customer,
        i.company,i.product_name,COALESCE(NULLIF(i.lot,''),'-') AS lot,
        COALESCE(NULLIF(i.exp_date,''),'-') AS exp_date,SUM(i.qty) AS total_qty
        FROM outbound_orders o JOIN outbound_order_items i ON i.order_id=o.id
        WHERE COALESCE(o.status,'') NOT IN ('취소됨','취소')
        GROUP BY o.id,i.company,i.product_name,COALESCE(NULLIF(i.lot,''),'-'),COALESCE(NULLIF(i.exp_date,''),'-')
        HAVING SUM(i.qty)>0 ORDER BY o.order_date DESC,o.id DESC''')
    received = {}
    if _exists(con):
        received = dict(con.execute(f"SELECT outbound_key,SUM(qty) FROM {TABLE} WHERE status='received' GROUP BY outbound_key").fetchall())
    result = []
    for row in rows:
        if customer.casefold() not in _text(row['customer']).casefold() or product.casefold() not in _text(row['product_name']).casefold():
            continue
        day = _text(row['order_date'])[:10]
        if (start and day < str(start)) or (end and day > str(end)):
            continue
        key = _hash([row[k] for k in ('order_id','company','product_name','lot','exp_date')])
        row.update(source_kind='outbound',source_key=key,fingerprint=key)
        row['returned_qty'] = int(received.get(key,0))
        row['remaining_qty'] = max(0,int(row['total_qty'])-row['returned_qty'])
        result.append(row)
    return result


def _outbound_received(con, key):
    if not _exists(con):
        return 0
    return int(con.execute(f"SELECT COALESCE(SUM(qty),0) FROM {TABLE} WHERE outbound_key=? AND status='received'",(key,)).fetchone()[0])


def _statement_rows(con):
    rows = _rows(con, '''SELECT s.statement_id,s.statement_date,s.statement_number,s.vendor_name AS customer,
        i.sequence,i.product_code,i.product_name,i.packaging_unit,i.lot_number AS lot,
        i.expiry_date AS exp_date,i.apply_price
        FROM statements s JOIN statement_items i ON i.statement_id=s.statement_id
        WHERE i.apply_price LIKE '반품:%' ORDER BY s.statement_date DESC,s.statement_id,i.sequence''')
    item_cols={r[1] for r in con.execute('PRAGMA table_info(statement_items)')}
    header_cols={r[1] for r in con.execute('PRAGMA table_info(statements)')}
    primary='s.order_id' if 'order_id' in header_cols else "''"
    origin=f"COALESCE(NULLIF(TRIM(i.source_order_id),''),{primary},'')" if 'source_order_id' in item_cols else primary
    links={(r['statement_id'],r['sequence']):r['order_id'] for r in _rows(con,f'SELECT i.statement_id,i.sequence,{origin} AS order_id FROM statement_items i JOIN statements s ON s.statement_id=i.statement_id')}
    orders={r['order_id']:r['ordered_at'] for r in _rows(con,'SELECT order_id,ordered_at FROM orders')} if con.execute("SELECT 1 FROM sqlite_master WHERE name='orders'").fetchone() else {}
    result=[]
    for row in rows:
        row['purchase_order_id']=_text(links.get((row['statement_id'],row['sequence'])))
        row['purchase_order_date']=orders.get(row['purchase_order_id']) or row['statement_date']

        parts=_text(row['apply_price']).split(':',3)
        try: qty=int(parts[1])
        except (IndexError,ValueError): continue
        if qty<=0: continue
        row['lot']=_text(row['lot']) or '-'; row['exp_date']=_text(row['exp_date']) or '-'
        row.update(source_kind='statement', source_key=json.dumps([row['statement_id'],int(row['sequence'])],ensure_ascii=False), total_qty=qty)
        row['fingerprint']=_hash([row.get(k) for k in ('statement_id','sequence','customer','product_code','product_name','packaging_unit','lot','exp_date')])
        result.append(row)
    return result


def statement_sources(statement_id=None):
    path=purchase_db_path()
    if not path.is_file(): return []
    with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)) as db:
        rows=_statement_rows(db)
    with connect() as con:
        for row in rows:
            row['returned_qty']=source_received(con,'statement',row['source_key'])
            row['remaining_qty']=max(0,row['total_qty']-row['returned_qty'])
    return [r for r in rows if statement_id is None or r['statement_id']==statement_id]


def source_received(con,kind,key):
    if not _exists(con):return 0
    return int(con.execute(f"SELECT COALESCE(SUM(source_qty),0) FROM {TABLE} WHERE source_kind=? AND source_key=? AND status='received'",(kind,key)).fetchone()[0])


def _company_column(company):
    if company not in COMPANIES:
        raise ValueError('유효한 반품 입고 사업장을 선택하세요.')
    return _mapping_column_for_company(company)


def product_catalog(company=COMPANY):
    column = _company_column(company)
    with connect() as con:
        return _rows(con, f"SELECT DISTINCT standard_name,{column} AS erp_name,product_code FROM products WHERE TRIM(COALESCE(standard_name,''))<>'' ORDER BY standard_name")


def receipt_history():
    with connect() as con:
        return _rows(con,f'SELECT * FROM {TABLE} ORDER BY id DESC') if _exists(con) else []


def valid_locations():
    result=set(SPECIAL_LOCATIONS)
    for area,config in AREA_CONFIG.items():
        lines,levels=config.get('lines',[]),config.get('levels',[])
        if lines and levels:
            result.update(make_location(area,line,level) for line in lines for level in levels)
        elif area!='N':result.add(area)
    return result


def receive_return(**item):
    """Receive one item through the same atomic path as a basket."""
    return receive_returns([item])[0]


def receive_returns(items, *, location=None, receipt_date=None, memo=None):
    """Commit the entire basket, or roll back every stock/history change."""
    items=[dict(item) for item in items]
    if not items:
        raise ValueError('반품 입고 목록에 제품을 먼저 담아 주세요.')
    tokens=[item.get('request_token') for item in items]
    if any(not _text(token) for token in tokens) or len(set(tokens))!=len(tokens):
        raise ValueError('반품 입고 요청번호가 없거나 중복됩니다.')
    for item in items:
        if location is not None:item['location']=location
        if receipt_date is not None:item['receipt_date']=receipt_date
        if memo is not None:item['memo']=memo
    with connect() as con:
        if any(item.get('kind')=='statement' for item in items):
            path=purchase_db_path()
            if not path.is_file():raise ValueError('거래명세서 DB를 찾을 수 없습니다.')
            con.execute('ATTACH DATABASE ? AS return_source',(str(path.resolve()),))
            con.set_authorizer(lambda action, arg1, arg2, database, origin:
                sqlite3.SQLITE_DENY if database == 'return_source' and action != sqlite3.SQLITE_READ else sqlite3.SQLITE_OK)
        con.execute('BEGIN IMMEDIATE')
        _ensure(con)
        mapping_requests={}
        for item in items:
            if item.get('mapping_name') is not None:
                identity=(item.get('product_name'),item.get('company',COMPANY))
                name=_text(item['mapping_name'])
                if identity in mapping_requests and mapping_requests[identity]!=name:
                    raise ValueError('같은 표준제품명·사업장의 연결 제품명이 서로 다릅니다.')
                mapping_requests[identity]=name
        return [_receive_return(con,**item) for item in items]


def _receive_return(con, *,kind,key,fingerprint,source_qty,location,request_token,
                   product_name=None,factor='1',outbound_key=None,memo='',receipt_date=None,company=COMPANY,mapping_name=None,mapping_before=None):
    column=_company_column(company)
    qty_in_source=_qty(source_qty); conversion=_positive(factor,'환산계수')
    qty=_qty(Decimal(qty_in_source)*conversion)
    if kind not in ('outbound','statement'):raise ValueError('반품 출처를 선택하세요.')
    if location not in valid_locations():raise ValueError('유효한 입고 로케이션을 선택하세요.')
    if not _text(request_token):raise ValueError('입고 요청번호가 없습니다. 화면을 다시 열어 주세요.')
    day=date.fromisoformat(str(receipt_date or date.today())).isoformat()
    if day>date.today().isoformat():raise ValueError('미래 날짜로 입고할 수 없습니다.')
    now=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    previous=con.execute(f'SELECT id,source_kind,source_key,status,source_qty,conversion_factor,location,company FROM {TABLE} WHERE request_token=?',(request_token,)).fetchone()
    if previous:
        if tuple(previous[1:3])!=(kind,key):raise ValueError('다른 반품에 사용된 요청번호입니다.')
        if previous[3]!='received':raise ValueError('이미 취소된 요청입니다. 다시 조회하세요.')
        if previous[4]!=qty_in_source or Decimal(previous[5])!=conversion or previous[6]!=location or previous[7]!=company:
            raise ValueError('이미 저장된 요청과 수량·위치·사업장이 다릅니다. 입고 내역을 확인하세요.')
        return int(previous[0])
    if kind=='outbound':
        matches=[r for r in outbound_sources(con) if r['source_key']==key]
    else:
        # Keep the source read in the same transaction snapshot as the receipt.
        rows=_rows(con,'''SELECT s.statement_id,s.statement_date,s.statement_number,s.vendor_name AS customer,
            i.sequence,i.product_code,i.product_name,i.packaging_unit,i.lot_number AS lot,i.expiry_date AS exp_date,i.apply_price
            FROM return_source.statements s JOIN return_source.statement_items i ON i.statement_id=s.statement_id
            WHERE s.statement_id=? AND i.sequence=?''',tuple(json.loads(key)))
        matches=[]
        for r in rows:
            try:total=int(_text(r['apply_price']).split(':',3)[1]) if _text(r['apply_price']).startswith('반품:') else 0
            except (IndexError,ValueError):total=0
            r['lot']=_text(r['lot']) or '-';r['exp_date']=_text(r['exp_date']) or '-'
            r['total_qty']=total;r['fingerprint']=_hash([r.get(k) for k in ('statement_id','sequence','customer','product_code','product_name','packaging_unit','lot','exp_date')]);matches.append(r)
    if len(matches)!=1:raise ValueError('원본 반품/출고 내역이 삭제·취소되었거나 중복됩니다. 다시 조회하세요.')
    source=matches[0]
    if source['fingerprint']!=fingerprint:raise ValueError('원본 품목 정보가 변경됐습니다. 다시 조회하세요.')
    prior=_rows(con,f"SELECT product_name,conversion_factor,source_fingerprint,outbound_key FROM {TABLE} WHERE source_kind=? AND source_key=? AND status='received'",(kind,key))
    if kind=='outbound':
        product_name=source['product_name'];outbound_key=key
        if conversion!=1:raise ValueError('WMS 출고 내역의 단위는 변경할 수 없습니다.')
    if any(r['product_name']!=product_name or Decimal(r['conversion_factor'])!=conversion or r['source_fingerprint']!=fingerprint or r['outbound_key']!=outbound_key for r in prior):
        raise ValueError('이미 입고한 반품과 제품·수량 단위가 다릅니다. 기존 입고를 먼저 확인하세요.')
    if source_received(con,kind,key)+qty_in_source>int(source['total_qty']):raise ValueError('원본 반품수량 또는 출고수량을 초과합니다. 이미 입고한 수량을 확인하세요.')
    order_id=None
    if outbound_key:
        outbound=next((r for r in outbound_sources(con) if r['source_key']==outbound_key),None)
        if not outbound:raise ValueError('연결할 출고 내역이 취소·변경됐습니다.')
        if kind=='statement' and not customer_matches(source['customer'],outbound['customer']):
            raise ValueError('거래명세서와 원출고의 거래처가 다릅니다.')
        if (outbound['product_name'],outbound['lot'],outbound['exp_date'])!=(product_name,source['lot'],source['exp_date']):raise ValueError('연결 출고의 제품·제조번호·유통기한이 반품과 다릅니다.')
        if _outbound_received(con,outbound_key)+qty>int(outbound['total_qty']):raise ValueError('원출고의 반품 가능 잔량을 초과합니다.')
        order_id=int(outbound['order_id'])
    if mapping_name is not None:
        name=_text(mapping_name);product_name=_text(product_name)
        if not name or not product_name:raise ValueError('표준제품명과 사업장 연결 제품명을 입력하세요.')
        current=sorted({_text(r[0]) for r in con.execute(f'SELECT {column} FROM products WHERE standard_name=?',(product_name,)) if _text(r[0])})
        if mapping_before is None or (current!=sorted(mapping_before) and current!=[name]):
            raise ValueError('제품 매칭표가 변경됐습니다. 주문을 다시 조회하고 담아 주세요.')
        existing=con.execute('SELECT id FROM products WHERE standard_name=?',(product_name,)).fetchall()
        if existing:
            con.execute(f'UPDATE products SET {column}=? WHERE standard_name=?',(name,product_name))
        else:
            if 'warehouse_name' in {r[1] for r in con.execute('PRAGMA table_info(products)')}:
                con.execute(f'INSERT INTO products(standard_name,warehouse_name,{column}) VALUES(?,?,?)',(product_name,product_name,name))
            else:
                con.execute(f'INSERT INTO products(standard_name,{column}) VALUES(?,?)',(product_name,name))
    mappings=_rows(con,f"SELECT DISTINCT {column} AS erp_name FROM products WHERE standard_name=? AND TRIM(COALESCE({column},''))<>''",(product_name,))
    if len(mappings)!=1:raise ValueError(f'제품 매칭 관리에서 {company} 제품명을 한 가지로 연결한 뒤 입고하세요.')
    warehouse=mappings[0]['erp_name'];lot=source['lot'];exp=source['exp_date']
    dest=_rows(con,"SELECT * FROM inventory WHERE company=? AND product_name=? AND IFNULL(warehouse_name,'')=? AND COALESCE(lot,'-')=? AND COALESCE(exp_date,'-')=? AND location=? ORDER BY id LIMIT 1",(company,product_name,warehouse,lot,exp,location))
    if dest:
        inventory_id=int(dest[0]['id']);con.execute('UPDATE inventory SET qty=qty+?,updated_at=? WHERE id=?',(qty,now,inventory_id))
    else:
        inventory_id=con.execute('INSERT INTO inventory(company,product_name,warehouse_name,lot,exp_date,location,qty,updated_at) VALUES(?,?,?,?,?,?,?,?)',(company,product_name,warehouse,lot,exp,location,qty,now)).lastrowid
    receipt_id=con.execute(f'''INSERT INTO {TABLE}(request_token,source_kind,source_key,source_fingerprint,source_snapshot,outbound_key,outbound_order_id,statement_id,statement_sequence,product_name,lot,exp_date,source_qty,conversion_factor,qty,company,warehouse_name,location,inventory_id,receipt_date,memo,created_at,actor)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(request_token,kind,key,fingerprint,json.dumps(source,ensure_ascii=False),outbound_key,order_id,source.get('statement_id'),source.get('sequence'),product_name,lot,exp,qty_in_source,str(conversion),qty,company,warehouse,location,inventory_id,day,_text(memo),now,_current_actor())).lastrowid
    cur=con.cursor()
    insert_transaction_log(cur,created_at=now,tx_type='반품입고',product_name=product_name,warehouse_name=warehouse,lot=lot,exp_date=exp,to_company=company,to_location=location,qty=qty,memo=f"고객반품 #{receipt_id} / {source.get('customer','')} / 입고일자: {day} / {memo}")
    con.execute(f'UPDATE {TABLE} SET transaction_id=? WHERE id=?',(cur.lastrowid,receipt_id))
    return int(receipt_id)


def cancel_return(receipt_id):
    cancel_returns([receipt_id])


def cancel_returns(receipt_ids):
    ids=list(dict.fromkeys(int(value) for value in receipt_ids))
    if not ids:raise ValueError('취소할 입고를 체크해 주세요.')
    now=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with connect() as con:
        con.execute('BEGIN IMMEDIATE')
        for receipt_id in ids:
            _cancel_return(con,receipt_id,now)


def _cancel_return(con,receipt_id,now):
    if not _exists(con):raise ValueError('반품 입고 기록이 없습니다.')
    rows=_rows(con,f"SELECT * FROM {TABLE} WHERE id=? AND status='received'",(int(receipt_id),))
    if not rows:raise ValueError('이미 취소되었거나 없는 반품 입고입니다.')
    r=rows[0]
    stock=_rows(con,'SELECT * FROM inventory WHERE id=?',(r['inventory_id'],))
    if not stock or any(stock[0].get(k)!=r[k] for k in ('company','product_name','warehouse_name','lot','exp_date','location')) or int(stock[0]['qty'])<r['qty']:
        raise ValueError('입고 재고가 이동·출고·변경되어 바로 취소할 수 없습니다. 재고를 확인하세요.')
    con.execute('UPDATE inventory SET qty=qty-?,updated_at=? WHERE id=?',(r['qty'],now,r['inventory_id']))
    cur=con.cursor()
    insert_transaction_log(cur,created_at=now,tx_type='반품입고취소',product_name=r['product_name'],warehouse_name=r['warehouse_name'],lot=r['lot'],exp_date=r['exp_date'],to_company=r['company'],to_location=r['location'],qty=-r['qty'],memo=f"고객반품 #{receipt_id} 입고 취소 / 원입고 이력 #{r['transaction_id']}")
    con.execute(f"UPDATE {TABLE} SET status='cancelled',cancelled_at=?,cancel_transaction_id=? WHERE id=?",(now,cur.lastrowid,receipt_id))


def assert_order_editable(cur,order_id):
    if _exists(cur.connection) and cur.execute(f"SELECT 1 FROM {TABLE} WHERE outbound_order_id=? AND status='received' LIMIT 1",(int(order_id),)).fetchone():
        raise ValueError('반품 입고가 연결된 출고지시입니다. 반품 입고 화면에서 해당 입고를 취소한 뒤 수정·취소하세요.')


def update_return_for_history_delete(cur,tx_id,*,reverse):
    """Keep the receipt ledger consistent with either history deletion mode."""
    con=cur.connection
    if not _exists(con):return
    rows=_rows(con,f'SELECT * FROM {TABLE} WHERE transaction_id=? OR cancel_transaction_id=?',(tx_id,tx_id))
    for receipt in rows:
        is_receipt=receipt['transaction_id']==tx_id
        column='transaction_id' if is_receipt else 'cancel_transaction_id'
        if reverse:
            if is_receipt:
                if receipt['status']!='received':
                    raise ValueError('이미 취소된 반품 입고입니다. 연결된 반품입고취소 이력도 함께 선택하거나 이력만 삭제하세요.')
                cur.execute(f"UPDATE {TABLE} SET status='cancelled',cancelled_at=? WHERE id=?",(datetime.now().strftime('%Y-%m-%d %H:%M:%S'),receipt['id']))
            else:
                if receipt['status']!='cancelled':raise ValueError('반품 취소 상태가 변경됐습니다. 이력을 다시 조회하세요.')
                if receipt['source_kind']=='outbound':
                    sources=outbound_sources(con)
                else:
                    path=purchase_db_path()
                    with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)) as db:
                        sources=_statement_rows(db)
                source=next((r for r in sources if r['source_key']==receipt['source_key']),None)
                if not source or source['fingerprint']!=receipt['source_fingerprint']:
                    raise ValueError('반품 원본이 변경·삭제되어 취소를 되돌릴 수 없습니다. 이력만 삭제는 가능합니다.')
                if source_received(con,receipt['source_kind'],receipt['source_key'])+receipt['source_qty']>source['total_qty']:
                    raise ValueError('이미 다시 입고한 수량이 있어 반품 가능 수량을 초과합니다. 이력만 삭제는 가능합니다.')
                if receipt['outbound_key']:
                    outbound=next((r for r in outbound_sources(con) if r['source_key']==receipt['outbound_key']),None)
                    if not outbound or _outbound_received(con,receipt['outbound_key'])+receipt['qty']>outbound['total_qty']:
                        raise ValueError('원출고의 반품 가능 수량을 초과하여 취소를 되돌릴 수 없습니다.')
                cur.execute(f"UPDATE {TABLE} SET status='received',cancelled_at=NULL WHERE id=?",(receipt['id'],))
        cur.execute(f'UPDATE {TABLE} SET {column}=NULL WHERE id=?',(receipt['id'],))


def assert_history_editable(cur,ids):
    if not ids or not _exists(cur.connection):return
    for tx_id in ids:
        row=cur.execute('SELECT memo FROM transactions WHERE id=?',(tx_id,)).fetchone()
        if row:
            import re
            match=re.search(r'출고지시서\s*#(\d+)',str(row[0] or ''))
            if match:assert_order_editable(cur,int(match.group(1)))


def customer_matches(statement_customer, outbound_customer):
    left, right = _text(statement_customer).casefold(), _text(outbound_customer).casefold()
    return bool(left) and (left == right or right.startswith(left + ' '))


def validate_statement_replacement(data_dir, frame):
    """A received return's identity/quantity cannot be silently removed by bulk CSV-style rewrites."""
    if (Path(data_dir)/'purchase_order.db').resolve()!=purchase_db_path().resolve():
        return
    from nohtus.db import DB_PATH
    if not Path(DB_PATH).is_file():
        return
    with closing(sqlite3.connect(Path(DB_PATH).resolve().as_uri()+'?mode=ro',uri=True)) as con:
        if not _exists(con):return
        receipts=_rows(con,f"SELECT source_key,source_snapshot,SUM(source_qty) AS received FROM {TABLE} WHERE source_kind='statement' AND status='received' GROUP BY source_key")
    for receipt in receipts:
        sid,sequence=json.loads(receipt['source_key'])
        matching=frame[(frame['명세서ID'].astype(str)==str(sid)) & (frame['순번'].astype(str).isin([str(sequence),str(float(sequence))]))]
        if len(matching)!=1:raise ValueError('WMS 반품 입고가 연결된 명세서 품목은 삭제할 수 없습니다. 반품 입고를 먼저 취소하세요.')
        row=matching.iloc[0];snapshot=json.loads(receipt['source_snapshot'])
        pairs={'product_code':'제품코드','product_name':'정식제품명','packaging_unit':'단위','lot':'제조번호','exp_date':'유통기한'}
        for key,column in pairs.items():
            actual=_text(row.get(column)) or ('-' if key in ('lot','exp_date') else '')
            if actual!=_text(snapshot.get(key)):
                raise ValueError('WMS 반품 입고가 연결된 품목·제조번호·유통기한·단위는 변경할 수 없습니다. 반품 입고를 먼저 취소하세요.')
        marker=_text(row.get('가격적용여부'))
        try:amount=int(marker.split(':',3)[1]) if marker.startswith('반품:') else 0
        except (IndexError,ValueError):amount=0
        if amount<int(receipt['received']):raise ValueError('반품수량을 WMS 반품 입고 완료 수량보다 줄일 수 없습니다. 반품 입고를 먼저 취소하세요.')
