from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime

from nohtus.db import connect
from nohtus.services.inventory import insert_transaction_log

P = "P"
STAGING_LOCATIONS = ("P", "T1", "T2", "T3", "T4", "T5")
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
    # 유통기한까지 모두 같은, 그 품목이 실제로 적재된 위치(waiting_location)의
    # 재고가 정확히 한 행일 때만 고유 ID를 복구한다.
    c.execute("""
        UPDATE export_waiting_items
        SET waiting_inventory_id=(
            SELECT inv.id
            FROM inventory inv
            WHERE inv.location=IFNULL(export_waiting_items.waiting_location,'P')
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
              WHERE inv.location=IFNULL(export_waiting_items.waiting_location,'P')
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
    """끊어진 수출대기 재고 ID를 저장 당시의 전체 재고키로 안전하게 복구한다."""
    if not order_id:
        return 0
    repaired = 0
    with connect() as con:
        broken = con.execute(
            """SELECT i.id,i.company,i.product_name,IFNULL(i.warehouse_name,''),
                      IFNULL(i.lot,'-'),IFNULL(i.exp_date,'-'),i.qty,
                      IFNULL(i.waiting_location,'P')
               FROM export_waiting_items i
               LEFT JOIN inventory p
                 ON p.id=i.waiting_inventory_id
                AND UPPER(TRIM(COALESCE(p.location,'')))=UPPER(TRIM(IFNULL(i.waiting_location,'P')))
               WHERE i.order_id=? AND COALESCE(i.confirmed,0)=0
                 AND (p.id IS NULL OR COALESCE(p.qty,0) < i.qty)
               ORDER BY i.id""",
            (int(order_id),),
        ).fetchall()
        for item_id, company, product_name, warehouse_name, lot, exp_date, qty, waiting_location in broken:
            candidates = con.execute(
                """SELECT id FROM inventory
                   WHERE UPPER(TRIM(COALESCE(location,'')))=UPPER(TRIM(?))
                     AND company=? AND product_name=?
                     AND IFNULL(warehouse_name,'')=?
                     AND IFNULL(lot,'-')=? AND IFNULL(exp_date,'-')=?
                     AND COALESCE(qty,0)>=?
                   ORDER BY id""",
                (waiting_location, company, product_name, warehouse_name, lot, exp_date, int(qty or 0)),
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
    """장바구니가 가리키던 재고와 현재 ID 행이 같은 재고인지 확인한다.

    위치는 비교하지 않는다 - 재고이동 등록 같은 정상적인 이동으로 실제
    위치가 바뀌는 건 흔한 일이고, 이 함수는 항상 정확한 재고 id를 이미 알고
    있는 상태에서 호출된다(같은 id면 같은 재고). 예전에는 위치까지 정확히
    같아야만 같은 재고로 인정해서, 예약 이후 정상적으로 재고이동된 재고를
    repair_broken_waiting_reservations가 "찾을 수 없음"으로 오판하는
    원인이었다."""
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
    return True


def _resolve_source_row(cur, inventory_id, fallback=None, required_qty=0):
    source_id = int(inventory_id or 0)
    hint = fallback or {}
    required_qty = max(0, int(required_qty or 0))

    if source_id:
        row = _dict_row(cur, "SELECT * FROM inventory WHERE id=?", (source_id,))
        row_location = str((row or {}).get("location") or "").strip()
        hinted_location = str(hint.get("location") or hint.get("source_location") or "").strip()
        if (
            row
            and row_location in STAGING_LOCATIONS
            and hinted_location in STAGING_LOCATIONS
            and _source_identity_matches(row, hint)
        ):
            return row
        if (
            row
            and row_location not in STAGING_LOCATIONS
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
    if not company or not product_name or not location or location in STAGING_LOCATIONS:
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
    if not candidates:
        # 재고조사나 위치 이동으로 원본 ID와 로케이션이 함께 바뀐 구형 연결행은
        # 완전 동일한 재고키가 다른 일반 로케이션에 단 하나만 있을 때만 복구한다.
        staging_placeholders = ",".join("?" for _ in STAGING_LOCATIONS)
        relocated_sql = f"""SELECT * FROM inventory
            WHERE company=? AND product_name=? AND IFNULL(lot,'-')=?
              AND IFNULL(exp_date,'-')=? AND location NOT IN ({staging_placeholders}) AND COALESCE(qty,0)>0"""
        relocated_params = [company, product_name, lot, exp_date, *STAGING_LOCATIONS]
        if warehouse_name:
            relocated_sql += " AND IFNULL(warehouse_name,'')=?"
            relocated_params.append(warehouse_name)
        relocated_sql += " ORDER BY qty DESC,id"
        relocated_rows = cur.execute(relocated_sql, tuple(relocated_params)).fetchall()
        relocated_columns = [d[0] for d in cur.description]
        relocated = [dict(zip(relocated_columns, row)) for row in relocated_rows]
        eligible = [
            row for row in relocated
            if int(row.get("qty") or 0) >= required_qty
        ]
        if len(eligible) == 1:
            return eligible[0]
    # 같은 재고키는 있지만 수량만 부족한 경우에는 행을 반환해 호출부가
    # 정확한 요청수량/현재수량 부족 안내를 표시하게 한다.
    return candidates[0] if candidates else None


def _take_source(cur, inventory_id, qty, now, fallback=None):
    s = _resolve_source_row(cur, inventory_id, fallback, required_qty=qty)
    if not s:
        existing = _resolve_source_row(cur, inventory_id, fallback, required_qty=0)
        if existing:
            available = int(existing.get("qty") or 0)
            raise ValueError(
                f"{existing.get('product_name','제품')} 재고 부족: 요청 {qty}EA / 현재 {available}EA"
            )
        hint = fallback or {}
        label = " / ".join(x for x in [
            str(hint.get("company") or "").strip(),
            str(hint.get("location") or hint.get("source_location") or "").strip(),
            str(hint.get("product_name") or "").strip(),
        ] if x)
        suffix = f" ({label})" if label else ""
        raise ValueError(f"재고 #{inventory_id}를 찾을 수 없습니다.{suffix}")
    available = int(s.get("qty") or 0)
    source_location = str(s.get("location") or "").strip()
    if source_location in STAGING_LOCATIONS:
        reserved = cur.execute(
            """SELECT COALESCE(SUM(COALESCE(i.qty,0)),0)
               FROM export_waiting_items i JOIN export_waiting_orders o ON o.id=i.order_id
               WHERE i.waiting_inventory_id=? AND COALESCE(i.confirmed,0)=0
                 AND o.status IN ('waiting','partial','confirmed')""",
            (int(s.get("id") or 0),),
        ).fetchone()[0]
        available -= int(reserved or 0)
        if qty <= 0 or qty > available:
            raise ValueError(
                f"{source_location} 로케이션의 {s.get('product_name','제품')} 미예약 재고가 부족합니다. "
                f"요청 {qty}EA / 가능 {max(0, available)}EA"
            )
        s["_resolved_inventory_id"] = int(s.get("id") or 0)
        s["_already_staged"] = True
        return s
    if qty <= 0 or qty > available:
        raise ValueError(f"{s.get('product_name','제품')} 재고 부족: 요청 {qty}EA / 현재 {available}EA")
    resolved_id = int(s.get("id") or 0)
    cur.execute("UPDATE inventory SET qty=?,updated_at=? WHERE id=?", (available - qty, now, resolved_id))
    s["_resolved_inventory_id"] = resolved_id
    return s


def _place_source_in_staging(cur, source, qty, now, staging_location):
    """일반 재고는 지정한 수출대기 위치로 이동하고, 이미 그 위치의 미예약분은
    수량을 더하지 않고 예약만 연결한다."""
    if source.get("_already_staged"):
        return int(source.get("id") or 0), False
    return _add(cur, source, staging_location, qty, now, 0), True


def _take_p(cur, item, now, qty=None):
    take_qty = int(item.get("qty") or 0) if qty is None else int(qty or 0)
    waiting_inventory_id = int(item.get("waiting_inventory_id") or 0)
    staging_location = str(item.get("waiting_location") or "").strip() or P
    rows = cur.execute(
        """SELECT id,COALESCE(qty,0) FROM inventory
           WHERE company=? AND product_name=? AND IFNULL(warehouse_name,'')=?
             AND IFNULL(lot,'-')=? AND IFNULL(exp_date,'-')=? AND location=?
           ORDER BY CASE WHEN id=? THEN 0 ELSE 1 END, qty DESC, id""",
        (
            item.get("company", ""), item.get("product_name", ""),
            item.get("warehouse_name", "") or "", item.get("lot", "-") or "-",
            item.get("exp_date", "-") or "-", staging_location, waiting_inventory_id,
        ),
    ).fetchall()
    available = sum(int(row[1] or 0) for row in rows)
    if take_qty <= 0 or available < take_qty:
        raise ValueError(f"{staging_location} 로케이션의 {item['product_name']} 재고가 부족합니다.")

    # 재고조사·행 병합 후 같은 P 재고가 여러 ID로 나뉘어도 총량을 사용한다.
    # 연결된 행을 우선 차감하고, 부족하면 완전 일치하는 다른 P 행에서 이어서 차감한다.
    remaining = take_qty
    linked_id = 0
    for inventory_id, row_qty in rows:
        row_qty = int(row_qty or 0)
        used = min(row_qty, remaining)
        if used:
            cur.execute(
                "UPDATE inventory SET qty=?,updated_at=? WHERE id=?",
                (row_qty - used, now, int(inventory_id)),
            )
            linked_id = linked_id or int(inventory_id)
            remaining -= used
        if remaining <= 0:
            break
    if linked_id and item.get("id") and linked_id != waiting_inventory_id:
        cur.execute(
            "UPDATE export_waiting_items SET waiting_inventory_id=? WHERE id=?",
            (linked_id, int(item["id"])),
        )
        item["waiting_inventory_id"] = linked_id


def _restore_waiting_item(cur, item, now, qty=None):
    """P 예약분을 원위치로 돌리되 이미 원복된 재고는 중복 가산하지 않는다."""
    restore_qty = int(item.get("qty") or 0) if qty is None else int(qty or 0)
    restore_item = dict(item)
    restore_item["qty"] = restore_qty
    try:
        _take_p(cur, restore_item, now)
    except ValueError:
        # 주문행을 먼저 삭제하거나 재고조사에서 P→원위치로 옮긴 경우에는
        # 수출대기 연결만 남고 실재고는 이미 source_location에 존재한다.
        # 그 수량을 다시 더하면 재고가 부풀기 때문에 현재 원본행을 그대로 쓴다.
        source = _resolve_source_row(
            cur,
            item.get("source_inventory_id"),
            item,
            required_qty=restore_qty,
        )
        if not source or int(source.get("qty") or 0) < restore_qty:
            raise
        return source, False

    restored_id = _add(cur, item, item["source_location"], restore_qty, now, 1)
    restored = _dict_row(cur, "SELECT * FROM inventory WHERE id=?", (restored_id,))
    return restored, True


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
        _, moved_from_p = _restore_waiting_item(cur, item, now)
        if not moved_from_p:
            continue
        insert_transaction_log(cur, created_at=now, tx_type="위치이동", product_name=item["product_name"],
            warehouse_name=item.get("warehouse_name", ""), lot=item.get("lot", "-"), exp_date=item.get("exp_date", "-"),
            from_company=item["company"], from_location=str(item.get("waiting_location") or "").strip() or P,
            to_company=item["company"],
            to_location=item["source_location"], qty=item["qty"], memo=memo)


def _current_item_signature(cur, order_id, *, confirmed=False):
    grouped = defaultdict(int)
    for item in _items(cur, order_id, confirmed=confirmed):
        grouped[int(item.get("source_inventory_id") or 0)] += int(item.get("qty") or 0)
    return dict(grouped)


def _waiting_inventory_matches_items(cur, order_id):
    """미확정 연결 수량만큼 실제 P 재고가 남아 있는지 확인한다."""
    required_by_inventory = defaultdict(int)
    available_by_inventory = {}
    for item in _items(cur, order_id, confirmed=False):
        waiting_id = int(item.get("waiting_inventory_id") or 0)
        staging_location = str(item.get("waiting_location") or "").strip() or P
        row = None
        if waiting_id:
            row = cur.execute(
                "SELECT id,qty FROM inventory WHERE id=? AND location=?",
                (waiting_id, staging_location),
            ).fetchone()
        if not row:
            row = _find(cur, item, staging_location)
        if not row:
            return False
        inventory_id = int(row[0])
        required_by_inventory[inventory_id] += int(item.get("qty") or 0)
        available_by_inventory[inventory_id] = int(row[1] or 0)
    return all(
        available_by_inventory.get(inventory_id, 0) >= required
        for inventory_id, required in required_by_inventory.items()
    )


def _waiting_item_link_is_healthy(cur, item):
    """이 품목이 가리키는 대기 재고(waiting_inventory_id)가 지금도 요청 수량만큼
    실제로 남아 있는지 확인한다. 수량이 그대로인 품목을 건드리지 않고 넘어가려면,
    먼저 연결이 멀쩡한지부터 확인해야 한다 — 이미 깨진 연결까지 그냥 넘기면
    재고 정합성이 어긋난 채로 영영 고쳐지지 않는다."""
    waiting_inventory_id = int(item.get("waiting_inventory_id") or 0)
    if not waiting_inventory_id:
        return False
    row = cur.execute("SELECT qty FROM inventory WHERE id=?", (waiting_inventory_id,)).fetchone()
    return bool(row) and int(row[0] or 0) >= int(item.get("qty") or 0)


def _apply_export_waiting_item_changes(cur, order_id, grouped, source_hints, now, title, export_no, target_location=P):
    current_items = _items(cur, order_id, confirmed=False)
    target_qty = {int(k): int(v) for k, v in dict(grouped).items() if int(v) > 0}
    # 이미 있던 품목은 재저장할 때마다 매번 target_location(기본 P)으로 슬쩍
    # 옮겨가면 안 된다 — 실제로 T3 등에 놓인 재고가 관계없는 수정 저장 한 번에
    # 조용히 P로 되돌아가는 사고를 막기 위해, 기존 위치를 그대로 유지하고
    # target_location은 이번에 새로 추가되는 품목에만 적용한다.
    prior_location_by_source = {
        int(item.get("source_inventory_id") or 0): str(item.get("waiting_location") or "").strip() or P
        for item in current_items
    }

    # 수량도 그대로고 연결도 멀쩡한 품목은 절대 건드리지 않는다 — 예전에는
    # 매 저장마다 미확정 품목 전체를 원위치로 되돌렸다가 다시 꺼내 담았는데,
    # 그 되돌리기/재적재 과정이 source_inventory_id의 원래 위치(T1~T5)를
    # '수출대기 보관 위치'로 오인해 관계없는 품목까지 "재고를 찾을 수
    # 없습니다" 오류로 저장을 막는 사고로 이어졌다. 다만 연결이 이미 깨진
    # 품목은(예: 재고조사로 대기 재고가 원위치로 옮겨진 경우) 수량이 그대로여도
    # 여전히 복구를 시도해야 한다.
    remaining_target = dict(target_qty)
    restored_source_rows = {}
    for item in current_items:
        source_id = int(item.get("source_inventory_id") or 0)
        old_qty = int(item.get("qty") or 0)
        desired_qty = remaining_target.pop(source_id, 0)
        if desired_qty == old_qty and _waiting_item_link_is_healthy(cur, item):
            continue
        try:
            restored, moved_from_p = _restore_waiting_item(cur, item, now)
        except ValueError:
            # 사용자가 이 원본 재고를 목록에서 완전히 삭제하는 경우에는 이미
            # 대기 위치와 원위치 양쪽에 재고가 없어도 깨진 대기 연결 자체는
            # 제거한다. 남겨 둘 수량이 있는 수정은 재고 정합성을 확인해야
            # 하므로 기존 부족 오류를 그대로 전파한다.
            if desired_qty > 0:
                raise
            cur.execute("DELETE FROM export_waiting_items WHERE id=?", (int(item["id"]),))
            continue
        if restored:
            restored_source_rows[source_id] = restored
            source_hints[source_id] = restored
        cur.execute("DELETE FROM export_waiting_items WHERE id=?", (int(item["id"]),))
        if moved_from_p:
            insert_transaction_log(
                cur,
                created_at=now,
                tx_type="위치이동",
                product_name=item["product_name"],
                warehouse_name=item.get("warehouse_name", ""),
                lot=item.get("lot", "-"),
                exp_date=item.get("exp_date", "-"),
                from_company=item["company"],
                from_location=str(item.get("waiting_location") or "").strip() or P,
                to_company=item["company"],
                to_location=item["source_location"],
                qty=item["qty"],
                memo=f"수출대기 수정 / 변경된 품목 원복 / {title} / 수출번호: {export_no}",
            )
        if desired_qty > 0:
            remaining_target[source_id] = desired_qty

    for source_id, qty in remaining_target.items():
        hint = source_hints.get(source_id) or restored_source_rows.get(source_id)
        source = _take_source(cur, source_id, qty, now, hint)
        resolved_inventory_id = int(source.get("_resolved_inventory_id") or source.get("id") or source_id)
        item_target_location = prior_location_by_source.get(source_id, target_location)
        waiting_inventory_id, moved_to_p = _place_source_in_staging(cur, source, qty, now, item_target_location)
        cur.execute("""INSERT INTO export_waiting_items(order_id,source_inventory_id,waiting_inventory_id,company,product_name,
            warehouse_name,lot,exp_date,source_location,waiting_location,qty,moved_at,confirmed)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,0)""",
            (order_id,resolved_inventory_id,waiting_inventory_id,source.get("company", ""),source.get("product_name", ""),source.get("warehouse_name", "") or "",
             source.get("lot", "-") or "-",source.get("exp_date", "-") or "-",source.get("location", ""),item_target_location,qty,now))
        if moved_to_p:
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
            to_location=item_target_location,
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
    target_location=P,
):
    """기존 확정분은 유지하고 목록의 증감분만 재고에 반영한다.

    같은 원본 재고의 기존 확정 수량까지는 확정 행과 ERP 매출 정보를 그대로
    둔다. 줄어든 수량만 출고 취소로 원복하고, 늘어난 수량과 새 품목은 P에
    적재한 미확정 행으로 추가한다.
    """
    current_items = _items(cur, order_id, confirmed=True)
    remaining_target = {int(k): int(v) for k, v in dict(grouped).items() if int(v) > 0}
    if not current_items:
        raise ValueError("수정할 수출확정 품목을 찾을 수 없습니다.")

    # 이미 미확정으로 대기 중인 품목의 증가분은, 새로 추가되는 품목과 달리
    # 원래 있던 위치(예: T3)에 그대로 더 쌓는다 — target_location(기본 P)은
    # 이번에 처음 담기는 품목에만 적용한다.
    prior_location_by_source = {
        int(item.get("source_inventory_id") or 0): str(item.get("waiting_location") or "").strip() or P
        for item in _items(cur, order_id, confirmed=False)
    }

    for item in current_items:
        source_id = int(item.get("source_inventory_id") or 0)
        old_qty = int(item.get("qty") or 0)
        kept_qty = min(old_qty, int(remaining_target.get(source_id, 0)))
        removed_qty = old_qty - kept_qty
        remaining_target[source_id] = int(remaining_target.get(source_id, 0)) - kept_qty

        if kept_qty:
            cur.execute("UPDATE export_waiting_items SET qty=? WHERE id=?", (kept_qty, int(item["id"])))
        else:
            cur.execute("DELETE FROM export_waiting_items WHERE id=?", (int(item["id"]),))

        if not removed_qty:
            continue
        restored_id = _add(cur, item, item["source_location"], removed_qty, now, 1)
        restored = _dict_row(cur, "SELECT * FROM inventory WHERE id=?", (restored_id,))
        if restored:
            source_hints[source_id] = restored
        insert_transaction_log(
            cur,
            created_at=now,
            tx_type="출고지시취소",
            product_name=item["product_name"],
            warehouse_name=item.get("warehouse_name", ""),
            lot=item.get("lot", "-"),
            exp_date=item.get("exp_date", "-"),
            from_company=str(item.get("confirmed_company") or ""),
            from_location="",
            to_company=item["company"],
            to_location=item["source_location"],
            qty=removed_qty,
            memo=(
                f"수출확정 수정 / 감소분 원복 / {title} / "
                f"{str(item.get('confirmed_customer_name') or '')} / 수출번호: {export_no}"
            ),
        )

    # 부분 확정 건을 다시 수정할 때 이미 P에 남아 있는 미확정 수량도 목표에
    # 포함한다. 그대로 필요한 수량은 행과 재고를 유지하고, 감소분만 원복한다.
    # 이 계산이 없으면 기존 미확정분까지 신규 증가분으로 오인해 재고를 중복
    # 차감한다.
    for item in _items(cur, order_id, confirmed=False):
        source_id = int(item.get("source_inventory_id") or 0)
        old_qty = int(item.get("qty") or 0)
        kept_qty = min(old_qty, int(remaining_target.get(source_id, 0)))
        removed_qty = old_qty - kept_qty
        remaining_target[source_id] = int(remaining_target.get(source_id, 0)) - kept_qty

        if kept_qty:
            cur.execute("UPDATE export_waiting_items SET qty=? WHERE id=?", (kept_qty, int(item["id"])))
        else:
            cur.execute("DELETE FROM export_waiting_items WHERE id=?", (int(item["id"]),))

        if not removed_qty:
            continue
        restored, moved_from_p = _restore_waiting_item(cur, item, now, removed_qty)
        if restored:
            source_hints[source_id] = restored
        if not moved_from_p:
            continue
        insert_transaction_log(
            cur,
            created_at=now,
            tx_type="위치이동",
            product_name=item["product_name"],
            warehouse_name=item.get("warehouse_name", ""),
            lot=item.get("lot", "-"),
            exp_date=item.get("exp_date", "-"),
            from_company=item["company"],
            from_location=str(item.get("waiting_location") or "").strip() or P,
            to_company=item["company"],
            to_location=item["source_location"],
            qty=removed_qty,
            memo=f"수출확정 수정 / 미확정 감소분 원복 / {title} / 수출번호: {export_no}",
        )

    for source_id, qty in remaining_target.items():
        if qty <= 0:
            continue
        hint = source_hints.get(source_id)
        source = _take_source(cur, source_id, qty, now, hint)
        resolved_inventory_id = int(source.get("_resolved_inventory_id") or source.get("id") or source_id)
        item_target_location = prior_location_by_source.get(source_id, target_location)
        waiting_inventory_id, moved_to_p = _place_source_in_staging(cur, source, qty, now, item_target_location)
        existing_waiting = _dict_row(
            cur,
            """SELECT id,qty FROM export_waiting_items
               WHERE order_id=? AND source_inventory_id=? AND COALESCE(confirmed,0)=0
               ORDER BY id LIMIT 1""",
            (int(order_id), int(resolved_inventory_id)),
        )
        if existing_waiting:
            cur.execute(
                "UPDATE export_waiting_items SET qty=?,waiting_inventory_id=?,waiting_location=?,moved_at=? WHERE id=?",
                (
                    int(existing_waiting.get("qty") or 0) + qty,
                    waiting_inventory_id,
                    item_target_location,
                    now,
                    int(existing_waiting["id"]),
                ),
            )
        else:
            cur.execute(
                """INSERT INTO export_waiting_items(
                   order_id,source_inventory_id,waiting_inventory_id,company,product_name,
                   warehouse_name,lot,exp_date,source_location,waiting_location,qty,moved_at,
                   confirmed
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,0)""",
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
                    item_target_location,
                    qty,
                    now,
                ),
            )
        if moved_to_p:
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
            to_location=item_target_location,
            qty=qty,
                memo=f"수출확정 수정 / 추가 품목 수출대기 / {title} / 수출번호: {export_no}",
            )

    remaining = cur.execute(
        "SELECT COUNT(*) FROM export_waiting_items WHERE order_id=? AND COALESCE(confirmed,0)=0",
        (int(order_id),),
    ).fetchone()[0]
    total = cur.execute(
        "SELECT COUNT(*) FROM export_waiting_items WHERE order_id=?",
        (int(order_id),),
    ).fetchone()[0]
    # A confirmed order whose last item(s) just got removed (e.g. deleting every
    # row in the intake editor) has zero items left, not zero *unconfirmed*
    # items — that must not read as "confirmed" or the next save on this order
    # trips the "수정할 수출확정 품목을 찾을 수 없습니다" guard above, since it
    # requires at least one confirmed item to edit against.
    if int(total or 0) == 0:
        status = "waiting"
    else:
        status = "partial" if int(remaining or 0) else "confirmed"
    cur.execute(
        "UPDATE export_waiting_orders SET status=?,updated_at=? WHERE id=?",
        (status, now, int(order_id)),
    )

def save_export_waiting_order(
    cart, *, country, buyer="", transport_method="미지정", export_no, editing_order_id=None,
    staging_location=P,
):
    country = str(country or "").strip()
    buyer = str(buyer or "").strip()
    transport_method = str(transport_method or "").strip() or "미지정"
    export_no = str(export_no or "").strip()
    staging_location = str(staging_location or "").strip() or P
    if not country:
        raise ValueError("국가를 입력하세요.")
    if transport_method not in TRANSPORT_METHODS:
        raise ValueError("운송방식을 항공, 해상, 핸드캐리, 미지정 중에서 선택하세요.")
    if not export_no:
        raise ValueError("수출번호를 입력하세요.")
    if staging_location not in STAGING_LOCATIONS:
        raise ValueError("수출대기 보관 위치를 P, T1~T5 중에서 선택하세요.")

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
            if not row or row["status"] not in {"waiting", "partial", "confirmed"}:
                raise ValueError("취소된 수출대기 건은 수정할 수 없습니다.")
            is_confirmed = row["status"] in {"partial", "confirmed"}
            items_changed = _current_item_signature(
                cur,
                editing_order_id,
                confirmed=is_confirmed,
            ) != dict(grouped) or not _waiting_inventory_matches_items(
                cur, editing_order_id
            )
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
                    target_location=staging_location,
                )
            else:
                _apply_export_waiting_item_changes(
                    cur, order_id, grouped, source_hints, now, title, export_no,
                    target_location=staging_location,
                )
            total = sum(grouped.values())
        else:
            cur.execute("""INSERT INTO export_waiting_orders(export_no,country,buyer,transport_method,title,status,created_at,updated_at,created_by)
                VALUES(?,?,?,?,?,'waiting',?,?,?)""", (export_no,country,buyer,transport_method,title,now,now,_actor()))
            order_id = int(cur.lastrowid)

            total = 0
            for inventory_id, qty in grouped.items():
                s = _take_source(cur, inventory_id, qty, now, source_hints.get(inventory_id))
                resolved_inventory_id = int(s.get("_resolved_inventory_id") or s.get("id") or inventory_id)
                waiting_inventory_id, moved_to_p = _place_source_in_staging(cur, s, qty, now, staging_location)
                cur.execute("""INSERT INTO export_waiting_items(order_id,source_inventory_id,waiting_inventory_id,company,product_name,
                    warehouse_name,lot,exp_date,source_location,waiting_location,qty,moved_at,confirmed)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,0)""",
                    (order_id,resolved_inventory_id,waiting_inventory_id,s.get("company", ""),s.get("product_name", ""),s.get("warehouse_name", "") or "",
                     s.get("lot", "-") or "-",s.get("exp_date", "-") or "-",s.get("location", ""),staging_location,qty,now))
                if moved_to_p:
                    insert_transaction_log(cur, created_at=now, tx_type="위치이동", product_name=s.get("product_name", ""),
                        warehouse_name=s.get("warehouse_name", "") or "", lot=s.get("lot", "-"), exp_date=s.get("exp_date", "-"),
                        from_company=s.get("company", ""), from_location=s.get("location", ""), to_company=s.get("company", ""),
                        to_location=staging_location, qty=qty, memo=f"수출대기 등록 / {title} / 수출번호: {export_no}")
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


def repair_broken_waiting_reservations(export_no: str) -> dict:
    """일반 '이동 등록' 등으로 수출대기 예약 재고(P/T1~T5)가 몰래 다른
    위치로 옮겨져 waiting_location에 실제 수량이 부족해진 품목을 복구한다.

    각 미확정 품목의 waiting_location에 실제로 요청수량만큼 재고가 있는지
    확인하고, 부족하면 그 제품이 지금 실제로 있는 다른 위치(같은 사업장/
    제품명/LOT/유통기한 조합)에서 다시 가져와 원래 waiting_location으로
    재배치한다. 어디에도 충분한 재고가 없으면 손대지 않고 실패 목록으로
    보고한다.
    """
    normalized = str(export_no or "").strip()
    if not normalized:
        return {"repaired": [], "failed": []}
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    repaired: list[str] = []
    failed: list[str] = []
    with connect() as con:
        cur = con.cursor()
        ensure_export_waiting_tables(cur)
        orders = cur.execute(
            """SELECT id FROM export_waiting_orders
               WHERE TRIM(export_no)=TRIM(?) AND status IN ('waiting','partial','confirmed')""",
            (normalized,),
        ).fetchall()
        for (order_id,) in orders:
            for item in _items(cur, int(order_id), confirmed=False):
                qty = int(item.get("qty") or 0)
                if qty <= 0:
                    continue
                staging_location = str(item.get("waiting_location") or "").strip() or P
                available = cur.execute(
                    """SELECT COALESCE(SUM(qty),0) FROM inventory
                       WHERE company=? AND product_name=? AND IFNULL(warehouse_name,'')=?
                         AND IFNULL(lot,'-')=? AND IFNULL(exp_date,'-')=? AND location=?""",
                    (item["company"], item["product_name"], item.get("warehouse_name", "") or "",
                     item.get("lot", "-") or "-", item.get("exp_date", "-") or "-", staging_location),
                ).fetchone()
                if int(available[0] or 0) >= qty:
                    continue  # 정상 예약: 손대지 않는다.
                try:
                    s = _take_source(cur, item.get("source_inventory_id"), qty, now, fallback=item)
                except ValueError:
                    failed.append(f"{item['product_name']} ({qty}EA)")
                    continue
                resolved_inventory_id = int(s.get("_resolved_inventory_id") or s.get("id") or 0)
                waiting_inventory_id, _ = _place_source_in_staging(cur, s, qty, now, staging_location)
                cur.execute(
                    """UPDATE export_waiting_items
                       SET source_inventory_id=?,waiting_inventory_id=?,source_location=?,moved_at=?
                       WHERE id=?""",
                    (resolved_inventory_id, waiting_inventory_id, s.get("location", ""), now, int(item["id"])),
                )
                insert_transaction_log(
                    cur, created_at=now, tx_type="위치이동", product_name=item["product_name"],
                    warehouse_name=item.get("warehouse_name", "") or "", lot=item.get("lot", "-"),
                    exp_date=item.get("exp_date", "-"), from_company=s.get("company", ""),
                    from_location=s.get("location", ""), to_company=item["company"], to_location=staging_location,
                    qty=qty, memo=f"수출대기 예약 복구 / 수출번호: {normalized}",
                )
                repaired.append(f"{item['product_name']} ({qty}EA)")
        con.commit()
    return {"repaired": repaired, "failed": failed}


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
                from_company=item["company"], from_location=str(item.get("waiting_location") or "").strip() or P,
                to_company=erp_company,
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


def return_confirmed_export_to_waiting(export_no: str) -> int:
    """Restore confirmed stock to P and make the export selectable again."""
    normalized = str(export_no or "").strip()
    if not normalized:
        return 0
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with connect() as con:
        cur = con.cursor()
        ensure_export_waiting_tables(cur)
        orders = cur.execute(
            """SELECT id,title,status FROM export_waiting_orders
               WHERE TRIM(export_no)=TRIM(?) AND status IN ('partial','confirmed')
               ORDER BY id""",
            (normalized,),
        ).fetchall()
        if not orders:
            return 0
        if len(orders) > 1:
            raise ValueError(
                f"수출번호 {normalized}에 연결된 수출확정 건이 여러 개라 재고를 자동 원복할 수 없습니다."
            )

        order_id, title, _ = orders[0]
        confirmed_items = _items(cur, int(order_id), confirmed=True)
        for item in confirmed_items:
            staging_location = str(item.get("waiting_location") or "").strip() or P
            restored_id = _add(cur, item, staging_location, int(item.get("qty") or 0), now, 0)
            cur.execute(
                """UPDATE export_waiting_items
                   SET waiting_inventory_id=?,waiting_location=?,confirmed=0,
                       confirmed_company=NULL,confirmed_customer_code=NULL,
                       confirmed_customer_name=NULL,confirmed_at=NULL
                   WHERE id=? AND COALESCE(confirmed,0)=1""",
                (restored_id, staging_location, int(item["id"])),
            )
            insert_transaction_log(
                cur,
                created_at=now,
                tx_type="출고취소",
                product_name=item["product_name"],
                warehouse_name=item.get("warehouse_name", ""),
                lot=item.get("lot", "-"),
                exp_date=item.get("exp_date", "-"),
                from_company=str(item.get("confirmed_company") or ""),
                from_location="",
                to_company=item["company"],
                to_location=staging_location,
                qty=int(item.get("qty") or 0),
                memo=f"패킹완료 단계로 되돌리기 / {title} / 수출번호: {normalized}",
            )

        if confirmed_items:
            cur.execute(
                """UPDATE export_waiting_orders
                   SET status='waiting',erp_company=NULL,erp_customer_code=NULL,
                       erp_customer_name=NULL,order_date=NULL,confirmed_at=NULL,updated_at=?
                   WHERE id=?""",
                (now, int(order_id)),
            )
        con.commit()
        return len(confirmed_items)


def update_confirmed_export_waiting_items(
    order_id,
    item_ids,
    *,
    erp_company,
    customer_code,
    customer_name,
    shipment_date,
):
    """이미 확정된 품목의 ERP 매출 정보와 출고일자를 다시 저장한다.

    재고 출고 자체는 다시 발생시키지 않는다. 품목 교체/수량 변경은 수출대기
    입고 수정에서 기존 확정 감소분을 원복하고 신규분을 P로 이동시킨 뒤, 이
    화면에서 신규분을 다시 확정하는 기존 흐름을 사용한다.
    """
    erp_company = str(erp_company or "").strip()
    customer_code = str(customer_code or "").strip()
    customer_name = str(customer_name or "").strip()
    order_date = _normalize_shipment_date(shipment_date)
    selected_ids = sorted({int(x) for x in (item_ids or [])})
    if not selected_ids:
        raise ValueError("수정할 확정 품목을 선택하세요.")
    if not erp_company or not customer_name:
        raise ValueError("ERP 사업장과 수출 매출처를 선택하세요.")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    confirmed_at = f"{order_date} {now[11:]}"
    with connect() as con:
        cur = con.cursor(); ensure_export_waiting_tables(cur)
        order = cur.execute(
            "SELECT title,status FROM export_waiting_orders WHERE id=?",
            (int(order_id),),
        ).fetchone()
        if not order or order[1] not in {"partial", "confirmed"}:
            raise ValueError("수정할 수출확정 건이 없습니다.")

        placeholders = ",".join("?" for _ in selected_ids)
        rows = cur.execute(
            f"""SELECT id FROM export_waiting_items
                WHERE order_id=? AND id IN ({placeholders})
                  AND COALESCE(confirmed,0)=1""",
            (int(order_id), *selected_ids),
        ).fetchall()
        if len(rows) != len(selected_ids):
            raise ValueError("선택 품목 중 확정되지 않았거나 찾을 수 없는 항목이 있습니다.")

        cur.execute(
            f"""UPDATE export_waiting_items
                SET confirmed_company=?,confirmed_customer_code=?,
                    confirmed_customer_name=?,confirmed_at=?
                WHERE order_id=? AND id IN ({placeholders})
                  AND COALESCE(confirmed,0)=1""",
            (erp_company, customer_code, customer_name, confirmed_at, int(order_id), *selected_ids),
        )
        cur.execute(
            """UPDATE export_waiting_orders
               SET erp_company=?,erp_customer_code=?,erp_customer_name=?,
                   order_date=?,confirmed_at=?,updated_at=?
               WHERE id=?""",
            (erp_company, customer_code, customer_name, order_date, confirmed_at, now, int(order_id)),
        )
        con.commit()

    return {
        "updated_count": len(selected_ids),
        "order_date": order_date,
        "confirmed_at": confirmed_at,
    }
