from __future__ import annotations

from html import escape

import streamlit as st

import nohtus.pages.saved_outbound_business_v2 as saved_v2


def _status_text_html(status):
    status = str(status or "저장됨")
    if status == "취소됨":
        return "<span class='saved-order-status cancel'>취소됨</span>"
    if status == "수정됨":
        return "<span class='saved-order-status edit'>수정됨</span>"
    return "<span class='saved-order-status save'>저장됨</span>"


def _render_saved_orders_clean(orders_df, selected_order_id):
    rows = []
    for r in orders_df.itertuples(index=False):
        oid = int(getattr(r, "id"))
        created = str(getattr(r, "order_date", "") or getattr(r, "created_at", ""))[:10]
        customer = str(getattr(r, "customer_name", "") or "-")
        status = str(getattr(r, "status", "저장됨") or "저장됨")
        items_text = saved_v2._order_items_summary(oid)
        selected_class = " selected" if int(selected_order_id or 0) == oid else ""
        rows.append(
            f"""
            <a class='saved-order-row{selected_class}' href='?saved_order_id={oid}#selected-outbound-detail' target='_self'>
              <span class='saved-order-cell no'>#{oid}</span>
              <span class='saved-order-cell date'>{escape(created)}</span>
              <span class='saved-order-cell customer' title='{escape(customer)}'>{escape(customer)}</span>
              <span class='saved-order-cell items' title='{escape(items_text)}'>{escape(items_text)}</span>
              <span class='saved-order-cell status-cell'>{_status_text_html(status)}</span>
            </a>
            """
        )
    st.markdown(
        f"""
        <style>
        .saved-order-list-clean{{width:100%;}}
        .saved-order-head-clean{{
            display:grid;grid-template-columns:.65fr .9fr 1.7fr 4.5fr .9fr;gap:8px;
            align-items:center;padding:8px 10px;border-bottom:1px solid #e5e7eb;
            color:#64748b;font-size:13px;font-weight:800;
        }}
        .saved-order-row{{
            display:grid;grid-template-columns:.65fr .9fr 1.7fr 4.5fr .9fr;gap:8px;
            align-items:center;padding:10px 10px;border-bottom:1px solid #f1f5f9;
            color:#111827!important;text-decoration:none!important;border-radius:8px;
            cursor:pointer;min-height:42px;
        }}
        .saved-order-row:hover{{
            background:#f8fafc;text-decoration:none!important;
        }}
        .saved-order-row:hover .saved-order-cell:not(.status-cell){{
            text-decoration:underline;text-underline-offset:3px;
        }}
        .saved-order-row.selected{{
            background:#eff6ff;border:1px solid #bfdbfe;border-bottom-color:#bfdbfe;
            margin:2px 0;
        }}
        .saved-order-cell{{
            min-width:0;font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
            color:#111827;
        }}
        .saved-order-cell.no{{font-weight:500;color:#334155;}}
        .saved-order-cell.status-cell{{text-align:center;}}
        .saved-order-status.save{{color:#2563eb;font-weight:800;}}
        .saved-order-status.edit{{color:#16a34a;font-weight:800;}}
        .saved-order-status.cancel{{color:#dc2626;font-weight:800;}}
        </style>
        <div class='saved-order-list-clean'>
          <div class='saved-order-head-clean'>
            <div>번호</div>
            <div>날짜</div>
            <div>매출처</div>
            <div>포함된 출고 제품</div>
            <div style='text-align:center;'>상태</div>
          </div>
          {''.join(rows)}
        </div>
        """,
        unsafe_allow_html=True,
    )


def page_saved_outbound():
    original_renderer = saved_v2._render_saved_orders
    saved_v2._render_saved_orders = _render_saved_orders_clean
    try:
        return saved_v2.page_saved_outbound()
    finally:
        saved_v2._render_saved_orders = original_renderer
