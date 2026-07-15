from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from nohtus.db import connect
from nohtus.services.inventory import insert_transaction_log

P = "P"


def ensure_export_waiting_tables(cur=None):
    own = cur is None
    con = connect() if own else None
    c = con.cursor() if own else cur
    c.execute("""CREATE TABLE IF NOT EXISTS export_waiting_orders(
        id INTEGER PRIMARY KEY AUTOINCREMENT, export_no TEXT NOT NULL, country TEXT NOT NULL,
        title TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'waiting', erp_company TEXT,
        erp_customer_code TEXT, erp_customer_name TEXT, confirmed_at TEXT, cancelled_at TEXT,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL, created_by TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS export_waiting_items(
        id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER NOT NULL, source_inventory_id INTEGER,
        company TEXT NOT NULL, product_name TEXT NOT NULL, warehouse_name TEXT, lot TEXT, exp_date TEXT,
        source_location TEXT NOT NULL, waiting_location TEXT NOT NULL DEFAULT 'P', qty INTEGER NOT NULL,
        FOREIGN KEY(order_id) REFERENCES export_waiting_orders(id))""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_export_waiting_items_order ON export_waiting_items(order_id)")
    if own:
        con.commit(); con.close()


def _actor():
    try:
        from nohtus.auth import current_display_name, current_username
        return str(current_display_name() or current_username() or "").strip()
    except Exception:
        return ""


def _dict_row(cur, sql, params):
    raw = cur.execute(sql, params).fetchone()
    return dict(zip([d[0] for d in cur.description], raw)) if raw else None


def _find(cur, s, location):
    return cur.execute("""SELECT id,qty FROM inventory WHERE company=? AND product_name=?
        AND IFNULL(warehouse_name,'')=? AND IFNULL(lot,'-')=? AND IFNULL(exp_date,'-')=? AND location=?""",
        (s.get("company", ""), s.get("product_name", ""), s.get("warehouse_name", "") or "",
         s.get("lot", "-") or "-", s.get("exp_date", "-") or "-", location)).fetchone()


def _add(cur, s, location, qty, now, shippable):
    cols = {r[1] for r in cur.execute("PRAGMA table_info(inventory)").fetchall()}
    row = _find(cur, s, location)
    if row:
        if "is_shippable" in cols:
            cur.execute("UPDATE inventory SET qty=?,updated_at=?,is_shippable=? WHERE id=?",
                        (int(row[1] or 0) + qty, now, int(shippable), int(row[0])))
        else:
            cur.execute("UPDATE inventory SET qty=?,updated_at=? WHERE id=?", (int(row[1] or 0) + qty, now, int(row[0])))
        return int(row[0])
    fields = ["company","product_name","warehouse_name","lot","exp_date","location","qty","updated_at"]
    values = [s.get("company", ""),s.get("product_name", ""),s.get("warehouse_name", "") or "",
              s.get("lot", "-") or "-",s.get("exp_date", "-") or "-",location,qty,now]
    if "is_shippable" in cols:
        fields.append("is_shippable"); values.append(int(shippable))
    cur.execute(f"INSERT INTO inventory({','.join(fields)}) VALUES({','.join('?' for _ in fields)})", values)
    return int(cur.lastrowid)


def _take_source(cur, inventory_id, qty, now):
    s = _dict_row(cur, "SELECT * FROM inventory WHERE id=?", (int(inventory_id),))
    if not s:
        raise ValueError(f"재고 #{inventory_id}를 찾을 수 없습니다.")
    available = int(s.get("qty") or 0)
    if qty <= 0 or qty > available:
        raise ValueError(f"{s.get('product_name','제품')} 재고 부족: 요청 {qty}EA / 현재 {available}EA")
    if str(s.get("location") or "").strip() == P:
        raise ValueError(f"{s.get('product_name','제품')}은 이미 수출대기 위치 P에 있습니다.")
    cur.execute("UPDATE inventory SET qty=?,updated_at=? WHERE id=?", (available - qty, now, int(inventory_id)))
    return s


def _take_p(cur, item, now):
    row = _find(cur, item, P); qty = int(item["qty"] or 0)
    if not row or int(row[1] or 0) < qty:
        raise ValueError(f"P 로케이션의 {item['product_name']} 재고가 부족합니다.")
    cur.execute("UPDATE inventory SET qty=?,updated_at=? WHERE id=?", (int(row[1] or 0) - qty, now, int(row[0])))


def _items(cur, order_id):
    rows = cur.execute("""SELECT source_inventory_id,company,product_name,warehouse_name,lot,exp_date,
        source_location,waiting_location,qty FROM export_waiting_items WHERE order_id=? ORDER BY id""", (int(order_id),)).fetchall()
    keys = ["source_inventory_id","company","product_name","warehouse_name","lot","exp_date","source_location","waiting_location","qty"]
    return [dict(zip(keys, r)) for r in rows]


def _restore(cur, order_id, now, memo):
    for item in _items(cur, order_id):
        _take_p(cur, item, now)
        _add(cur, item, item["source_location"], int(item["qty"]), now, 1)
        insert_transaction_log(cur, created_at=now, tx_type="위치이동", product_name=item["product_name"],
            warehouse_name=item.get("warehouse_name", ""), lot=item.get("lot", "-"), exp_date=item.get("exp_date", "-"),
            from_company=item["company"], from_location=P, to_company=item["company"],
            to_location=item["source_location"], qty=item["qty"], memo=memo)


def save_export_waiting_order(cart, *, country, export_no, editing_order_id=None):
    country, export_no = str(country or "").strip(), str(export_no or "").strip()
    if not country: raise ValueError("국가를 입력하세요.")
    if not export_no: raise ValueError("수출번호를 입력하세요.")
    grouped = defaultdict(int)
    for x in cart or []:
        if int(x.get("요청수량") or 0) > 0: grouped[int(x.get("id"))] += int(x.get("요청수량"))
    if not grouped: raise ValueError("수출대기 등록할 품목이 없습니다.")
    now, title = datetime.now().strftime("%Y-%m-%d %H:%M:%S"), f"{country}_{export_no}"
    with connect() as con:
        cur = con.cursor(); ensure_export_waiting_tables(cur)
        if editing_order_id:
            row = cur.execute("SELECT status FROM export_waiting_orders WHERE id=?", (int(editing_order_id),)).fetchone()
            if not row or row[0] != "waiting": raise ValueError("수정할 수출대기 건이 없거나 이미 처리되었습니다.")
            _restore(cur, editing_order_id, now, f"수출대기 수정 원복 / {title}")
            cur.execute("DELETE FROM export_waiting_items WHERE order_id=?", (int(editing_order_id),))
            cur.execute("UPDATE export_waiting_orders SET export_no=?,country=?,title=?,updated_at=? WHERE id=?",
                        (export_no,country,title,now,int(editing_order_id)))
            order_id = int(editing_order_id)
        else:
            cur.execute("""INSERT INTO export_waiting_orders(export_no,country,title,status,created_at,updated_at,created_by)
                VALUES(?,?,?,'waiting',?,?,?)""", (export_no,country,title,now,now,_actor()))
            order_id = int(cur.lastrowid)
        total = 0
        for inventory_id, qty in grouped.items():
            s = _take_source(cur, inventory_id, qty, now); _add(cur, s, P, qty, now, 0)
            cur.execute("""INSERT INTO export_waiting_items(order_id,source_inventory_id,company,product_name,
                warehouse_name,lot,exp_date,source_location,waiting_location,qty) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (order_id,inventory_id,s.get("company", ""),s.get("product_name", ""),s.get("warehouse_name", "") or "",
                 s.get("lot", "-") or "-",s.get("exp_date", "-") or "-",s.get("location", ""),P,qty))
            insert_transaction_log(cur, created_at=now, tx_type="위치이동", product_name=s.get("product_name", ""),
                warehouse_name=s.get("warehouse_name", "") or "", lot=s.get("lot", "-"), exp_date=s.get("exp_date", "-"),
                from_company=s.get("company", ""), from_location=s.get("location", ""), to_company=s.get("company", ""),
                to_location=P, qty=qty, memo=f"수출대기 등록 / {title}")
            total += qty
        con.commit()
    return {"order_id":order_id,"row_count":len(grouped),"total_qty":total,"title":title}


def cancel_export_waiting_order(order_id):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with connect() as con:
        cur=con.cursor(); ensure_export_waiting_tables(cur)
        row=cur.execute("SELECT title,status FROM export_waiting_orders WHERE id=?",(int(order_id),)).fetchone()
        if not row or row[1] != "waiting": raise ValueError("취소할 수출대기 건이 없거나 이미 처리되었습니다.")
        _restore(cur,order_id,now,f"수출대기 취소 / {row[0]}")
        cur.execute("UPDATE export_waiting_orders SET status='cancelled',cancelled_at=?,updated_at=? WHERE id=?",(now,now,int(order_id)))
        con.commit()


def confirm_export_waiting_order(order_id, *, erp_company, customer_code, customer_name):
    erp_company, customer_name = str(erp_company or "").strip(), str(customer_name or "").strip()
    if not erp_company or not customer_name: raise ValueError("ERP 사업장과 수출 매출처를 선택하세요.")
    now=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with connect() as con:
        cur=con.cursor(); ensure_export_waiting_tables(cur)
        order=cur.execute("SELECT title,status FROM export_waiting_orders WHERE id=?",(int(order_id),)).fetchone()
        if not order or order[1] != "waiting": raise ValueError("확정할 수출대기 건이 없거나 이미 처리되었습니다.")
        for item in _items(cur,order_id):
            _take_p(cur,item,now)
            insert_transaction_log(cur,created_at=now,tx_type="수출확정",product_name=item["product_name"],
                warehouse_name=item.get("warehouse_name", ""),lot=item.get("lot", "-"),exp_date=item.get("exp_date", "-"),
                from_company=item["company"],from_location=P,to_company=None,to_location=None,qty=item["qty"],
                memo=f"수출확정 / {order[0]} / ERP매출처: {customer_name}")
        cur.execute("""UPDATE export_waiting_orders SET status='confirmed',erp_company=?,erp_customer_code=?,
            erp_customer_name=?,confirmed_at=?,updated_at=? WHERE id=?""",
            (erp_company,str(customer_code or "").strip(),customer_name,now,now,int(order_id)))
        con.commit()


def move_cart_to_export_waiting(cart, *, title="", customer_name=""):
    title=str(title or "").strip()
    country, export_no = title.split("_",1) if "_" in title else ("수출",title or "미지정")
    return save_export_waiting_order(cart,country=country,export_no=export_no)
