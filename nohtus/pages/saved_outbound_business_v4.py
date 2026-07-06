from __future__ import annotations

from html import escape

import streamlit as st
import streamlit.components.v1 as components

import nohtus.pages.saved_outbound_business_v2 as saved_v2


SELECTED_NO_CHIP_STYLE = (
    "width:48px;height:28px;min-width:48px;max-width:48px;"
    "display:inline-flex;align-items:center;justify-content:center;"
    "padding:0;border:1px solid #93c5fd;background:#dbeafe;color:#1d4ed8;"
    "border-radius:6px;font-size:13px;font-weight:700;line-height:1;box-sizing:border-box;"
)


def _status_text_html(status):
    status = str(status or "저장됨")
    if status == "취소됨":
        return "<span style='color:#dc2626;font-weight:800;'>취소됨</span>"
    if status == "수정됨":
        return "<span style='color:#16a34a;font-weight:800;'>수정됨</span>"
    return "<span style='color:#2563eb;font-weight:800;'>저장됨</span>"


def _selected_number_chip(oid):
    return f"<span class='saved-order-no-chip selected' style='{SELECTED_NO_CHIP_STYLE}'>#{int(oid)}</span>"


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


def _row_cell_html(content, *, title="", class_name=""):
    title_attr = f" title='{escape(title)}'" if title else ""
    return f"<div class='saved-order-cell {class_name}'{title_attr}>{content}</div>"


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
            height:34px;display:flex;align-items:center;min-width:0;
            color:#111827;font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
            line-height:1.2;
        }
        .saved-order-status{justify-content:center;text-align:center;}
        .saved-order-sep{height:1px;background:#f1f5f9;margin:3px 0 5px;}
        .saved-order-no-chip{
            width:48px!important;height:28px!important;min-width:48px!important;max-width:48px!important;
            display:inline-flex!important;align-items:center!important;justify-content:center!important;
            padding:0!important;box-sizing:border-box!important;line-height:1!important;
        }
        div[data-testid="stButton"] button[kind="secondary"]{
            width:48px!important;min-width:48px!important;max-width:48px!important;height:28px!important;
            padding:0!important;border:1px solid #d1d5db!important;
            background:#ffffff!important;color:#334155!important;border-radius:6px!important;
            font-size:13px!important;font-weight:500!important;line-height:1!important;
            box-shadow:none!important;box-sizing:border-box!important;
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
        cols = st.columns([0.65, 0.9, 1.7, 4.5, 0.9], gap="small")
        with cols[0]:
            if selected:
                st.markdown(f"<div style='height:34px;display:flex;align-items:center;'>{_selected_number_chip(oid)}</div>", unsafe_allow_html=True)
            else:
                if st.button(f"#{oid}", key=f"open_order_no_{oid}", use_container_width=False, type="secondary"):
                    st.session_state["selected_saved_order_id"] = oid
                    st.session_state["_scroll_saved_outbound_detail"] = True
                    st.rerun()
        with cols[1]:
            st.markdown(_row_cell_html(escape(created)), unsafe_allow_html=True)
        with cols[2]:
            st.markdown(_row_cell_html(escape(customer), title=customer), unsafe_allow_html=True)
        with cols[3]:
            st.markdown(_row_cell_html(escape(items_text), title=items_text), unsafe_allow_html=True)
        with cols[4]:
            st.markdown(_row_cell_html(_status_text_html(status), class_name="saved-order-status"), unsafe_allow_html=True)
        st.markdown("<div class='saved-order-sep'></div>", unsafe_allow_html=True)


def page_saved_outbound():
    original_renderer = saved_v2._render_saved_orders
    saved_v2._render_saved_orders = _render_saved_orders_compact_number_button
    try:
        result = saved_v2.page_saved_outbound()
        _scroll_selected_detail_once()
        return result
    finally:
        saved_v2._render_saved_orders = original_renderer
