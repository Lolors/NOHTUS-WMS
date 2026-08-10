from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime

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
    if "order_date" not in order_cols:
        c.execute("ALTER TABLE export_waiting_orders ADD COLUMN order_date TEXT")

    c.execute("""CREATE TABLE IF NOT EXISTS export_waiting_items(
        id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER NOT NULL, source_inventory_id INTEGER,
        waiting_inventory_id INTEGER, company TEXT NOT NULL, product_name TEXT NOT NULL,
        warehouse_name TEXT, lot TEXT, exp_date TEXT,
        source_location TEXT NOT NULL, waiting_location TEXT NOT NULL DEFAULT 'P', qty INTEGER NOT NULL,
        moved_at TEXT, confirmed INTEGER NOT NULL DEFAULT 0, confirmed_company TEXT,
        confirmed_customer_code TEXT, confirmed_customer_name TEXT, confirmed_at TEXT,
        FOREIGN KEY(order_id) REFERENCES export_waiting_orders(id))""")
    item_cols = {r[1] for r in c.execute("PRAGMA table_info(export_waiting_items)").fetchall()}
    additions = {
        "waiting_inventory_id": "INTEGER",
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
    c.execute("CREATE INDEX IF NOT EXISTS idx_export_waiting_items_waiting_inventory ON export_waiting_items(waiting_inventory_id)")
    # 기존 수출대기 자료는 제품명만으로 추정하지 않는다. 사업장·원본 ERP명·LOT·
    # 유통기한까지 모두 같은 P 재고가 정확히 한 행일 때만 고유 ID를 복구한다.
    c.execute("""
        UPDATE export_waiting_items
        SET waiting_inventory_id=(
            SELECT inv.id
            FROM inventory inv
            WHERE inv.location='P'
              AND inv.company=export_waiting_items.company
              AND inv.product_name=export_waiting_items.product_name
              AND IFNULL(inv.warehouse_name,'')=IFNULL(export_waiting_items.warehouse_name,'')
              AND IFNULL(inv.lot,'-')=IFNULL(export_waiting_items.lot,'-')
              AND IFNULL(inv.exp_date,'-')=IFNULL(export_waiting_items.exp_date,'-')
            ORDER BY inv.id
            LIMIT 1
        )
        WHERE waiting_inventory_id IS NULL
          AND COALESCE(confirmed,0)=0
          AND (
              SELECT COUNT(*)
              FROM inventory inv
              WHERE inv.location='P'
                AND inv.company=export_waiting_items.company
                AND inv.product_name=export_waiting_items.product_name
                AND IFNULL(inv.warehouse_name,'')=IFNULL(export_waiting_items.warehouse_name,'')
                AND IFNULL(inv.lot,'-')=IFNULL(export_waiting_items.lot,'-')
                AND IFNULL(inv.exp_date,'-')=IFNULL(export_waiting_items.exp_date,'-')
          )=1
    """)
    if own:
        con.commit(); con.close()


def _actor():
    try:
        from nohtus.auth import current_display_name, current_username
        return str(current_display_name() or current_username() or "").strip()
    except Exception:
        return ""


def repair_p_inventory_links(order_id):
    """끊어진 P 재고 ID를 저장 당시의 전체 재고키로 안전하게 복구한다."""
    if not order_id:
        return 0
    repaired = 0
    with connect() as con:
        broken = con.execute(
            """SELECT i.id,i.company,i.product_name,IFNULL(i.warehouse_name,''),
                      IFNULL(i.lot,'-'),IFNULL(i.exp_date,'-'),i.qty
               FROM export_waiting_items i
               LEFT JOIN inventory p
                 ON p.id=i.waiting_inventory_id AND p.location='P'
               WHERE i.order_id=? AND COALESCE(i.confirmed,0)=0
                 AND (p.id IS NULL OR COALESCE(p.qty,0) < i.qty)
               ORDER BY i.id""",
            (int(order_id),),
        ).fetchall()
        for item_id, company, product_name, warehouse_name, lot, exp_date, qty in broken:
            candidates = con.execute(
                """SELECT id FROM inventory
                   WHERE location='P' AND company=? AND product_name=?
                     AND IFNULL(warehouse_name,'')=?
                     AND IFNULL(lot,'-')=? AND IFNULL(exp_date,'-')=?
                     AND COALESCE(qty,0)>=?
                   ORDER BY id""",
                (company, product_name, warehouse_name, lot, exp_date, int(qty or 0)),
            ).fetchall()
            # 전체 재고키와 필요 수량을 모두 만족하는 행이 하나일 때만 자동 연결한다.
            if len(candidates) != 1:
                continue
            con.execute(
                "UPDATE export_waiting_items SET waiting_inventory_id=? WHERE id=?",
                (int(candidates[0][0]), int(item_id)),
            )
            repaired += 1
        if repaired:
            con.commit()
    return repaired


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


def _source_identity_matches(row, hint):
    """장바구니가 가리키던 재고와 현재 ID 행이 같은 재고인지 확인한다."""
    if not row:
        return False
    hint = hint or {}
    checks = (
        ("company", "company", ""),
        ("product_name", "product_name", ""),
        ("warehouse_name", "warehouse_name", ""),
        ("lot", "lot", "-"),
        ("exp_date", "exp_date", "-"),
    )
    for row_key, hint_key, default in checks:
        expected = str(hint.get(hint_key) or default).strip() or default
        # 예전 장바구니에 저장되지 않은 ERP 원본명은 비교 조건에서 제외한다.
        if hint_key == "warehouse_name" and not expected:
            continue
        actual = str(row.get(row_key) or default).strip() or default
        if expected and actual != expected:
            return False
    expected_location = str(
        hint.get("location") or hint.get("source_location") or ""
    ).strip()
    return not expected_location or str(row.get("location") or "").strip() == expected_location


def _resolve_source_row(cur, inventory_id, fallback=None, required_qty=0):
    source_id = int(inventory_id or 0)
    hint = fallback or {}
    required_qty = max(0, int(required_qty or 0))

    if source_id:
        row = _dict_row(cur, "SELECT * FROM inventory WHERE id=?", (source_id,))
        if (
            row
            and str(row.get("location") or "").strip() != P
            and _source_identity_matches(row, hint)
            and int(row.get("qty") or 0) >= required_qty
        ):
            return row

    company = str(hint.get("company") or "").strip()
    product_name = str(hint.get("product_name") or "").strip()
    lot = str(hint.get("lot") or "-").strip() or "-"
    exp_date = str(hint.get("exp_date") or "-").strip() or "-"
    location = str(hint.get("location") or hint.get("source_location") or "").strip()
    warehouse_name = str(hint.get("warehouse_name") or "").strip()
    if not company or not product_name or not location or location == P:
        return None

    sql = """SELECT * FROM inventory
        WHERE company=? AND product_name=? AND IFNULL(lot,'-')=?
          AND IFNULL(exp_date,'-')=? AND location=? AND COALESCE(qty,0)>0"""
    params = [company, product_name, lot, exp_date, location]
    if warehouse_name:
        sql += " AND IFNULL(warehouse_name,'')=?"
        params.append(warehouse_name)
    sql += " ORDER BY CASE WHEN id=? THEN 0 ELSE 1 END, qty DESC, id"
    params.append(source_id)

    rows = cur.execute(sql, tuple(params)).fetchall()
    columns = [d[0] for d in cur.description]
    candidates = [dict(zip(columns, row)) for row in rows]
    for candidate in candidates:
        if int(candidate.get("qty") or 0) >= required_qty:
            return candidate
    # 같은 재고키는 있지만 수량만 부족한 경우에는 행을 반환해 호출부가
    # 정확한 요청수량/현재수량 부족 안내를 표시하게 한다.
    return candidates[0] if candidates else None


def _take_source(cur, inventory_id, qty, now, fallback=None):
    s = _resolve_source_row(cur, inventory_id, fallback, required_qty=qty)
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
    waiting_inventory_id = int(item.get("waiting_inventory_id") or 0)
    row = None
    if waiting_inventory_id:
        row = cur.execute(
            "SELECT id,qty FROM inventory WHERE id=? AND location=?",
            (waiting_inventory_id, P),
        ).fetchone()
    if not row:
        # 과거 자료에 연결 ID가 없을 때만 전체 재고키가 정확히 같은 P 행을 사용한다.
        # 제품명이나 LOT 일부만 같은 다른 행을 임의로 고르지 않는다.
        row = _find(cur, item, P)
        if row and item.get("id"):
            cur.execute(
                "UPDATE export_waiting_items SET waiting_inventory_id=? WHERE id=?",
                (int(row[0]), int(item["id"])),
            )
            item["waiting_inventory_id"] = int(row[0])
    if not row or int(row[1] or 0) < take_qty:
        raise ValueError(f"P 로케이션의 {item['product_name']} 재고가 부족합니다.")
    cur.execute("UPDATE inventory SET qty=?,updated_at=? WHERE id=?", (int(row[1] or 0) - take_qty, now, int(row[0])))


def _items(cur, order_id, *, confirmed=None):
    where = "order_id=?"
    params = [int(order_id)]
    if confirmed is not None:
        where += " AND COALESCE(confirmed,0)=?"
        params.append(int(bool(confirmed)))
    rows = cur.execute(f"""SELECT id,source_inventory_id,waiting_inventory_id,company,product_name,warehouse_name,lot,exp_date,
        source_location,waiting_location,qty,moved_at,COALESCE(confirmed,0),confirmed_company,
        confirmed_customer_code,confirmed_customer_name,confirmed_at
        FROM export_waiting_items WHERE {where} ORDER BY id""", tuple(params)).fetchall()
    keys = ["id","source_inventory_id","waiting_inventory_id","company","product_name","warehouse_name","lot","exp_date",
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


def _current_item_signature(cur, order_id, *, confirmed=False):
    grouped = defaultdict(int)
    for item in _items(cur, order_id, confirmed=confirmed):
        grouped[int(item.get("source_inventory_id") or 0)] += int(item.get("qty") or 0)
    return dict(grouped)


def _apply_export_waiting_item_changes(cur, order_id, grouped, source_hints, now, title, export_no):
    current_items = _items(cur, order_id, confirmed=False)
    target_qty = {int(k): int(v) for k, v in dict(grouped).items() if int(v) > 0}

    restored_source_rows = {}
    for item in current_items:
        source_id = int(item.get("source_inventory_id") or 0)
        _take_p(cur, item, now)
        restored_id = _add(cur, item, item["source_location"], int(item["qty"]), now, 1)
        restored = _dict_row(cur, "SELECT * FROM inventory WHERE id=?", (restored_id,))
        if restored:
            restored_source_rows[source_id] = restored
            source_hints[source_id] = restored
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
            qty=item["qty"],
            memo=f"수출대기 수정 / 기존 품목 전체 원복 / {title} / 수출번호: {export_no}",
        )

    cur.execute("DELETE FROM export_waiting_items WHERE order_id=?", (int(order_id),))

    for source_id, qty in target_qty.items():
        hint = source_hints.get(source_id) or restored_source_rows.get(source_id)
        source = _take_source(cur, source_id, qty, now, hint)
        resolved_inventory_id = int(source.get("_resolved_inventory_id") or source.get("id") or source_id)
        waiting_inventory_id = _add(cur, source, P, qty, now, 0)
        cur.execute("""INSERT INTO export_waiting_items(order_id,source_inventory_id,waiting_inventory_id,company,product_name,
            warehouse_name,lot,exp_date,source_location,waiting_location,qty,moved_at,confirmed)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,0)""",
            (order_id,resolved_inventory_id,waiting_inventory_id,source.get("company", ""),source.get("product_name", ""),source.get("warehouse_name", "") or "",
             source.get("lot", "-") or "-",source.get("exp_date", "-") or "-",source.get("location", ""),P,qty,now))
        insert_transaction_log(
            cur,
            created_at=now,
            tx_type="위치이동",
            product_name=source.get("product_name", ""),
            warehouse_name=source.get("warehouse_name", "") or "",
            lot=source.get("lot", "-"),
            exp_date=source.get("exp_date", "-"),
            from_company=source.get("company", ""),
            from_location=source.get("location", ""),
            to_company=source.get("company", ""),
            to_location=P,
            qty=qty,
            memo=f"수출대기 수정 / 새 목록 재적재 / {title} / 수출번호: {export_no}",
        )


def _apply_confirmed_export_item_changes(
    cur,
    order_id,
    grouped,
    source_hints,
    now,
    title,
    export_no,
    *,
    erp_company,
    customer_code,
    customer_name,
    order_date,
):
    """확정 출고를 원복한 뒤 수정 목록을 같은 트랜잭션에서 다시 출고한다."""
    current_items = _items(cur, order_id, confirmed=True)
    target_qty = {int(k): int(v) for k, v in dict(grouped).items() if int(v) > 0}
    if not current_items:
        raise ValueError("수정할 수출확정 품목을 찾을 수 없습니다.")

    restored_source_rows = {}
    for item in current_items:
        source_id = int(item.get("source_inventory_id") or 0)
        restored_id = _add(cur, item, item["source_location"], int(item["qty"]), now, 1)
        restored = _dict_row(cur, "SELECT * FROM inventory WHERE id=?", (restored_id,))
        if restored:
            restored_source_rows[source_id] = restored
            source_hints[source_id] = restored
        insert_transaction_log(
            cur,
            created_at=now,
            tx_type="출고지시취소",
            product_name=item["product_name"],
            warehouse_name=item.get("warehouse_name", ""),
            lot=item.get("lot", "-"),
            exp_date=item.get("exp_date", "-"),
            from_company=erp_company,
            from_location="",
            to_company=item["company"],
            to_location=item["source_location"],
            qty=item["qty"],
            memo=f"수출확정 수정 / 기존 출고 원복 / {title} / 수출번호: {export_no}",
        )

    cur.execute("DELETE FROM export_waiting_items WHERE order_id=?", (int(order_id),))

    for source_id, qty in target_qty.items():
        hint = source_hints.get(source_id) or restored_source_rows.get(source_id)
        source = _take_source(cur, source_id, qty, now, hint)
        resolved_inventory_id = int(source.get("_resolved_inventory_id") or source.get("id") or source_id)
        waiting_inventory_id = _add(cur, source, P, qty, now, 0)
        waiting_item = {
            **source,
            "waiting_inventory_id": waiting_inventory_id,
            "qty": qty,
        }
        _take_p(cur, waiting_item, now)
        cur.execute(
            """INSERT INTO export_waiting_items(
                   order_id,source_inventory_id,waiting_inventory_id,company,product_name,
                   warehouse_name,lot,exp_date,source_location,waiting_location,qty,moved_at,
                   confirmed,confirmed_company,confirmed_customer_code,confirmed_customer_name,confirmed_at
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,1,?,?,?,?)""",
            (
                order_id,
                resolved_inventory_id,
                waiting_inventory_id,
                source.get("company", ""),
                source.get("product_name", ""),
                source.get("warehouse_name", "") or "",
                source.get("lot", "-") or "-",
                source.get("exp_date", "-") or "-",
                source.get("location", ""),
                P,
                qty,
                now,
                erp_company,
                customer_code,
                customer_name,
                now,
            ),
        )
        insert_transaction_log(
            cur,
            created_at=now,
            tx_type="출고",
            product_name=source.get("product_name", ""),
            warehouse_name=source.get("warehouse_name", "") or "",
            lot=source.get("lot", "-"),
            exp_date=source.get("exp_date", "-"),
            from_company=source.get("company", ""),
            from_location=P,
            to_company=erp_company,
            to_location="",
            qty=qty,
            memo=(
                f"수출확정 수정 / 새 출고 목록 / {title} / {customer_name} / "
                f"출고일자: {order_date} / 수출번호: {export_no}"
            ),
        )

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

        for inventory_id, requested_qty in grouped.items():
            current = _resolve_source_row(
                cur,
                inventory_id,
                source_hints.get(inventory_id),
                required_qty=requested_qty,
            )
            if current:
                source_hints[inventory_id] = current

        if editing_order_id:
            row = _dict_row(
                cur,
                """SELECT status,erp_company,erp_customer_code,erp_customer_name,order_date
                   FROM export_waiting_orders WHERE id=?""",
                (int(editing_order_id),),
            )
            if not row or row["status"] not in {"waiting", "confirmed"}:
                raise ValueError("일부 확정되었거나 취소된 수출대기 건은 수정할 수 없습니다.")
            is_confirmed = row["status"] == "confirmed"
            items_changed = _current_item_signature(
                cur,
                editing_order_id,
                confirmed=is_confirmed,
            ) != dict(grouped)
            cur.execute("UPDATE export_waiting_orders SET export_no=?,country=?,buyer=?,transport_method=?,title=?,updated_at=? WHERE id=?",
                        (export_no,country,buyer,transport_method,title,now,int(editing_order_id)))
            order_id = int(editing_order_id)
            if not items_changed:
                con.commit()
                return {"order_id":order_id,"row_count":len(grouped),"total_qty":sum(grouped.values()),"title":title}
            if is_confirmed:
                _apply_confirmed_export_item_changes(
                    cur,
                    order_id,
                    grouped,
                    source_hints,
                    now,
                    title,
                    export_no,
                    erp_company=str(row.get("erp_company") or ""),
                    customer_code=str(row.get("erp_customer_code") or ""),
                    customer_name=str(row.get("erp_customer_name") or ""),
                    order_date=str(row.get("order_date") or ""),
                )
            else:
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
                waiting_inventory_id = _add(cur, s, P, qty, now, 0)
                cur.execute("""INSERT INTO export_waiting_items(order_id,source_inventory_id,waiting_inventory_id,company,product_name,
                    warehouse_name,lot,exp_date,source_location,waiting_location,qty,moved_at,confirmed)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,0)""",
                    (order_id,resolved_inventory_id,waiting_inventory_id,s.get("company", ""),s.get("product_name", ""),s.get("warehouse_name", "") or "",
                     s.get("lot", "-") or "-",s.get("exp_date", "-") or "-",s.get("location", ""),P,qty,now))
                insert_transaction_log(cur, created_at=now, tx_type="위치이동", product_name=s.get("product_name", ""),
                    warehouse_name=s.get("warehouse_name", "") or "", lot=s.get("lot", "-"), exp_date=s.get("exp_date", "-"),
                    from_company=s.get("company", ""), from_location=s.get("location", ""), to_company=s.get("company", ""),
                    to_location=P, qty=qty, memo=f"수출대기 등록 / {title} / 수출번호: {export_no}")
                total += qty
        con.commit()
    return {"order_id":order_id,"row_count":len(grouped),"total_qty":total,"title":title}


def update_confirmed_export_waiting_metadata(
    order_id,
    *,
    country,
    buyer="",
    transport_method="미지정",
    export_no,
):
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

    title = f"{country}-{buyer or '미지정'}-{transport_method}"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with connect() as con:
        cur = con.cursor()
        ensure_export_waiting_tables(cur)
        row = cur.execute(
            "SELECT status FROM export_waiting_orders WHERE id=?",
            (int(order_id),),
        ).fetchone()
        if not row or str(row[0]) != "confirmed":
            raise ValueError("수출확정된 건만 이 수정창에서 변경할 수 있습니다.")
        cur.execute(
            """UPDATE export_waiting_orders
               SET country=?,buyer=?,transport_method=?,export_no=?,title=?,updated_at=?
               WHERE id=?""",
            (country, buyer, transport_method, export_no, title, now, int(order_id)),
        )
        con.commit()
    return title


def merge_export_waiting_orders(source_order_id, target_order_id):
    source_order_id = int(source_order_id or 0)
    target_order_id = int(target_order_id or 0)
    if not source_order_id or not target_order_id:
        raise ValueError("합칠 수출대기 건과 대상 수출대기 건을 선택하세요.")
    if source_order_id == target_order_id:
        raise ValueError("같은 수출대기 건끼리는 합칠 수 없습니다.")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with connect() as con:
        cur = con.cursor()
        ensure_export_waiting_tables(cur)
        source = _dict_row(cur,"SELECT id,export_no,title,status FROM export_waiting_orders WHERE id=?",(source_order_id,))
        target = _dict_row(cur,"SELECT id,export_no,title,status FROM export_waiting_orders WHERE id=?",(target_order_id,))
        if not source:
            raise ValueError("합칠 원본 수출대기 건을 찾을 수 없습니다.")
        if not target:
            raise ValueError("병합 대상 수출대기 건을 찾을 수 없습니다.")
        if source["status"] != "waiting" or target["status"] != "waiting":
            raise ValueError("아직 품목이 확정되지 않은 수출대기 건끼리만 합칠 수 있습니다.")

        confirmed_count = cur.execute("""SELECT COUNT(*) FROM export_waiting_items
               WHERE order_id IN (?,?) AND COALESCE(confirmed,0)<>0""",(source_order_id, target_order_id)).fetchone()[0]
        if int(confirmed_count or 0):
            raise ValueError("수출확정된 품목이 있는 수출대기 건은 합칠 수 없습니다.")

        source_summary = cur.execute("SELECT COUNT(*),COALESCE(SUM(qty),0) FROM export_waiting_items WHERE order_id=?",(source_order_id,)).fetchone()
        if not int(source_summary[0] or 0):
            raise ValueError("원본 수출대기 건에 합칠 품목이 없습니다.")

        grouped_items = cur.execute("""SELECT source_inventory_id,waiting_inventory_id,company,product_name,warehouse_name,lot,exp_date,
                      source_location,waiting_location,SUM(qty) AS qty,MIN(moved_at) AS moved_at
               FROM export_waiting_items
               WHERE order_id IN (?,?)
               GROUP BY source_inventory_id,waiting_inventory_id,company,product_name,warehouse_name,lot,exp_date,
                        source_location,waiting_location
               ORDER BY MIN(id)""",(target_order_id, source_order_id)).fetchall()

        cur.execute("DELETE FROM export_waiting_items WHERE order_id IN (?,?)",(target_order_id, source_order_id))
        for item in grouped_items:
            cur.execute("""INSERT INTO export_waiting_items(
                       order_id,source_inventory_id,waiting_inventory_id,company,product_name,warehouse_name,lot,exp_date,
                       source_location,waiting_location,qty,moved_at,confirmed
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,0)""",(target_order_id, *item))

        cur.execute("DELETE FROM export_waiting_orders WHERE id=?", (source_order_id,))
        cur.execute("UPDATE export_waiting_orders SET updated_at=? WHERE id=?",(now, target_order_id))
        con.commit()

    return {
        "source_order_id": source_order_id,
        "source_export_no": str(source["export_no"] or ""),
        "target_order_id": target_order_id,
        "target_export_no": str(target["export_no"] or ""),
        "target_title": str(target["title"] or ""),
        "merged_row_count": int(source_summary[0] or 0),
        "merged_qty": int(source_summary[1] or 0),
        "result_row_count": len(grouped_items),
        "result_qty": sum(int(item[9] or 0) for item in grouped_items),
    }


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


def _normalize_shipment_date(value):
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    text = str(value or "").strip()
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        raise ValueError("출고일자를 선택하세요.")


def confirm_export_waiting_items(
    order_id,
    item_ids,
    *,
    erp_company,
    customer_code,
    customer_name,
    shipment_date,
):
    erp_company = str(erp_company or "").strip()
    customer_code = str(customer_code or "").strip()
    customer_name = str(customer_name or "").strip()
    order_date = _normalize_shipment_date(shipment_date)
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
        rows = cur.execute(f"""SELECT id,source_inventory_id,waiting_inventory_id,company,product_name,warehouse_name,lot,exp_date,
            source_location,waiting_location,qty,moved_at,COALESCE(confirmed,0),confirmed_company,
            confirmed_customer_code,confirmed_customer_name,confirmed_at
            FROM export_waiting_items
            WHERE order_id=? AND id IN ({placeholders}) AND COALESCE(confirmed,0)=0 ORDER BY id""",
            (int(order_id), *selected_ids)).fetchall()
        keys = ["id","source_inventory_id","waiting_inventory_id","company","product_name","warehouse_name","lot","exp_date",
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
                to_location="", qty=item["qty"], memo=f"수출확정 / {order[0]} / {customer_name} / 출고일자: {order_date}")
            cur.execute("""UPDATE export_waiting_items
                SET confirmed=1,confirmed_company=?,confirmed_customer_code=?,confirmed_customer_name=?,confirmed_at=?
                WHERE id=?""", (erp_company,customer_code,customer_name,now,int(item["id"])))

        remaining = cur.execute("SELECT COUNT(*) FROM export_waiting_items WHERE order_id=? AND COALESCE(confirmed,0)=0", (int(order_id),)).fetchone()[0]
        total_count = cur.execute("SELECT COUNT(*) FROM export_waiting_items WHERE order_id=?", (int(order_id),)).fetchone()[0]
        confirmed_count = int(total_count or 0) - int(remaining or 0)
        status = "confirmed" if int(remaining or 0) == 0 else "partial"
        cur.execute("""UPDATE export_waiting_orders
            SET status=?,erp_company=?,erp_customer_code=?,erp_customer_name=?,order_date=?,confirmed_at=?,updated_at=?
            WHERE id=?""", (status,erp_company,customer_code,customer_name,order_date,now,now,int(order_id)))
        con.commit()

    return {
        "status": status,
        "selected_count": len(selected_ids),
        "confirmed_count": confirmed_count,
        "total_count": int(total_count or 0),
        "order_date": order_date,
    }
