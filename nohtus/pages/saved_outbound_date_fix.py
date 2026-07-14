from __future__ import annotations

from datetime import date, datetime

import streamlit as st

from nohtus.db import connect, q
import nohtus.pages.saved_outbound_business_v4 as saved_v4


def _extend_default_range_to_scheduled_orders():
    today = date.today()
    latest_df = q("""
        SELECT MAX(order_date) AS latest_date
        FROM outbound_orders
        WHERE IFNULL(status,'')<>'취소됨'
          AND TRIM(COALESCE(order_date,''))<>''
    """)
    if latest_df.empty:
        return
    latest_text = str(latest_df.iloc[0].get("latest_date") or "").strip()
    if not latest_text:
        return
    try:
        latest_date = date.fromisoformat(latest_text[:10])
    except Exception:
        return
    if latest_date <= today:
        return

    current_start = st.session_state.get("saved_start_date")
    current_end = st.session_state.get("saved_end_date")
    default_like = current_start in (None, today) and current_end in (None, today)
    if default_like:
        st.session_state["saved_start_date"] = today
        st.session_state["saved_end_date"] = latest_date


def _cancelled_order_customer(order_id):
    with connect() as con:
        row = con.execute(
            """
            SELECT COALESCE(customer_name,''), COALESCE(customer_company,''),
                   COALESCE(order_date,'')
            FROM outbound_orders
            WHERE id=?
            """,
            (int(order_id),),
        ).fetchone()
    if not row:
        return "", "", ""
    return tuple(str(value or "").strip() for value in row)


def _refresh_customer_last_sale(customer_name, company, cancelled_date):
    """취소된 출고지시의 날짜가 최근거래일이면 유효한 이전 날짜로 되돌린다."""
    customer_name = str(customer_name or "").strip()
    company = str(company or "").strip()
    cancelled_date = str(cancelled_date or "").strip()[:10]
    if not customer_name or not cancelled_date:
        return

    with connect() as con:
        cur = con.cursor()
        stored = cur.execute(
            """
            SELECT id, COALESCE(last_sale_date,'')
            FROM customer_last_sales
            WHERE customer_name=? AND company=?
            """,
            (customer_name, company),
        ).fetchone()

        # 현재 저장값이 취소된 지시보다 다른 최신 거래라면 손대지 않는다.
        if stored and str(stored[1] or "").strip()[:10] != cancelled_date:
            return

        valid = cur.execute(
            """
            SELECT MAX(order_date)
            FROM outbound_orders
            WHERE COALESCE(customer_name,'')=?
              AND COALESCE(customer_company,'')=?
              AND IFNULL(status,'')<>'취소됨'
              AND TRIM(COALESCE(order_date,''))<>''
            """,
            (customer_name, company),
        ).fetchone()
        valid_date = str(valid[0] if valid else "").strip()[:10]
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if valid_date:
            if stored:
                cur.execute(
                    """
                    UPDATE customer_last_sales
                    SET last_sale_date=?, source_company='WMS', updated_at=?
                    WHERE id=?
                    """,
                    (valid_date, now, int(stored[0])),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO customer_last_sales(
                        customer_name, company, last_sale_date, source_company, updated_at
                    ) VALUES(?,?,?,?,?)
                    """,
                    (customer_name, company, valid_date, "WMS", now),
                )
        elif stored:
            cur.execute("DELETE FROM customer_last_sales WHERE id=?", (int(stored[0]),))
        con.commit()


def page_saved_outbound():
    _extend_default_range_to_scheduled_orders()

    original_cancel_order = saved_v4.saved_v2._cancel_order

    def patched_cancel_order(order_id):
        customer_name, company, cancelled_date = _cancelled_order_customer(order_id)
        result = original_cancel_order(order_id)
        _refresh_customer_last_sale(customer_name, company, cancelled_date)
        return result

    saved_v4.saved_v2._cancel_order = patched_cancel_order
    try:
        return saved_v4.page_saved_outbound()
    finally:
        saved_v4.saved_v2._cancel_order = original_cancel_order
