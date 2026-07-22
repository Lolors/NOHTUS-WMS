from __future__ import annotations

import re
from datetime import datetime

import pandas as pd
import streamlit as st

from nohtus.db import connect
import nohtus.pages.history as history_page
from nohtus.pages.history import page_history as _page_history
from nohtus.services.inventory import backfill_missing_transaction_final_stock


def _normalize_created_at(value):
    text = str(value or "").strip()
    if not text:
        raise ValueError("일시는 비워둘 수 없습니다.")
    parsed = pd.to_datetime(text, errors="coerce")
    if pd.isna(parsed):
        raise ValueError(f"일시 형식을 확인하세요: {text}")
    return parsed.strftime("%Y-%m-%d %H:%M:%S")


def _display_row_to_tx_id(cur, row, used_ids):
    created_at = str(row.get("일시") or "").strip()
    tx_type = str(row.get("이력유형") or "").strip()
    product_name = str(row.get("제품명") or "").strip()
    lot = str(row.get("LOT") or "").strip()
    exp_date = str(row.get("유통기한") or "").strip()
    memo = str(row.get("메모") or "").strip()
    if not created_at or not tx_type or not product_name:
        return None
    rows = cur.execute(
        """
        SELECT id
        FROM transactions
        WHERE created_at=?
          AND tx_type=?
          AND product_name=?
          AND IFNULL(lot, '')=?
          AND IFNULL(exp_date, '')=?
          AND IFNULL(memo, '')=?
        ORDER BY id DESC
        """,
        (created_at, tx_type, product_name, lot, exp_date, memo),
    ).fetchall()
    for raw in rows:
        tx_id = int(raw[0])
        if tx_id not in used_ids:
            used_ids.add(tx_id)
            return tx_id
    return None


def _update_history_dates(original_df, edited_df):
    if not isinstance(original_df, pd.DataFrame) or not isinstance(edited_df, pd.DataFrame):
        return 0
    if "일시" not in original_df.columns or "일시" not in edited_df.columns:
        return 0

    changed_indexes = []
    for idx in range(min(len(original_df), len(edited_df))):
        before = str(original_df.iloc[idx].get("일시") or "").strip()
        after = str(edited_df.iloc[idx].get("일시") or "").strip()
        if before != after:
            changed_indexes.append(idx)
    if not changed_indexes:
        return 0

    with connect() as con:
        cur = con.cursor()
        used_ids = set()
        row_to_id = {}
        for idx in range(len(original_df)):
            tx_id = _display_row_to_tx_id(cur, original_df.iloc[idx], used_ids)
            if tx_id is not None:
                row_to_id[idx] = tx_id

        updated = 0
        now_ids = []
        for idx in changed_indexes:
            tx_id = row_to_id.get(idx)
            if tx_id is None:
                continue
            new_created_at = _normalize_created_at(edited_df.iloc[idx].get("일시"))
            cur.execute("UPDATE transactions SET created_at=? WHERE id=?", (new_created_at, tx_id))
            updated += 1
            now_ids.append(tx_id)
        con.commit()
    if changed_indexes and updated == 0:
        raise ValueError("수정할 이력 행을 찾지 못했습니다. 같은 내용의 중복 이력이 있으면 조건을 좁혀 다시 시도하세요.")
    return updated


def _deleted_outbound_orders_for_transactions(tx_ids):
    ids = [int(x) for x in tx_ids if x]
    if not ids:
        return []
    placeholders = ",".join("?" for _ in ids)
    with connect() as con:
        cur = con.cursor()
        rows = cur.execute(
            f"""
            SELECT tx_type, memo, from_company
            FROM transactions
            WHERE id IN ({placeholders})
            """,
            tuple(ids),
        ).fetchall()
        order_companies = {}
        for tx_type, memo, from_company in rows:
            if str(tx_type or "") not in {"출고지시", "출고", "출고지시수정"}:
                continue
            match = re.search(r"출고지시서\s*#(\d+)", str(memo or ""))
            if match:
                order_id = int(match.group(1))
                company = str(from_company or "").strip()
                if company:
                    order_companies.setdefault(order_id, company)
        if not order_companies:
            return []
        order_ids = sorted(order_companies)
        order_placeholders = ",".join("?" for _ in order_ids)
        columns = {row[1] for row in cur.execute("PRAGMA table_info(outbound_orders)").fetchall()}
        customer_expr = "COALESCE(customer_name, '')" if "customer_name" in columns else "''"
        company_expr = "COALESCE(customer_company, '')" if "customer_company" in columns else "''"
        orders = cur.execute(
            f"""
            SELECT id, order_date, COALESCE(title, ''), {customer_expr}, {company_expr}
            FROM outbound_orders
            WHERE id IN ({order_placeholders})
            """,
            tuple(order_ids),
        ).fetchall()
    result = []
    for order_id, order_date, title, customer_name, customer_company in orders:
        customer = str(customer_name or "").strip()
        if not customer:
            customer = str(title or "").split(" - ", 1)[0].strip()
        company = str(customer_company or "").strip() or order_companies.get(int(order_id), "")
        result.append({
            "order_id": int(order_id),
            "order_date": str(order_date or "").strip(),
            "customer_name": customer,
            "company": company,
        })
    return result


def _sync_customer_last_sales_after_delete(deleted_orders):
    if not deleted_orders:
        return
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with connect() as con:
        cur = con.cursor()
        tables = {row[0] for row in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        if "customer_last_sales" not in tables:
            return
        order_columns = {row[1] for row in cur.execute("PRAGMA table_info(outbound_orders)").fetchall()}
        if "customer_name" not in order_columns:
            return
        company_expr = "COALESCE(customer_company, '')" if "customer_company" in order_columns else "''"
        for deleted in deleted_orders:
            customer = str(deleted.get("customer_name") or "").strip()
            company = str(deleted.get("company") or "").strip()
            deleted_date = str(deleted.get("order_date") or "").strip()
            if not customer or not deleted_date:
                continue
            current = cur.execute(
                """
                SELECT id, last_sale_date
                FROM customer_last_sales
                WHERE customer_name=? AND company=?
                """,
                (customer, company),
            ).fetchone()
            if not current or str(current[1] or "").strip() != deleted_date:
                continue
            latest = cur.execute(
                f"""
                SELECT MAX(order_date)
                FROM outbound_orders
                WHERE TRIM(COALESCE(customer_name, ''))=?
                  AND {company_expr}=?
                  AND IFNULL(status, '') NOT IN ('삭제됨', '취소됨')
                """,
                (customer, company),
            ).fetchone()[0]
            latest_date = str(latest or "").strip()
            if latest_date:
                cur.execute(
                    "UPDATE customer_last_sales SET last_sale_date=?, updated_at=? WHERE id=?",
                    (latest_date, now, int(current[0])),
                )
            else:
                cur.execute("DELETE FROM customer_last_sales WHERE id=?", (int(current[0]),))
        con.commit()


def _restore_history_spinner_style():
    st.markdown(
        """
        <style>
        div[data-testid="stNumberInput"]{
            width:138px!important;
            margin:10px auto 0 auto!important;
            overflow:visible!important;
        }
        div[data-testid="stNumberInput"] input{
            height:68px!important;
            min-height:68px!important;
            text-align:center!important;
            font-size:16px!important;
        }
        div[data-testid="stNumberInput"] button{
            display:flex!important;
            visibility:visible!important;
            opacity:1!important;
            width:32px!important;
            min-width:32px!important;
            height:34px!important;
            min-height:34px!important;
            padding:0!important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def page_history():
    original_data_editor = st.data_editor
    original_delete_transactions = history_page._delete_transaction_ids

    def patched_delete_transactions(tx_ids):
        deleted_orders = _deleted_outbound_orders_for_transactions(tx_ids)
        deleted_count = original_delete_transactions(tx_ids)
        _sync_customer_last_sales_after_delete(deleted_orders)
        return deleted_count

    def patched_data_editor(data, *args, **kwargs):
        if kwargs.get("key") == "history_admin_delete_editor" and isinstance(data, pd.DataFrame):
            disabled = kwargs.get("disabled")
            if isinstance(disabled, list):
                kwargs["disabled"] = [c for c in disabled if c != "일시"]
            edited = original_data_editor(data, *args, **kwargs)
            try:
                updated = _update_history_dates(data, edited)
                if updated:
                    st.success(f"이력 일시 {updated}건을 수정했습니다.")
                    st.rerun()
            except Exception as e:
                st.error(str(e))
            return edited
        return original_data_editor(data, *args, **kwargs)

    st.data_editor = patched_data_editor
    history_page._delete_transaction_ids = patched_delete_transactions
    try:
        try:
            updated = backfill_missing_transaction_final_stock()
            if updated:
                st.caption(f"최종재고 누락 이력 {updated:,}건을 보정했습니다.")
        except Exception as e:
            st.warning(f"최종재고 보정 중 오류가 발생했습니다: {e}")
        result = _page_history()
        _restore_history_spinner_style()
        return result
    finally:
        st.data_editor = original_data_editor
        history_page._delete_transaction_ids = original_delete_transactions
