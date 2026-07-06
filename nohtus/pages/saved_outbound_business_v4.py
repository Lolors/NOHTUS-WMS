from __future__ import annotations

from html import escape

import streamlit as st

import nohtus.pages.saved_outbound_business_v2 as saved_v2


def _status_text_html(status):
    status = str(status or "저장됨")
    if status == "취소됨":
        return "<span style='color:#dc2626;font-weight:800;'>취소됨</span>"
    if status == "수정됨":
        return "<span style='color:#16a34a;font-weight:800;'>수정됨</span>"
    return "<span style='color:#2563eb;font-weight:800;'>저장됨</span>"


def _render_saved_orders_compact_number_button(orders_df, selected_order_id):
    st.markdown(
        """
        <style>
        .saved-order-head-clean{
            display:grid;grid-template-columns:.65fr .9fr 1.7fr 4.5fr .9fr;gap:8px;
            align-items:center;padding:8px 10px;border-bottom:1px solid #e5e7eb;
            color:#64748b;font-size:13px;font-weight:800;
        }
        .saved-order-cell{
            height:32px;display:flex;align-items:center;min-width:0;
            color:#111827;font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
        }
        .saved-order-status{justify-content:center;}
        .saved-order-selected-wrap{
            background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;
            padding:3px 0;margin:2px 0;
        }
        .saved-order-sep{height:1px;background:#f1f5f9;margin:3px 0 5px;}
        div[data-testid="stButton"] button[kind="secondary"]{
            width:auto!important;min-width:42px!important;height:26px!important;
            padding:2px 8px!important;border:1px solid #d1d5db!important;
            background:#ffffff!important;color:#334155!important;border-radius:6px!important;
            font-size:13px!important;font-weight:500!important;line-height:1!important;
            box-shadow:none!important;
        }
        div[data-testid="stButton"] button[kind="secondary"]:hover{
            background:#f8fafc!important;border-color:#cbd5e1!important;color:#111827!important;
        }
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
        if selected:
            st.markdown("<div class='saved-order-selected-wrap'>", unsafe_allow_html=True)
        cols = st.columns([0.65, 0.9, 1.7, 4.5, 0.9], gap="small")
        with cols[0]:
            if st.button(f"#{oid}", key=f"open_order_no_{oid}", use_container_width=False, type="secondary"):
                st.session_state["selected_saved_order_id"] = oid
                st.rerun()
        with cols[1]:
            st.markdown(f"<div class='saved-order-cell'>{escape(created)}</div>", unsafe_allow_html=True)
        with cols[2]:
            st.markdown(f"<div class='saved-order-cell' title='{escape(customer)}'>{escape(customer)}</div>", unsafe_allow_html=True)
        with cols[3]:
            st.markdown(f"<div class='saved-order-cell' title='{escape(items_text)}'>{escape(items_text)}</div>", unsafe_allow_html=True)
        with cols[4]:
            st.markdown(f"<div class='saved-order-cell saved-order-status'>{_status_text_html(status)}</div>", unsafe_allow_html=True)
        if selected:
            st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("<div class='saved-order-sep'></div>", unsafe_allow_html=True)


def page_saved_outbound():
    original_renderer = saved_v2._render_saved_orders
    saved_v2._render_saved_orders = _render_saved_orders_compact_number_button
    try:
        return saved_v2.page_saved_outbound()
    finally:
        saved_v2._render_saved_orders = original_renderer
