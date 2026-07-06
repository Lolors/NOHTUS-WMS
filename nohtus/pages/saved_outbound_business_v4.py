from __future__ import annotations

from datetime import date
from html import escape

import streamlit as st
import streamlit.components.v1 as components

import nohtus.pages.saved_outbound_business_v2 as saved_v2


BUTTON_W = 48
BUTTON_H = 28
ROW_H = 46


def _status_text_html(status):
    status = str(status or "저장됨")
    if status == "취소됨":
        return "<span style='color:#dc2626;font-weight:800;'>취소됨</span>"
    if status == "수정됨":
        return "<span style='color:#16a34a;font-weight:800;'>수정됨</span>"
    return "<span style='color:#2563eb;font-weight:800;'>저장됨</span>"


def _selected_number_chip(oid):
    return f"""
    <span class='saved-order-no-chip selected'>#{int(oid)}</span>
    """


def _scroll_selected_detail_once():
    if not st.session_state.pop("_scroll_saved_outbound_detail", False):
        return
    components.html(
        """
        <script>
        setTimeout(function(){
          try{
            const target = window.parent.document.getElementById('selected-outbound-detail');
            if(target){ target.scrollIntoView({behavior:'smooth', block:'center'}); }
          }catch(e){}
        }, 120);
        </script>
        """,
        height=0,
        scrolling=False,
    )


def _cell(content, *, title="", class_name=""):
    title_attr = f" title='{escape(str(title))}'" if title else ""
    return f"<div class='saved-order-cell {class_name}'{title_attr}>{content}</div>"


def _saved_outbound_total_pages(per_page=10):
    all_orders = saved_v2.q(
        f"""
        SELECT DISTINCT o.id, o.created_at, o.order_date, COALESCE(o.title,'') AS title,
               COALESCE(o.customer_name,'') AS customer_name,
               COALESCE(o.customer_company,'') AS customer_company,
               o.status
        FROM outbound_orders o
        JOIN outbound_order_items i ON o.id=i.order_id
        WHERE IFNULL(o.status,'')<>'취소됨'
          AND {saved_v2._valid_outbound_exists_sql('o', 'i')}
        ORDER BY o.id DESC
        """
    )
    if all_orders.empty:
        return 1

    filtered = all_orders.copy()
    start_date = st.session_state.get("saved_start_date", date.today())
    end_date = st.session_state.get("saved_end_date", date.today())
    customer_term = str(st.session_state.get("saved_customer_search", "") or "")
    search_term = str(st.session_state.get("saved_outbound_search", "") or "")

    if start_date:
        filtered = filtered[filtered["order_date"] >= str(start_date)]
    if end_date:
        filtered = filtered[filtered["order_date"] <= str(end_date)]
    if customer_term.strip():
        needle = customer_term.strip().lower()
        filtered = filtered[filtered["customer_name"].fillna("").astype(str).str.lower().str.contains(needle, regex=False)]
    if search_term.strip() and not filtered.empty:
        ids = filtered["id"].astype(int).tolist()
        if ids:
            placeholders = ",".join(["?"] * len(ids))
            items_df = saved_v2.q(
                f"""
                SELECT DISTINCT i.order_id
                FROM outbound_order_items i
                JOIN outbound_orders o ON o.id=i.order_id
                WHERE i.order_id IN ({placeholders})
                  AND i.product_name LIKE ?
                  AND {saved_v2._valid_outbound_exists_sql('o', 'i')}
                """,
                tuple(ids + [f"%{search_term.strip()}%"]),
            )
            matched_ids = items_df["order_id"].astype(int).tolist() if not items_df.empty else []
            filtered = filtered[filtered["id"].astype(int).isin(matched_ids)]

    total = len(filtered)
    return max(1, (total + per_page - 1) // per_page)


def _render_saved_order_page_input():
    total_pages = _saved_outbound_total_pages(per_page=10)
    if total_pages <= 1:
        return
    current_page = int(st.session_state.get("saved_order_page", 1) or 1)
    current_page = max(1, min(current_page, total_pages))
    st.session_state["saved_order_page"] = current_page
    st.markdown(
        """
        <style>
        div[data-testid="stNumberInput"]{
            width:138px!important;
            margin:10px auto 2px auto!important;
            overflow:visible!important;
        }
        div[data-testid="stNumberInput"] input{
            height:54px!important;
            min-height:54px!important;
            text-align:center!important;
            font-size:16px!important;
        }
        div[data-testid="stNumberInput"] button{
            display:flex!important;
            visibility:visible!important;
            opacity:1!important;
            width:32px!important;
            min-width:32px!important;
            height:27px!important;
            min-height:27px!important;
            padding:0!important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    _left, page_col, _right = st.columns([1, 0.22, 1])
    with page_col:
        selected_page = st.number_input(
            "저장된 출고지시 페이지",
            min_value=1,
            max_value=total_pages,
            value=current_page,
            step=1,
            key="saved_order_page_input",
            label_visibility="collapsed",
        )
    if int(selected_page) != current_page:
        st.session_state["saved_order_page"] = int(selected_page)
        st.rerun()


def _render_saved_orders_compact_number_button(orders_df, selected_order_id):
    st.markdown(
        f"""
        <style>
        .saved-order-head-clean{{
            display:grid;grid-template-columns:.65fr .9fr 1.7fr 4.5fr .9fr;gap:8px;
            align-items:center;padding:8px 10px;border-bottom:1px solid #e5e7eb;
            color:#64748b;font-size:13px;font-weight:800;
        }}
        .saved-order-cell{{
            height:{ROW_H}px;display:flex;align-items:center;min-width:0;
            color:#111827;font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
            line-height:1.2;
        }}
        .saved-order-status{{justify-content:center;text-align:center;}}
        .saved-order-sep{{height:1px;background:#f6f7f9;margin:1px 0 3px;}}
        .saved-order-no-chip{{
            display:inline-flex;align-items:center;justify-content:center;
            width:{BUTTON_W}px;min-width:{BUTTON_W}px;max-width:{BUTTON_W}px;
            height:{BUTTON_H}px;min-height:{BUTTON_H}px;max-height:{BUTTON_H}px;
            padding:0;border:1px solid #d1d5db;
            background:#fff;color:#334155;border-radius:6px;font-size:13px;font-weight:500;
            box-sizing:border-box;line-height:1;
        }}
        .saved-order-no-chip.selected{{
            border-color:#93c5fd;background:#dbeafe;color:#1d4ed8;font-weight:700;
        }}
        </style>
        <div class='saved-order-head-clean'>
          <div>번호</div>
          <div>날짜</div>
          <div>매출처</div>
          <div>포함된 출고 제품</div>
          <div style='text-align:center;'>상태</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    for r in orders_df.itertuples(index=False):
        oid = int(getattr(r, "id"))
        created = str(getattr(r, "order_date", "") or getattr(r, "created_at", ""))[:10]
        customer = str(getattr(r, "customer_name", "") or "-")
        status = str(getattr(r, "status", "저장됨") or "저장됨")
        items_text = saved_v2._order_items_summary(oid)
        selected = int(selected_order_id or 0) == oid
        cols = st.columns([0.65, 0.9, 1.7, 4.5, 0.9], gap="small")
        with cols[0]:
            if selected:
                st.markdown(_cell(_selected_number_chip(oid)), unsafe_allow_html=True)
            else:
                if st.button(f"#{oid}", key=f"open_order_no_{oid}", use_container_width=False, type="secondary"):
                    st.session_state["selected_saved_order_id"] = oid
                    st.session_state["_scroll_saved_outbound_detail"] = True
                    st.rerun()
        with cols[1]:
            st.markdown(_cell(escape(created)), unsafe_allow_html=True)
        with cols[2]:
            st.markdown(_cell(escape(customer), title=customer), unsafe_allow_html=True)
        with cols[3]:
            st.markdown(_cell(escape(items_text), title=items_text), unsafe_allow_html=True)
        with cols[4]:
            st.markdown(_cell(_status_text_html(status), class_name="saved-order-status"), unsafe_allow_html=True)
        st.markdown("<div class='saved-order-sep'></div>", unsafe_allow_html=True)
    _render_saved_order_page_input()


def page_saved_outbound():
    original_renderer = saved_v2._render_saved_orders
    original_button = st.button
    original_markdown = st.markdown

    def patched_button(*args, **kwargs):
        if kwargs.get("key") in {"page_prev", "page_next"}:
            return False
        return original_button(*args, **kwargs)

    def patched_markdown(body, *args, **kwargs):
        if isinstance(body, str) and "text-align:center;color:#64748b;font-weight:700;margin:8px 0;" in body:
            return None
        return original_markdown(body, *args, **kwargs)

    saved_v2._render_saved_orders = _render_saved_orders_compact_number_button
    st.button = patched_button
    st.markdown = patched_markdown
    try:
        result = saved_v2.page_saved_outbound()
        _scroll_selected_detail_once()
        return result
    finally:
        saved_v2._render_saved_orders = original_renderer
        st.button = original_button
        st.markdown = original_markdown
