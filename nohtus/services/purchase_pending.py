"""매입대기 보관과 정상재고 전환. 대기 수량은 inventory에 넣지 않는다."""
from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal, InvalidOperation

import pandas as pd

from nohtus.config import COMPANIES
from nohtus.db import connect
from nohtus.services.inbound import _mapping_column_for_company
from nohtus.services.inventory import insert_transaction_log, _current_actor
from nohtus.locations import expand_row_range


COLUMNS = ["id", "product_name", "lot", "exp_date", "location", "location_range_cells",
           "qty", "inbound_date", "supplier", "memo", "created_at", "actor"]


def _ensure_table(con):
    con.execute("""CREATE TABLE IF NOT EXISTS purchase_pending (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_token TEXT NOT NULL UNIQUE,
        product_name TEXT NOT NULL,
        lot TEXT NOT NULL, exp_date TEXT NOT NULL, location TEXT NOT NULL,
        location_range_cells TEXT,
        qty INTEGER NOT NULL CHECK(qty > 0),
        inbound_date TEXT NOT NULL, supplier TEXT NOT NULL DEFAULT '', memo TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL, actor TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','completed')),
        completed_at TEXT, completed_by TEXT, company TEXT, erp_name TEXT, inventory_id INTEGER
    )""")


def pending_rows():
    """초기 조회는 테이블/운영 데이터를 변경하지 않는다."""
    with connect() as con:
        if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='purchase_pending'").fetchone():
            return pd.DataFrame(columns=COLUMNS)
        cancellation_filter = ""
        if _has_cancellations(con):
            cancellation_filter = " AND id NOT IN (SELECT pending_id FROM purchase_pending_cancellations)"
        return pd.read_sql_query(
            f"SELECT {','.join(COLUMNS)} FROM purchase_pending WHERE status='pending'{cancellation_filter} ORDER BY id DESC", con)


def _has_cancellations(con):
    return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='purchase_pending_cancellations'").fetchone() is not None


def _is_cancelled(con, pending_id):
    return _has_cancellations(con) and con.execute(
        "SELECT 1 FROM purchase_pending_cancellations WHERE pending_id=?", (int(pending_id),)).fetchone() is not None


def cancel_pending(pending_id):
    """취소 기록을 별도 보존하고 대기 목록/도면에서 제외한다. 재고는 변경하지 않는다."""
    with connect() as con:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute("SELECT id FROM purchase_pending WHERE id=? AND status='pending'", (int(pending_id),)).fetchone()
        if not row or _is_cancelled(con, pending_id):
            raise ValueError("이미 매입등록 완료 또는 취소되었거나 존재하지 않는 대기 행입니다.")
        con.execute("""CREATE TABLE IF NOT EXISTS purchase_pending_cancellations(
            pending_id INTEGER PRIMARY KEY,
            cancelled_at TEXT NOT NULL,
            cancelled_by TEXT NOT NULL
        )""")
        con.execute("INSERT INTO purchase_pending_cancellations VALUES(?,?,?)",
                    (int(pending_id), datetime.now().strftime("%Y-%m-%d %H:%M:%S"), _current_actor()))


def _ensure_standard_product(cur, product):
    if not cur.execute("SELECT 1 FROM products WHERE TRIM(standard_name)=?", (product,)).fetchone():
        cur.execute("""INSERT INTO products(standard_name,warehouse_name,product_code,aliases,
            erp_nohtuspharm_name,erp_nohtus_name,erp_noh_name,erp_noh_code,bidata_name)
            VALUES(?,?,'','','','','','','')""", (product, product))


def register_pending(product, lot, exp, location, qty, inbound_date, supplier="", memo="",
                     location_range_cells=None, request_token=None):
    import uuid
    product, location = str(product or "").strip(), str(location or "").strip()
    if not product or not location:
        raise ValueError("표준제품명과 위치를 입력하세요.")
    try:
        number = Decimal(str(qty))
        if not number.is_finite() or number <= 0 or number != number.to_integral_value():
            raise ValueError
        qty = int(number)
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("수량은 1 이상의 정수로 입력하세요.")
    day = datetime.strptime(str(inbound_date), "%Y-%m-%d").strftime("%Y-%m-%d")
    cells = json.dumps(list(location_range_cells or []), ensure_ascii=False)
    token = str(request_token or uuid.uuid4())
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with connect() as con:
        con.execute("BEGIN IMMEDIATE")
        _ensure_table(con)
        existing = con.execute("SELECT id FROM purchase_pending WHERE request_token=?", (token,)).fetchone()
        if existing:
            return int(existing[0])
        cur = con.cursor()
        _ensure_standard_product(cur, product)
        cur.execute("""INSERT INTO purchase_pending(request_token,product_name,lot,exp_date,location,
            location_range_cells,qty,inbound_date,supplier,memo,created_at,actor)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (token, product, str(lot or "-"), str(exp or "-"), location, cells,
             qty, day, str(supplier or "").strip(), str(memo or "").strip(), now, _current_actor()))
        return int(cur.lastrowid)


def pending_product_catalog(company, term=""):
    """선택 사업장의 ERP명과 코드를 같은 매칭 행에서 읽는다."""
    column = _mapping_column_for_company(company)
    if not column:
        return pd.DataFrame(columns=['id', 'standard_name', 'erp_name', 'product_code', 'aliases'])
    code_column = {"노투스팜": "product_code", "NOH": "erp_noh_code"}.get(company)
    code_sql = f"COALESCE({code_column},'')" if code_column else "''"
    with connect() as con:
        frame = pd.read_sql_query(f"""SELECT id,TRIM(standard_name) AS standard_name,
            TRIM(COALESCE({column},'')) AS erp_name,{code_sql} AS product_code,
            COALESCE(aliases,'') AS aliases FROM products
            WHERE TRIM(COALESCE(standard_name,''))<>'' ORDER BY standard_name,id""", con)
    term = str(term or '').strip().casefold()
    if term and not frame.empty:
        frame = frame.loc[frame.apply(lambda row: any(term in str(row[c]).casefold()
                            for c in ['standard_name','erp_name','product_code','aliases']), axis=1)]
    return frame


def _save_mapping(cur, product, company, erp_name, product_code, mapping_id=None):
    column = _mapping_column_for_company(company)
    if mapping_id is not None:
        code_column = {"노투스팜": "product_code", "NOH": "erp_noh_code"}.get(company)
        code_sql = f"COALESCE({code_column},'')" if code_column else "''"
        selected = cur.execute(f"SELECT TRIM(standard_name),TRIM(COALESCE({column},'')),{code_sql} FROM products WHERE id=?",
                               (int(mapping_id),)).fetchone()
        if not selected or selected[0] != product or selected[1] != erp_name:
            raise ValueError("선택한 제품 매칭이 변경되었습니다. 제품을 다시 검색해 주세요.")
        if str(selected[2] or '').strip() != product_code and str(selected[2] or '').strip():
            raise ValueError("ERP 제품코드가 변경되었습니다. 제품을 다시 검색해 주세요.")
        if code_column and product_code and not str(selected[2] or '').strip():
            cur.execute(f"UPDATE products SET {code_column}=? WHERE id=?", (product_code, int(mapping_id)))
        return
    other = cur.execute(f"SELECT standard_name FROM products WHERE TRIM({column})=? AND TRIM(standard_name)<>?",
                        (erp_name, product)).fetchone()
    if other:
        raise ValueError(f"이 ERP명/비자료명은 다른 표준제품명({other[0]})에 연결되어 있습니다.")
    _ensure_standard_product(cur, product)
    row = cur.execute(f"SELECT id FROM products WHERE TRIM(standard_name)=? AND TRIM({column})=? ORDER BY id",
                      (product, erp_name)).fetchone()
    if not row:
        row = cur.execute(f"SELECT id FROM products WHERE TRIM(standard_name)=? AND TRIM(COALESCE({column},''))='' ORDER BY id",
                          (product,)).fetchone()
        if row:
            cur.execute(f"UPDATE products SET {column}=? WHERE id=?", (erp_name, row[0]))
        else:
            # 다른 ERP 매칭을 덮어쓰지 않고 별도 매칭 행을 만든다.
            cur.execute(f"""INSERT INTO products(standard_name,warehouse_name,{column},image_path,is_material,material_type)
                SELECT standard_name,warehouse_name,?,image_path,is_material,material_type
                FROM products WHERE TRIM(standard_name)=? ORDER BY id LIMIT 1""", (erp_name, product))
            row = (cur.lastrowid,)
    code_column = {"노투스팜": "product_code", "NOH": "erp_noh_code"}.get(company)
    if code_column and product_code:
        old = cur.execute(f"SELECT {code_column} FROM products WHERE id=?", (row[0],)).fetchone()[0]
        if str(old or "").strip() and str(old).strip() != product_code:
            raise ValueError("기존 ERP 제품코드와 다릅니다. 제품 매칭 관리에서 확인하세요.")
        cur.execute(f"UPDATE products SET {code_column}=? WHERE id=?", (product_code, row[0]))


def complete_pending(pending_id, company, erp_name, product_code="", *, standard_name=None, mapping_id=None):
    company, erp_name = str(company or "").strip(), str(erp_name or "").strip()
    if company not in COMPANIES:
        raise ValueError("매입등록을 완료할 사업장을 선택하세요.")
    if not erp_name:
        raise ValueError("ERP명/비자료명을 입력하세요.")
    if standard_name is not None:
        standard_name = str(standard_name).strip()
        if not standard_name:
            raise ValueError("표준제품명을 입력하세요.")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with connect() as con:
        con.execute("BEGIN IMMEDIATE")
        cur = con.cursor()
        raw = cur.execute("SELECT * FROM purchase_pending WHERE id=? AND status='pending'", (int(pending_id),)).fetchone()
        if not raw or _is_cancelled(con, pending_id):
            raise ValueError("이미 매입등록 완료 또는 취소되었거나 존재하지 않는 대기 행입니다.")
        item = dict(zip([d[0] for d in cur.description], raw))
        original_name = item['product_name']
        if standard_name is not None:
            item['product_name'] = standard_name
        _save_mapping(cur, item['product_name'], company, erp_name, str(product_code or '').strip(), mapping_id)
        key = (company, item['product_name'], erp_name, item['lot'], item['exp_date'], item['location'])
        old = cur.execute("""SELECT id,qty,location_range_cells,location_range_end FROM inventory
            WHERE company=? AND product_name=? AND IFNULL(warehouse_name,'')=?
            AND lot=? AND exp_date=? AND location=?""", key).fetchone()
        if old:
            occupied = set(expand_row_range(item['location'], old[2], old[3]))
            occupied.update(expand_row_range(item['location'], item['location_range_cells'], None))
            cur.execute("UPDATE inventory SET qty=qty+?,updated_at=?,location_range_cells=? WHERE id=?",
                        (item['qty'], now, json.dumps(sorted(occupied), ensure_ascii=False), old[0]))
            inventory_id = old[0]
        else:
            cur.execute("""INSERT INTO inventory(company,product_name,warehouse_name,lot,exp_date,location,
                qty,updated_at,location_range_cells) VALUES(?,?,?,?,?,?,?,?,?)""",
                (*key, item['qty'], now, item['location_range_cells']))
            inventory_id = cur.lastrowid
        memo = f"매입등록 완료 / 대기번호: {item['id']} / 실물 입고일: {item['inbound_date']}"
        if item['product_name'] != original_name:
            memo += f" / 대기 등록명: {original_name}"
        if item['supplier']:
            memo += f" / 매입처: {item['supplier']}"
        if item['memo']:
            memo += f" / {item['memo']}"
        insert_transaction_log(cur, created_at=now, tx_type="입고", product_name=item['product_name'],
                               warehouse_name=erp_name, lot=item['lot'], exp_date=item['exp_date'],
                               to_company=company, to_location=item['location'], qty=item['qty'], memo=memo)
        cur.execute("""UPDATE purchase_pending SET status='completed',completed_at=?,completed_by=?,
            company=?,erp_name=?,inventory_id=?,product_name=? WHERE id=? AND status='pending'""",
            (now, _current_actor(), company, erp_name, inventory_id, item['product_name'], int(pending_id)))
        return int(inventory_id)


def map_pending_rows():
    frame = pending_rows()
    if frame.empty:
        return frame
    frame = frame.copy()
    # 일반 재고와 ID 충돌 방지. 매입대기는 일반 이동/출고 대상으로 전달하지 않는다.
    frame['id'] = -frame['id']
    frame['company'] = '등록대기'
    frame['warehouse_name'] = ''
    frame['location_range_end'] = None
    frame['is_purchase_pending'] = True
    return frame
