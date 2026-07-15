from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from nohtus.db import connect
from nohtus.services.inventory import insert_transaction_log


EXPORT_WAITING_LOCATION = "P"


def ensure_export_waiting_tables(cur=None):
    own_connection = cur is None
    con = connect() if own_connection else None
    cursor = con.cursor() if own_connection else cur
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS export_waiting_orders(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            export_no TEXT NOT NULL,
            country TEXT NOT NULL,
            title TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'waiting',
            erp_company TEXT,
            erp_customer_code TEXT,
            erp_customer_name TEXT,
            confirmed_at TEXT,
            cancelled_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            created_by TEXT
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS export_waiting_items(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            source_inventory_id INTEGER,
            company TEXT NOT NULL,
            product_name TEXT NOT NULL,
            warehouse_name TEXT,
            lot TEXT,
            exp_date TEXT,
            source_location TEXT NOT NULL,
            waiting_location TEXT NOT NULL DEFAULT 'P',
            qty INTEGER NOT NULL,
            FOREIGN KEY(order_id) REFERENCES export_waiting_orders(id)
        )
        """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_export_waiting_items_order ON export_waiting_items(order_id)")
    if own_connection:
        con.commit()
        con.close()


def _actor():
    try:
        from nohtus.auth import current_display_name, current_username
        return str(current_display_name() or current_username() or "").strip()
    except Exception:
        return ""


def _inventory_columns(cur):
    return {row[1] for row in cur.execute("PRAGMA table_info(inventory)").fetchall()}


def _destination_row(cur, source, location):
    return cur.execute(
        """
        SELECT id, qty FROM inventory
        WHERE company=? AND product_name=? AND IFNULL(warehouse_name,'')=?
          AND IFNULL(lot,'-')=? AND IFNULL(exp_date,'-')=? AND location=?
        """,
        (
            source.get("company", ""), source.get("product_name", ""),
            source.get("warehouse_name", "") or "", source.get("lot", "-") or "-",
            source.get("exp_date", "-") or "-", location,
        ),
    ).fetchone()


def _add_inventory(cur, source, location, qty, now, *, shippable):
    cols = _inventory_columns(cur)
    row = _destination_row(cur, source, location)
    if row:
        if "is_shippable" in cols:
            cur.execute(
                "UPDATE inventory SET qty=?, updated_at=?, is_shippable=? WHERE id=?",
                (int(row[1] or 0) + int(qty), now, int(shippable), int(row[0])),
            )
        else:
            cur.execute("UPDATE inventory SET qty=?, updated_at=? WHERE id=?", (int(row[1] or 0) + int(qty), now, int(row[0])))
        return int(row[0])
    fields = ["company", "product_name", "warehouse_name", "lot", "exp_date", "location", "qty", "updated_at"]
    values = [source.get("company", ""), source.get("product_name", ""), source.get("warehouse_name", "") or "",
              source.get("lot", "-") or "-", source.get("exp_date", "-") or "-", location, int(qty), now]
    if "is_shippable" in cols:
        fields.append("is_shippable")
        values.append(int(shippable))
    marks = ",".join("?" for _ in fields)
    cur.execute(f"INSERT INTO inventory({','.join(fields)}) VALUES({marks})", values)
    return int(cur.lastrowid)


def _take_inventory(cur, inventory_id, qty, now):
    raw = cur.execute("SELECT * FROM inventory WHERE id=?", (int(inventory_id),)).fetchone()
    if not raw:
        raise ValueError(f"재고 #{inventory_id}를 찾을 수 없습니다. 화면을 새로고침하세요.")
    columns = [d[0] for d in cur.description]
    source = dict(zip(columns, raw))
    available = int(source.get("qty") or 0)
    if int(qty) <= 0 or int(qty) > available:
        raise ValueError(f"{source.get('product_name','제품')} 재고 부족: 요청 {qty}EA / 현재 {available}EA")
    if str(source.get("location") or "").strip() == EXPORT_WAITING_LOCATION:
        raise ValueError(f"{source.get('product_name','제품')}은 이미 수출대기 위치 P에 있습니다.")
    cur.execute("UPDATE inventory SET qty=?, updated_at=? WHERE id=?", (available - int(qty), now, int(inventory_id)))
    return source


def _remove_waiting_qty(cur, item, now):
    row = cur.execute(
        """
        SELECT id, qty FROM inventory
        WHERE company=? AND product_name=? AND IFNULL(warehouse_name,'')=?
          AND IFNULL(lot,'-')=? AND IFNULL(exp_date,'-')=? AND location='P'
        """,
        (item["company"], item["product_name"], item.get("warehouse_name", "") or "",
         item.get("lot", "-") or "-", item.get("exp_date", "-") or "-"),
    ).fetchone()
    qty = int(item["qty"] or 0)
    if not row or int(row[1] or 0) < qty:
        raise ValueError(f"P 로케이션의 {item['product_name']} 재고가 부족하여 처리할 수 없습니다.")
    cur.execute("UPDATE inventory SET qty=?, updated_at=? WHERE id=?", (int(row[1] or 0) - qty, now, int(row[0])))


def _group_cart(cart):
    grouped = defaultdict(int)
    for item in cart or []:
        inventory_id = int(item.get("id"))
        qty = int(item.get("요청수량") or 0)
        if qty > 0:
            grouped[inventory_id] += qty
    if not grouped:
        raise ValueError("수출대기 등록할 품목이 없습니다.")
    return grouped


def _restore_items(cur, order_id, now, memo):
    cur.row_factory = None
    rows = cur.execute(
        """SELECT source_inventory_id, company, product_name, warehouse_name, lot, exp_date,
                  source_location, waiting_location, qty
           FROM export_waiting_items WHERE order_id=? ORDER BY id""",
        (int(order_id),),
    ).fetchall()
    keys = ["source_inventory_id", "company", "product_name", "warehouse_name", "lot", "exp_date", "source_location", "waiting_location", "qty"]
    for raw in rows:
        item = dict(zip(keys, raw))
        _remove_waiting_qty(cur, item, now)
        source = dict(item)
        restored_id = _add_inventory(cur, source, item["source_location"], int(item["qty"]), now, shippable=1)
        insert_transaction_log(
            cur, created_at=now, tx_type="위치이동", product_name=item["product_name"],
            warehouse_name=item.get("warehouse_name", ""), lot=item.get("lot", "-"), exp_date=item.get("exp_date", "-"),
            from_company=item["company"], from_location=EXPORT_WAITING_LOCATION,
            to_company=item["company"], to_location=item["source_location"], qty=item["qty"], memo=memo,
        )
        if item.get("source_inventory_id") is None:
            cur.execute("UPDATE export_waiting_items SET source_inventory_id=? WHERE order_id=? AND product_name=? AND source_location=?",
                        (restored_id, int(order_id), item["product_name"], item["source_location"]))


def save_export_waiting_order(cart, *, country, export_no, editing_order_id=None):
    country = str(country or "").strip()
    export_no = str(export_no or "").strip()
    if not country:
        raise ValueError("국가를 입력하세요.")
    if not export_no:
        raise ValueError("수출번호를 입력하세요.")
    grouped = _group_cart(cart)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    title = f"{country}_{export_no}"
    with connect() as con:
        cur = con.cursor()
        ensure_export_waiting_tables(cur)
        if editing_order_id:
            status = cur.execute("SELECT status FROM export_waiting_orders WHERE id=?", (int(editing_order_id),)).fetchone()
            if not status or status[0] != "waiting":
                raise ValueError("수정할 수출대기 건을 찾을 수 없거나 이미 확정·취소되었습니다.")
            _restore_items(cur, int(editing_order_id), now, f"수출대기 수정 원복 / {title}")
            cur.execute("DELETE FROM export_waiting_items WHERE order_id=?", (int(editing_order_id),))
            cur.execute("UPDATE export_waiting_orders SET export_no=?, country=?, title=?, updated_at=? WHERE id=?",
                        (export_no, country, title, now, int(editing_order_id)))
            order_id = int(editing_order_id)
        else:
            cur.execute(
                "INSERT INTO export_waiting_orders(export_no,country,title,status,created_at,updated_at,created_by) VALUES(?,?,?,'waiting',?,?,?)",
                (export_no, country, title, now, now, _actor()),
            )
            order_id = int(cur.lastrowid)

        total_qty = 0
        for inventory_id, qty in grouped.items():
            source = _take_inventory(cur, inventory_id, qty, now)
            _add_inventory(cur, source, EXPORT_WAITING_LOCATION, qty, now, shippable=0)
            cur.execute(
                """INSERT INTO export_waiting_items(
                       order_id,source_inventory_id,company,product_name,warehouse_name,lot,exp_date,source_location,waiting_location,qty
                   ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (order_id, inventory_id, source.get("company", ""), source.get("product_name", ""),
                 source.get("warehouse_name", "") or "", source.get("lot", "-") or "-", source.get("exp_date", "-") or "-",
                 source.get("location", ""), EXPORT_WAITING_LOCATION, qty),
            )
            insert_transaction_log(
                cur, created_at=now, tx_type="위치이동", product_name=source.get("product_name", ""),
                warehouse_name=source.get("warehouse_name", "") or "", lot=source.get("lot", "-") or "-",
                exp_date=source.get("exp_date", "-") or "-", from_company=source.get("company", ""),
                from_location=source.get("location", ""), to_company=source.get("company", ""),
                to_location=EXPORT_WAITING_LOCATION, qty=qty, memo=f"수출대기 등록 / {title}",
            )
            total_qty += qty
        con.commit()
    return {"order_id": order_id, "row_count": len(grouped), "total_qty": total_qty, "title": title}


def cancel_export_waiting_order(order_id):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with connect() as con:
        cur = con.cursor()
        ensure_export_waiting_tables(cur)
        row = cur.execute("SELECT title,status FROM export_waiting_orders WHERE id=?", (int(order_id),)).fetchone()
        if not row or row[1] != "waiting":
            raise ValueError("취소할 수출대기 건을 찾을 수 없거나 이미 처리되었습니다.")
        _restore_items(cur, int(order_id), now, f"수출대기 취소 / {row[0]}")
        cur.execute("UPDATE export_waiting_orders SET status='cancelled', cancelled_at=?, updated_at=? WHERE id=?", (now, now, int(order_id)))
        con.commit()


def confirm_export_waiting_order(order_id, *, erp_company, customer_code, customer_name):
    erp_company = str(erp_company or "").strip()
    customer_name = str(customer_name or "").strip()
    if not erp_company or not customer_name:
        raise ValueError("ERP 사업장과 수출 매출처를 선택하세요.")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with connect() as con:
        cur = con.cursor()
        ensure_export_waiting_tables(cur)
        order = cur.execute("SELECT title,status FROM export_waiting_orders WHERE id=?", (int(order_id),)).fetchone()
        if not order or order[1] != "waiting":
            raise ValueError("확정할 수출대기 건을 찾을 수 없거나 이미 처리되었습니다.")
        rows = cur.execute(
            "SELECT company,product_name,warehouse_name,lot,exp_date,source_location,waiting_location,qty FROM export_waiting_items WHERE order_id=?",
            (int(order_id),),
        ).fetchall()
        keys = ["company","product_name","warehouse_name","lot","exp_date","source_location","waiting_location","qty"]
        for raw in rows:
            item = dict(zip(keys, raw))
            _remove_waiting_qty(cur, item, now)
            insert_transaction_log(
                cur, created_at=now, tx_type="수출확정", product_name=item["product_name"], warehouse_name=item.get("warehouse_name", ""),
                lot=item.get("lot", "-"), exp_date=item.get("exp_date", "-"), from_company=item["company"],
                from_location=EXPORT_WAITING_LOCATION, to_company=None, to_location=None, qty=item["qty"],
                memo=f"수출확정 / {order[0]} / ERP매출처: {customer_name}",
            )
        cur.execute(
            """UPDATE export_waiting_orders SET status='confirmed',erp_company=?,erp_customer_code=?,erp_customer_name=?,
                      confirmed_at=?,updated_at=? WHERE id=?""",
            (erp_company, str(customer_code or "").strip(), customer_name, now, now, int(order_id)),
        )
        con.commit()


# 이전 호출부 호환용
def move_cart_to_export_waiting(cart, *, title="", customer_name=""):
    title = str(title or "").strip()
    country, export_no = (title.split("_", 1) + [""])[:2] if "_" in title else ("수출", title or "미지정")
    return save_export_waiting_order(cart, country=country, export_no=export_no)
