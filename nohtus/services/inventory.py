"""Inventory service functions for NOHTUS WMS.

This module is migrated gradually from app.py. Keep functions independent from
Streamlit whenever possible.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime

from nohtus.db import connect, q


OUTBOUND_DEDUCT_TYPES = ["출고지시", "출고", "출고지시수정", "출고확정", "출고지시 재차감"]


def first_nonblank(*values):
    for v in values:
        if v is None:
            continue
        text = str(v).strip()
        if text and text.lower() != "nan" and text != "-":
            return text
    return ""


def product_mapping_name_for(company, standard_name):
    if not standard_name:
        return ""
    col = {
        "노투스팜": "erp_nohtuspharm_name",
        "NOH": "erp_noh_name",
        "노투스": "erp_nohtus_name",
        "비자료": "bidata_name",
    }.get(company)
    if not col:
        return ""
    df = q(f"SELECT {col} AS nm FROM products WHERE standard_name=?", (standard_name,))
    if df.empty:
        return ""
    return first_nonblank(df.iloc[0].get("nm"))


def _stock_key(company, product_name, lot, exp_date):
    return (
        str(company or "").strip(),
        str(product_name or "").strip(),
        str(lot or "-").strip() or "-",
        str(exp_date or "-").strip() or "-",
    )


def _current_actor():
    try:
        from nohtus.auth import current_display_name, current_username

        display_name = str(current_display_name() or "").strip()
        username = str(current_username() or "").strip()
        return display_name or username or ""
    except Exception:
        return ""


def _infer_transaction_stock_company(tx_type, from_company, to_company):
    tx_type = str(tx_type or "").strip()
    if tx_type in ["입고", "출고지시취소", "재고조사불러오기", "기준재고", "전산재고", "재고조정", "재고실사", "재고정보수정"]:
        return to_company or from_company
    if tx_type in OUTBOUND_DEDUCT_TYPES:
        return from_company or to_company
    return to_company or from_company


def stock_key_final_qty(cur, *, company, product_name, lot, exp_date):
    """사업장+표준제품명+LOT+유통기한 조합의 현재 최종재고 합계."""
    company, product, lot, exp_date = _stock_key(company, product_name, lot, exp_date)
    if not company or not product:
        return None
    row = cur.execute(
        """
        SELECT COALESCE(SUM(qty), 0)
        FROM inventory
        WHERE company=?
          AND product_name=?
          AND IFNULL(lot, '-')=?
          AND IFNULL(exp_date, '-')=?
        """,
        (company, product, lot, exp_date),
    ).fetchone()
    return int((row[0] if row else 0) or 0)


def current_product_lot_exp_stock(cur, product_name, lot, exp_date, company=None):
    """호환용 wrapper. company가 있으면 사업장 포함 기준으로 계산한다."""
    if company:
        return stock_key_final_qty(cur, company=company, product_name=product_name, lot=lot, exp_date=exp_date)
    product = str(product_name or "").strip()
    lot = str(lot or "-").strip() or "-"
    exp_date = str(exp_date or "-").strip() or "-"
    if not product:
        return None
    row = cur.execute(
        """
        SELECT COALESCE(SUM(qty), 0)
        FROM inventory
        WHERE product_name=?
          AND IFNULL(lot, '-')=?
          AND IFNULL(exp_date, '-')=?
        """,
        (product, lot, exp_date),
    ).fetchone()
    return int((row[0] if row else 0) or 0)


def _transaction_stock_delta(tx_type, qty, from_company=None, to_company=None):
    """사업장+표준제품명+LOT+유통기한 기준의 이력 증감값."""
    tx_type = str(tx_type or "").strip()
    qty = int(qty or 0)
    if tx_type in ["입고", "출고지시취소", "재고조사불러오기", "기준재고", "전산재고"]:
        return qty
    if tx_type in OUTBOUND_DEDUCT_TYPES:
        return -qty
    if tx_type in ["재고조정", "재고실사", "재고정보수정"]:
        return qty
    if tx_type in ["사업장이동", "사업장+위치이동", "비자료전환", "이동"]:
        return qty if str(from_company or "") != str(to_company or "") else 0
    if tx_type == "위치이동":
        return 0
    return 0


def backfill_missing_transaction_final_stock():
    """비어 있는 과거 final_stock을 현재 재고에서 이력을 역순으로 되감아 보정한다."""
    with connect() as con:
        cur = con.cursor()
        missing = cur.execute("SELECT COUNT(*) FROM transactions WHERE final_stock IS NULL").fetchone()[0]
        if int(missing or 0) <= 0:
            return 0

        stock_rows = cur.execute(
            """
            SELECT company, product_name, IFNULL(lot, '-') AS lot, IFNULL(exp_date, '-') AS exp_date,
                   COALESCE(SUM(qty), 0) AS qty
            FROM inventory
            GROUP BY company, product_name, IFNULL(lot, '-'), IFNULL(exp_date, '-')
            """
        ).fetchall()
        running = {_stock_key(r[0], r[1], r[2], r[3]): int(r[4] or 0) for r in stock_rows}

        rows = cur.execute(
            """
            SELECT id, tx_type, product_name, lot, exp_date, from_company, to_company, qty, final_stock
            FROM transactions
            WHERE TRIM(COALESCE(product_name, '')) <> ''
            ORDER BY id DESC
            """
        ).fetchall()
        updated = 0
        for tx_id, tx_type, product_name, lot, exp_date, from_company, to_company, qty, final_stock in rows:
            company = _infer_transaction_stock_company(tx_type, from_company, to_company)
            key = _stock_key(company, product_name, lot, exp_date)
            current_after = int(running.get(key, 0) or 0)
            if final_stock is None:
                cur.execute("UPDATE transactions SET final_stock=? WHERE id=?", (current_after, int(tx_id)))
                updated += 1
            running[key] = current_after - _transaction_stock_delta(tx_type, qty, from_company, to_company)
        con.commit()
        return updated


def insert_transaction_log(cur, *, created_at, tx_type, product_name, warehouse_name=None,
                           lot=None, exp_date=None, from_company=None, from_location=None,
                           to_company=None, to_location=None, qty=0, memo="", final_stock=None, actor=None):
    if final_stock is None:
        company = _infer_transaction_stock_company(tx_type, from_company, to_company)
        final_stock = stock_key_final_qty(
            cur,
            company=company,
            product_name=product_name,
            lot=lot,
            exp_date=exp_date,
        )
    actor = str(actor if actor is not None else _current_actor()).strip()
    cur.execute(
        """INSERT INTO transactions(
               created_at, actor, tx_type, product_name, warehouse_name, lot, exp_date,
               from_company, from_location, to_company, to_location, qty, memo, final_stock
           ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (created_at, actor, tx_type, product_name, warehouse_name, lot, exp_date,
         from_company, from_location, to_company, to_location, int(qty or 0), memo, final_stock),
    )


def add_inventory(company, product, warehouse, lot, exp, location, qty, memo="입고 등록"):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with connect() as con:
        cur = con.cursor()
        row = cur.execute("""SELECT id, qty FROM inventory WHERE company=? AND product_name=? AND IFNULL(warehouse_name,'')=? AND lot=? AND exp_date=? AND location=?""",
                          (company, product, warehouse or "", lot, exp, location)).fetchone()
        if row:
            cur.execute("UPDATE inventory SET qty=?, updated_at=? WHERE id=?", (int(row[1] or 0) + int(qty), now, row[0]))
        else:
            cur.execute("""INSERT INTO inventory(company,product_name,warehouse_name,lot,exp_date,location,qty,updated_at)
                           VALUES(?,?,?,?,?,?,?,?)""", (company, product, warehouse, lot, exp, location, int(qty), now))
        insert_transaction_log(cur, created_at=now, tx_type="입고", product_name=product, warehouse_name=warehouse,
                               lot=lot, exp_date=exp, from_company=None, from_location=None,
                               to_company=company, to_location=location, qty=qty, memo=memo)
        con.commit()


def adjust_inventory(inventory_id, actual_qty, reason, memo=""):
    """재고 실사 화면에서 한 재고행의 실제 수량으로 조정한다.

    반환값은 (조정 전 수량, 조정 후 수량, 증감량)이다.
    """
    inventory_id = int(inventory_id)
    actual_qty = int(actual_qty)
    if actual_qty < 0:
        raise ValueError("실물수량은 0 이상이어야 합니다.")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with connect() as con:
        cur = con.cursor()
        raw = cur.execute("SELECT * FROM inventory WHERE id=?", (inventory_id,)).fetchone()
        if not raw:
            raise ValueError("조정할 재고를 찾을 수 없습니다.")
        cols = [d[0] for d in cur.description]
        src = dict(zip(cols, raw))

        before_qty = int(src.get("qty", 0) or 0)
        diff = actual_qty - before_qty
        if diff == 0:
            return before_qty, actual_qty, 0

        cur.execute(
            "UPDATE inventory SET qty=?, updated_at=? WHERE id=?",
            (actual_qty, now, inventory_id),
        )
        reason_text = str(reason or "재고조정").strip() or "재고조정"
        memo_text = f"{reason_text}"
        if str(memo or "").strip():
            memo_text += f" / {str(memo).strip()}"

        insert_transaction_log(
            cur,
            created_at=now,
            tx_type="재고조정",
            product_name=src.get("product_name", ""),
            warehouse_name=src.get("warehouse_name", ""),
            lot=src.get("lot", "-"),
            exp_date=src.get("exp_date", "-"),
            from_company=src.get("company", ""),
            from_location=src.get("location", ""),
            to_company=src.get("company", ""),
            to_location=src.get("location", ""),
            qty=diff,
            memo=memo_text,
            final_stock=stock_key_final_qty(
                cur,
                company=src.get("company", ""),
                product_name=src.get("product_name", ""),
                lot=src.get("lot", "-"),
                exp_date=src.get("exp_date", "-"),
            ),
        )
        con.commit()
        return before_qty, actual_qty, diff


def move_inventory(src_id, to_company, to_location, qty, memo=""):
    """재고 이동. 사업장 이동 시 전산상명칭은 도착 사업장 기준으로 다시 계산한다."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with connect() as con:
        cur = con.cursor()
        src = cur.execute("SELECT * FROM inventory WHERE id=?", (src_id,)).fetchone()
        cols = [d[0] for d in cur.description]
        src = dict(zip(cols, src)) if src else None
        if not src:
            raise ValueError("출발 재고를 찾을 수 없습니다.")
        qty = int(qty)
        if qty <= 0 or qty > int(src["qty"] or 0):
            raise ValueError("이동 수량이 현재 재고보다 많거나 올바르지 않습니다.")

        product_name = src["product_name"]
        old_warehouse = src.get("warehouse_name") or ""
        dest_warehouse = product_mapping_name_for(to_company, product_name) or product_name

        cur.execute("UPDATE inventory SET qty=?, updated_at=? WHERE id=?", (int(src["qty"] or 0)-qty, now, src_id))
        row = cur.execute("""SELECT id, qty FROM inventory WHERE company=? AND product_name=? AND IFNULL(warehouse_name,'')=? AND lot=? AND exp_date=? AND location=?""",
                          (to_company, product_name, dest_warehouse or "", src["lot"], src["exp_date"], to_location)).fetchone()
        if row:
            cur.execute("UPDATE inventory SET qty=?, updated_at=? WHERE id=?", (int(row[1] or 0)+qty, now, row[0]))
        else:
            cur.execute("""INSERT INTO inventory(company,product_name,warehouse_name,lot,exp_date,location,qty,updated_at)
                           VALUES(?,?,?,?,?,?,?,?)""", (to_company, product_name, dest_warehouse, src["lot"], src["exp_date"], to_location, qty, now))

        from_company = src["company"]
        tx_type = "위치이동" if from_company == to_company else "사업장+위치이동"
        insert_transaction_log(cur, created_at=now, tx_type=tx_type, product_name=product_name,
                               warehouse_name=old_warehouse, lot=src["lot"], exp_date=src["exp_date"],
                               from_company=from_company, from_location=src["location"],
                               to_company=to_company, to_location=to_location, qty=qty, memo=memo)
        con.commit()
