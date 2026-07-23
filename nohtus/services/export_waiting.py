from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from nohtus.db import connect
from nohtus.services.inventory import insert_transaction_log

P = "P"
TRANSPORT_METHODS = ("미지정", "항공", "해상", "핸드캐리")


def ensure_export_waiting_tables(cur=None):
    own = cur is None
    con = connect() if own else None
    c = con.cursor() if own else cur
    c.execute("""CREATE TABLE IF NOT EXISTS export_waiting_orders(
        id INTEGER PRIMARY KEY AUTOINCREMENT, export_no TEXT NOT NULL, country TEXT NOT NULL,
        buyer TEXT, transport_method TEXT, title TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'waiting', erp_company TEXT,
        erp_customer_code TEXT, erp_customer_name TEXT, confirmed_at TEXT, cancelled_at TEXT,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL, created_by TEXT)""")
    order_cols = {r[1] for r in c.execute("PRAGMA table_info(export_waiting_orders)").fetchall()}
    if "buyer" not in order_cols:
        c.execute("ALTER TABLE export_waiting_orders ADD COLUMN buyer TEXT")
    if "transport_method" not in order_cols:
        c.execute("ALTER TABLE export_waiting_orders ADD COLUMN transport_method TEXT")

    c.execute("""CREATE TABLE IF NOT EXISTS export_waiting_items(
        id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER NOT NULL, source_inventory_id INTEGER,
        company TEXT NOT NULL, product_name TEXT NOT NULL, warehouse_name TEXT, lot TEXT, exp_date TEXT,
        source_location TEXT NOT NULL, waiting_location TEXT NOT NULL DEFAULT 'P', qty INTEGER NOT NULL,
        moved_at TEXT, confirmed INTEGER NOT NULL DEFAULT 0, confirmed_company TEXT,
        confirmed_customer_code TEXT, confirmed_customer_name TEXT, confirmed_at TEXT,
        FOREIGN KEY(order_id) REFERENCES export_waiting_orders(id))""")
    item_cols = {r[1] for r in c.execute("PRAGMA table_info(export_waiting_items)").fetchall()}
    additions = {
        "moved_at": "TEXT",
        "confirmed": "INTEGER NOT NULL DEFAULT 0",
        "confirmed_company": "TEXT",
        "confirmed_customer_code": "TEXT",
        "confirmed_customer_name": "TEXT",
        "confirmed_at": "TEXT",
    }
    for name, definition in additions.items():
        if name not in item_cols:
            c.execute(f"ALTER TABLE export_waiting_items ADD COLUMN {name} {definition}")
    c.execute("CREATE INDEX IF NOT EXISTS idx_export_waiting_items_order ON export_waiting_items(order_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_export_waiting_items_moved_at ON export_waiting_items(moved_at)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_export_waiting_items_confirmed ON export_waiting_items(order_id,confirmed)")
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


def _cart_source_hint(row):
    return {
        "company": str(row.get("사업장") or row.get("company") or "").strip(),
        "product_name": str(row.get("제품명") or row.get("product_name") or "").strip(),
        "warehouse_name": str(row.get("warehouse_name") or "").strip(),
        "lot": str(row.get("LOT") or row.get("lot") or "-").strip() or "-",
        "exp_date": str(row.get("유통기한") or row.get("exp_date") or "-").strip() or "-",
        "location": str(row.get("로케이션") or row.get("source_location") or row.get("location") or "").strip(),
    }


def _resolve_source_row(cur, inventory_id, fallback=None):
    source_id = int(inventory_id or 0)
    if source_id:
        row = _dict_row(cur, "SELECT * FROM inventory WHERE id=?", (source_id,))
        if row:
            return row

    hint = fallback or {}
    company = str(hint.get("company") or "").strip()
    product_name = str(hint.get("product_name") or "").strip()
    lot = str(hint.get("lot") or "-").strip() or "-"
    exp_date = str(hint.get("exp_date") or "-").strip() or "-"
    location = str(hint.get("location") or hint.get("source_location") or "").strip()
    warehouse_name = str(hint.get("warehouse_name") or "").strip()
    if not company or not product_name or not location:
        return None

    if warehouse_name:
        row = _dict_row(cur, """SELECT * FROM inventory
            WHERE company=? AND product_name=? AND IFNULL(warehouse_name,'')=?
              AND IFNULL(lot,'-')=? AND IFNULL(exp_date,'-')=? AND location=?
            ORDER BY qty DESC,id LIMIT 1""",
            (company, product_name, warehouse_name, lot, exp_date, location))
        if row:
            return row

    return _dict_row(cur, """SELECT * FROM inventory
        WHERE company=? AND product_name=? AND IFNULL(lot,'-')=?
          AND IFNULL(exp_date,'-')=? AND location=?
        ORDER BY qty DESC,id LIMIT 1""",
        (company, product_name, lot, exp_date, location))


def _take_source(cur, inventory_id, qty, now, fallback=None):
    s = _resolve_source_row(cur, inventory_id, fallback)
    if not s:
        hint = fallback or {}
        label = " / ".join(x for x in [
            str(hint.get("company") or "").strip(),
            str(hint.get("location") or hint.get("source_location") or "").strip(),
            str(hint.get("product_name") or "").strip(),
        ] if x)
        suffix = f" ({label})" if label else ""
        raise ValueError(f"재고 #{inventory_id}를 찾을 수 없습니다.{suffix}")
    available = int(s.get("qty") or 0)
    if qty <= 0 or qty > available:
        raise ValueError(f"{s.get('product_name','제품')} 재고 부족: 요청 {qty}EA / 현재 {available}EA")
    if str(s.get("location") or "").strip() == P:
        raise ValueError(f"{s.get('product_name','제품')}은 이미 수출대기 위치 P에 있습니다.")
    resolved_id = int(s.get("id") or 0)
    cur.execute("UPDATE inventory SET qty=?,updated_at=? WHERE id=?", (available - qty, now, resolved_id))
    s["_resolved_inventory_id"] = resolved_id
    return s


def _take_p(cur, item, now, qty=None):
    take_qty = int(item.get("qty") or 0) if qty is None else int(qty or 0)
    row = _find(cur, item, P)
    if not row or int(row[1] or 0) < take_qty:
        raise ValueError(f"P 로케이션의 {item['product_name']} 재고가 부족합니다.")
    cur.execute("UPDATE inventory SET qty=?,updated_at=? WHERE id=?", (int(row[1] or 0) - take_qty, now, int(row[0])))


def _items(cur, order_id, *, confirmed=None):
    where = "order_id=?"
    params = [int(order_id)]
    if confirmed is not None:
        where += " AND COALESCE(confirmed,0)=?"
        params.append(int(bool(confirmed)))
    rows = cur.execute(f"""SELECT id,source_inventory_id,company,product_name,warehouse_name,lot,exp_date,
        source_location,waiting_location,qty,moved_at,COALESCE(confirmed,0),confirmed_company,
        confirmed_customer_code,confirmed_customer_name,confirmed_at
        FROM export_waiting_items WHERE {where} ORDER BY id""", tuple(params)).fetchall()
    keys = ["id","source_inventory_id","company","product_name","warehouse_name","lot","exp_date",
            "source_location","waiting_location","qty","moved_at","confirmed","confirmed_company",
            "confirmed_customer_code","confirmed_customer_name","confirmed_at"]
    return [dict(zip(keys, r)) for r in rows]


def _restore(cur, order_id, now, memo):
    for item in _items(cur, order_id, confirmed=False):
        _take_p(cur, item, now)
        _add(cur, item, item["source_location"], int(item["qty"]), now, 1)
        insert_transaction_log(cur, created_at=now, tx_type="위치이동", product_name=item["product_name"],
            warehouse_name=item.get("warehouse_name", ""), lot=item.get("lot", "-"), exp_date=item.get("exp_date", "-"),
            from_company=item["company"], from_location=P, to_company=item["company"],
            to_location=item["source_location"], qty=item["qty"], memo=memo)


def _current_item_signature(cur, order_id):
    grouped = defaultdict(int)
    for item in _items(cur, order_id, confirmed=False):
        grouped[int(item.get("source_inventory_id") or 0)] += int(item.get("qty") or 0)
    return dict(grouped)


def _apply_export_waiting_item_changes(cur, order_id, grouped, source_hints, now, title, export_no):
    current_items = _items(cur, order_id, confirmed=False)
    current_qty = defaultdict(int)
    current_item_by_source = {}
    for item in current_items:
        source_id = int(item.get("source_inventory_id") or 0)
        current_qty[source_id] += int(item.get("qty") or 0)
        current_item_by_source.setdefault(source_id, item)

    target_qty = {int(k): int(v) for k, v in dict(grouped).items()}
    all_source_ids = sorted(set(current_qty) | set(target_qty))

    for source_id in all_source_ids:
        before = int(current_qty.get(source_id, 0))
        after = int(target_qty.get(source_id, 0))
        diff = after - before
        if diff == 0:
            continue

        if diff < 0:
            item = current_item_by_source[source_id]
            restore_qty = abs(diff)
            _take_p(cur, item, now, restore_qty)
            _add(cur, item, item["source_location"], restore_qty, now, 1)
            insert_transaction_log(
                cur,
                created_at=now,
                tx_type="위치이동",
                product_name=item["product_name"],
                warehouse_name=item.get("warehouse_name", ""),
                lot=item.get("lot", "-"),
                exp_date=item.get("exp_date", "-"),
                from_company=item["company"],
                from_location=P,
                to_company=item["company"],
                to_location=item["source_location"],
                qty=restore_qty,
                memo=f"수출대기 수정 / 수량감소 또는 품목삭제 / {title} / 수출번호: {export_no}",
            )
        else:
            hint = source_hints.get(source_id)
            s = _take_source(cur, source_id, diff, now, hint)
            _add(cur, s, P, diff, now, 0)
            source_hints[source_id] = s
            insert_transaction_log(
                cur,
                created_at=now,
                tx_type="위치이동",
                product_name=s.get("product_name", ""),
                warehouse_name=s.get("warehouse_name", "") or "",
                lot=s.get("lot", "-"),
                exp_date=s.get("exp_date", "-"),
                from_company=s.get("company", ""),
                from_location=s.get("location", ""),
                to_company=s.get("company", ""),
                to_location=P,
                qty=diff,
                memo=f"수출대기 수정 / 수량증가 또는 품목추가 / {title} / 수출번호: {export_no}",
            )

    cur.execute("DELETE FROM export_waiting_items WHERE order_id=?", (int(order_id),))
    for source_id, qty in target_qty.items():
        if qty <= 0:
            continue
        s = source_hints.get(source_id) or _resolve_source_row(cur, source_id, source_hints.get(source_id))
        if not s:
            s = current_item_by_source.get(source_id)
        if not s:
            raise ValueError(f"수출대기 품목 재구성 중 재고 #{source_id} 정보를 찾을 수 없습니다.")
        resolved_inventory_id = int(s.get("_resolved_inventory_id") or s.get("id") or source_id)
        source_location = str(s.get("location") or s.get("source_location") or "").strip()
        cur.execute("""INSERT INTO export_waiting_items(order_id,source_inventory_id,company,product_name,
            warehouse_name,lot,exp_date,source_location,waiting_location,qty,moved_at,confirmed)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,0)""",
            (order_id,resolved_inventory_id,s.get("company", ""),s.get("product_name", ""),s.get("warehouse_name", "") or "",
             s.get("lot", "-") or "-",s.get("exp_date", "-") or "-",source_location,P,qty,now))


def save_export_waiting_order(cart, *, country, buyer="", transport_method="미지정", export_no, editing_order_id=None):
    country = str(country or "").strip()
    buyer = str(buyer or "").strip()
    transport_method = str(transport_method or "").strip() or "미지정"
    export_no = str(export_no or "").strip()
    if not country:
        raise ValueError("국가를 입력하세요.")
    if transport_method not in TRANSPORT_METHODS:
        raise ValueError("운송방식을 항공, 해상, 핸드캐리, 미지정 중에서 선택하세요.")
    if not export_no:
        raise ValueError("수출번호를 입력하세요.")

    grouped = defaultdict(int)
    source_hints = {}
    for x in cart or []:
        qty = int(x.get("요청수량") or 0)
        if qty <= 0:
            continue
        inventory_id = int(x.get("id") or 0)
        grouped[inventory_id] += qty
        source_hints.setdefault(inventory_id, _cart_source_hint(x))
    if not grouped:
        raise ValueError("수출대기 등록할 품목이 없습니다.")

    buyer_title = buyer or "미지정"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    title = f"{country}-{buyer_title}-{transport_method}"
    with connect() as con:
        cur = con.cursor(); ensure_export_waiting_tables(cur)

        for inventory_id in grouped:
            current = _resolve_source_row(cur, inventory_id, source_hints.get(inventory_id))
            if current:
                source_hints[inventory_id] = current

        if editing_order_id:
            row = cur.execute("SELECT status FROM export_waiting_orders WHERE id=?", (int(editing_order_id),)).fetchone()
            if not row or row[0] != "waiting":
                raise ValueError("일부 확정되었거나 완료된 수출대기 건은 수정할 수 없습니다.")
            items_changed = _current_item_signature(cur, editing_order_id) != dict(grouped)
            cur.execute("UPDATE export_waiting_orders SET export_no=?,country=?,buyer=?,transport_method=?,title=?,updated_at=? WHERE id=?",
                        (export_no,country,buyer,transport_method,title,now,int(editing_order_id)))
            order_id = int(editing_order_id)
            if not items_changed:
                con.commit()
                return {"order_id":order_id,"row_count":len(grouped),"total_qty":sum(grouped.values()),"title":title}
            _apply_export_waiting_item_changes(cur, order_id, grouped, source_hints, now, title, export_no)
            total = sum(grouped.values())
        else:
            cur.execute("""INSERT INTO export_waiting_orders(export_no,country,buyer,transport_method,title,status,created_at,updated_at,created_by)
                VALUES(?,?,?,?,?,'waiting',?,?,?)""", (export_no,country,buyer,transport_method,title,now,now,_actor()))
            order_id = int(cur.lastrowid)

            total = 0
            for inventory_id, qty in grouped.items():
                s = _take_source(cur, inventory_id, qty, now, source_hints.get(inventory_id))
                resolved_inventory_id = int(s.get("_resolved_inventory_id") or s.get("id") or inventory_id)
                _add(cur, s, P, qty, now, 0)
                cur.execute("""INSERT INTO export_waiting_items(order_id,source_inventory_id,company,product_name,
                    warehouse_name,lot,exp_date,source_location,waiting_location,qty,moved_at,confirmed)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,0)""",
                    (order_id,resolved_inventory_id,s.get("company", ""),s.get("product_name", ""),s.get("warehouse_name", "") or "",
                     s.get("lot", "-") or "-",s.get("exp_date", "-") or "-",s.get("location", ""),P,qty,now))
                insert_transaction_log(cur, created_at=now, tx_type="위치이동", product_name=s.get("product_name", ""),
                    warehouse_name=s.get("warehouse_name", "") or "", lot=s.get("lot", "-"), exp_date=s.get("exp_date", "-"),
                    from_company=s.get("company", ""), from_location=s.get("location", ""), to_company=s.get("company", ""),
                    to_location=P, qty=qty, memo=f"수출대기 등록 / {title} / 수출번호: {export_no}")
                total += qty
        con.commit()
    return {"order_id":order_id,"row_count":len(grouped),"total_qty":total,"title":title}


def cancel_export_waiting_order(order_id):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with connect() as con:
        cur=con.cursor(); ensure_export_waiting_tables(cur)
        row=cur.execute("SELECT title,status FROM export_waiting_orders WHERE id=?",(int(order_id),)).fetchone()
        if not row or row[1] not in {"waiting", "partial"}:
            raise ValueError("취소할 수출대기 건이 없거나 이미 완료되었습니다.")
        _restore(cur,order_id,now,f"수출대기 취소 / {row[0]}")
        cur.execute("UPDATE export_waiting_orders SET status='cancelled',cancelled_at=?,updated_at=? WHERE id=?",(now,now,int(order_id)))
        con.commit()


def confirm_export_waiting_items(order_id, item_ids, *, erp_company, customer_code, customer_name):
    erp_company = str(erp_company or "").strip()
    customer_code = str(customer_code or "").strip()
    customer_name = str(customer_name or "").strip()
    selected_ids = sorted({int(x) for x in (item_ids or [])})
    if not selected_ids:
        raise ValueError("수출확정할 품목을 선택하세요.")
    if not erp_company or not customer_name:
        raise ValueError("ERP 사업장과 수출 매출처를 선택하세요.")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with connect() as con:
        cur = con.cursor(); ensure_export_waiting_tables(cur)
        order = cur.execute("SELECT title,status FROM export_waiting_orders WHERE id=?", (int(order_id),)).fetchone()
        if not order or order[1] not in {"waiting", "partial"}:
            raise ValueError("확정할 수출대기 건이 없거나 이미 처리되었습니다.")

        placeholders = ",".join("?" for _ in selected_ids)
        rows = cur.execute(f"""SELECT id,source_inventory_id,company,product_name,warehouse_name,lot,exp_date,
            source_location,waiting_location,qty,moved_at,COALESCE(confirmed,0),confirmed_company,
            confirmed_customer_code,confirmed_customer_name,confirmed_at
            FROM export_waiting_items
            WHERE order_id=? AND id IN ({placeholders}) AND COALESCE(confirmed,0)=0 ORDER BY id""",
            (int(order_id), *selected_ids)).fetchall()
        keys = ["id","source_inventory_id","company","product_name","warehouse_name","lot","exp_date",
                "source_location","waiting_location","qty","moved_at","confirmed","confirmed_company",
                "confirmed_customer_code","confirmed_customer_name","confirmed_at"]
        items = [dict(zip(keys, row)) for row in rows]
        if len(items) != len(selected_ids):
            raise ValueError("선택 품목 중 이미 확정되었거나 찾을 수 없는 항목이 있습니다.")

        for item in items:
            _take_p(cur, item, now)
            insert_transaction_log(cur, created_at=now, tx_type="출고", product_name=item["product_name"],
                warehouse_name=item.get("warehouse_name", ""), lot=item.get("lot", "-"), exp_date=item.get("exp_date", "-"),
                from_company=item["company"], from_location=P, to_company=erp_company,
                to_location="", qty=item["qty"], memo=f"수출확정 / {order[0]} / {customer_name}")
            cur.execute("""UPDATE export_waiting_items
                SET confirmed=1,confirmed_company=?,confirmed_customer_code=?,confirmed_customer_name=?,confirmed_at=?
                WHERE id=?""", (erp_company,customer_code,customer_name,now,int(item["id"])))

        remaining = cur.execute("SELECT COUNT(*) FROM export_waiting_items WHERE order_id=? AND COALESCE(confirmed,0)=0", (int(order_id),)).fetchone()[0]
        total_count = cur.execute("SELECT COUNT(*) FROM export_waiting_items WHERE order_id=?", (int(order_id),)).fetchone()[0]
        confirmed_count = int(total_count or 0) - int(remaining or 0)
        status = "confirmed" if int(remaining or 0) == 0 else "partial"
        cur.execute("""UPDATE export_waiting_orders
            SET status=?,erp_company=?,erp_customer_code=?,erp_customer_name=?,confirmed_at=?,updated_at=?
            WHERE id=?""", (status,erp_company,customer_code,customer_name,now,now,int(order_id)))
        con.commit()

    return {
        "status": status,
        "selected_count": len(selected_ids),
        "confirmed_count": confirmed_count,
        "total_count": int(total_count or 0),
    }
