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


def _normalize_order_number_search(value):
    text = str(value or "").strip()
    text = text.replace("출고지시서", "").replace("번호", "").replace("#", "").strip()
    return text


def page_saved_outbound():
    _extend_default_range_to_scheduled_orders()

    original_cancel_order = saved_v4.saved_v2._cancel_order
    original_filter_orders = saved_v4._filter_orders
    original_text_input = st.text_input
    original_columns = st.columns
    original_caption = st.caption

    def patched_cancel_order(order_id):
        customer_name, company, cancelled_date = _cancelled_order_customer(order_id)
        result = original_cancel_order(order_id)
        _refresh_customer_last_sale(customer_name, company, cancelled_date)
        return result

    def patched_filter_orders(all_orders, start_date, end_date, customer_term, search_term):
        number_term = _normalize_order_number_search(
            st.session_state.get("saved_outbound_number_search", "")
        )
        if number_term:
            # 출고지시서 번호는 날짜 범위와 무관하게 전체 저장 이력에서 찾는다.
            filtered = original_filter_orders(all_orders, None, None, customer_term, search_term)
            if number_term.isdigit():
                return filtered[filtered["id"].astype(int) == int(number_term)]
            return filtered.iloc[0:0]
        return original_filter_orders(all_orders, start_date, end_date, customer_term, search_term)

    def patched_columns(spec, *args, **kwargs):
        # 기본 필터 행의 매출처/제품명 검색 폭을 줄이고 남는 폭을 번호 검색에 자연스럽게 사용한다.
        if isinstance(spec, (list, tuple)) and list(spec) == [1.5, 1.5, 3, 4]:
            spec = [1.5, 1.5, 2.1, 4.9]
        return original_columns(spec, *args, **kwargs)

    def patched_text_input(label, *args, **kwargs):
        label_text = str(label or "").strip()
        key = str(kwargs.get("key") or "")

        if label_text == "검색" and key == "saved_outbound_search":
            product_col, number_col = original_columns([2.8, 4.2], gap="small")
            with product_col:
                product_term = original_text_input(label, *args, **kwargs)
            with number_col:
                original_text_input(
                    "출고지시서 번호",
                    placeholder="12345",
                    key="saved_outbound_number_search",
                    help="이력조회 메모에 표시되는 출고지시서 번호입니다. 번호로 검색 시 전체 기간에서 검색합니다.",
                )
            return product_term

        return original_text_input(label, *args, **kwargs)

    def patched_caption(body, *args, **kwargs):
        if str(body or "").strip() == "날짜, 매출처, 제품 검색으로 출고지시서를 필터링합니다.":
            body = "날짜, 매출처, 제품명, 출고지시서 번호로 출고지시서를 필터링합니다. 번호 검색은 전체 기간을 대상으로 합니다."
        return original_caption(body, *args, **kwargs)

    saved_v4.saved_v2._cancel_order = patched_cancel_order
    saved_v4._filter_orders = patched_filter_orders
    st.text_input = patched_text_input
    st.columns = patched_columns
    st.caption = patched_caption
    try:
        return saved_v4.page_saved_outbound()
    finally:
        saved_v4.saved_v2._cancel_order = original_cancel_order
        saved_v4._filter_orders = original_filter_orders
        st.text_input = original_text_input
        st.columns = original_columns
        st.caption = original_caption
