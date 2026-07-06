"""Inventory service functions for NOHTUS WMS.

This module is migrated gradually from app.py. Keep functions independent from
Streamlit whenever possible.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime

from nohtus.db import connect, q


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


def _current_actor_name():
    try:
        import streamlit as st
        user = st.session_state.get("current_user") or {}
        return str(user.get("display_name") or user.get("username") or "").strip()
    except Exception:
        return ""


def _transaction_has_actor_column(cur):
    try:
        cols = {r[1] for r in cur.execute("PRAGMA table_info(transactions)").fetchall()}
        return "actor" in cols
    except Exception:
        return False


def insert_transaction_log(cur, *, created_at, tx_type, product_name, warehouse_name=None,
                           lot=None, exp_date=None, from_company=None, from_location=None,
                           to_company=None, to_location=None, qty=0, memo="", final_stock=None):
    actor = _current_actor_name()
    if _transaction_has_actor_column(cur):
        cur.execute(
            """INSERT INTO transactions(
                   created_at, tx_type, product_name, warehouse_name, lot, exp_date,
                   from_company, from_location, to_company, to_location, qty, memo, final_stock, actor
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (created_at, tx_type, product_name, warehouse_name, lot, exp_date,
             from_company, from_location, to_company, to_location, int(qty or 0), memo, final_stock, actor),
        )
    else:
        cur.execute(
            """INSERT INTO transactions(
                   created_at, tx_type, product_name, warehouse_name, lot, exp_date,
                   from_company, from_location, to_company, to_location, qty, memo, final_stock
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (created_at, tx_type, product_name, warehouse_name, lot, exp_date,
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
        tx_type = "사업장+위치이동"
        if src["company"] == to_company and src["location"] != to_location: tx_type = "위치이동"
        elif src["company"] != to_company and src["location"] == to_location: tx_type = "사업장이동"
        if to_company == "비자료": tx_type = "비자료전환"

        move_memo = str(memo or "").strip()
        if str(old_warehouse or "").strip() != str(dest_warehouse or "").strip():
            erp_note = f"전산상명칭 변경: {old_warehouse or '-'} → {dest_warehouse or '-'}"
            move_memo = f"{move_memo} / {erp_note}" if move_memo else erp_note
        if src["company"] != to_company:
            dest_company_qty_row = cur.execute(
                "SELECT COALESCE(SUM(qty), 0) FROM inventory WHERE company=? AND product_name=?",
                (to_company, product_name),
            ).fetchone()
            dest_company_qty = int((dest_company_qty_row[0] if dest_company_qty_row else 0) or 0)
            stock_note = f"이동 후 {to_company} 해당 제품 재고: {dest_company_qty}EA"
            move_memo = f"{move_memo} / {stock_note}" if move_memo else stock_note

        insert_transaction_log(cur, created_at=now, tx_type=tx_type, product_name=product_name, warehouse_name=dest_warehouse,
                               lot=src["lot"], exp_date=src["exp_date"], from_company=src["company"], from_location=src["location"],
                               to_company=to_company, to_location=to_location, qty=qty, memo=move_memo)
        con.commit()


def adjust_inventory(inv_id, actual_qty, reason, memo=""):
    """실사 결과 기준으로 해당 재고 행의 수량을 실제 수량으로 조정한다."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with connect() as con:
        import sqlite3 as _sqlite3
        con.row_factory = _sqlite3.Row
        cur = con.cursor()
        src = cur.execute("SELECT * FROM inventory WHERE id=?", (inv_id,)).fetchone()
        if not src:
            raise ValueError("조정할 재고를 찾을 수 없습니다.")
        actual_qty = int(actual_qty)
        if actual_qty < 0:
            raise ValueError("실물수량은 0 이상이어야 합니다.")
        before = int(src["qty"])
        diff = actual_qty - before
        cur.execute("UPDATE inventory SET qty=?, updated_at=? WHERE id=?", (actual_qty, now, inv_id))
        reason_memo = reason if not memo else f"{reason} / {memo}"
        insert_transaction_log(cur, created_at=now, tx_type="재고조정", product_name=src["product_name"], warehouse_name=src["warehouse_name"],
                               lot=src["lot"], exp_date=src["exp_date"], from_company=src["company"], from_location=src["location"],
                               to_company=src["company"], to_location=src["location"], qty=diff, memo=reason_memo, final_stock=actual_qty)
        con.commit()
        return before, actual_qty, diff
