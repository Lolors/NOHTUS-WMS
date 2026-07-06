from __future__ import annotations

from html import escape

import streamlit.components.v1 as components

import nohtus.pages.saved_outbound_business_v2 as saved_v2


def _render_saved_orders_component(orders_df, selected_order_id):
    rows_html = []
    for r in orders_df.itertuples(index=False):
        oid = int(getattr(r, "id"))
        created = str(getattr(r, "order_date", "") or getattr(r, "created_at", ""))[:10]
        customer = str(getattr(r, "customer_name", "") or "-")
        status = str(getattr(r, "status", "저장됨") or "저장됨")
        items_text = saved_v2._order_items_summary(oid)
        selected_class = " selected" if int(selected_order_id or 0) == oid else ""
        status_class = "cancel" if status == "취소됨" else "save"
        rows_html.append(
            f"""
            <button class="saved-order-row{selected_class}" type="button" data-order-id="{oid}">
              <span class="saved-order-cell">{escape(created)}</span>
              <span class="saved-order-cell" title="{escape(customer)}">{escape(customer)}</span>
              <span class="saved-order-cell" title="{escape(items_text)}">{escape(items_text)}</span>
              <span class="saved-order-cell status {status_class}">{escape(status)}</span>
            </button>
            """
        )

    html = f"""
    <!doctype html>
    <html>
    <head>
      <meta charset="utf-8" />
      <style>
        html, body {{ margin:0; padding:0; background:transparent; font-family:Arial, 'Noto Sans KR', sans-serif; }}
        .saved-order-list {{ width:100%; box-sizing:border-box; }}
        .saved-order-head {{
          display:grid; grid-template-columns:.8fr 1.6fr 4.6fr .9fr; gap:8px; align-items:center;
          padding:8px 10px; border-bottom:1px solid #e5e7eb; color:#64748b; font-size:13px; font-weight:800;
          box-sizing:border-box;
        }}
        .saved-order-row {{
          width:100%; display:grid; grid-template-columns:.8fr 1.6fr 4.6fr .9fr; gap:8px; align-items:center;
          padding:9px 10px; border:0; border-bottom:1px solid #f1f5f9; border-radius:8px;
          background:white; color:#111827; text-align:left; cursor:pointer; box-sizing:border-box;
          font:inherit;
        }}
        .saved-order-row:hover {{ background:#f8fafc; text-decoration:underline; text-underline-offset:3px; }}
        .saved-order-row.selected {{ background:#eff6ff; border-bottom-color:#bfdbfe; }}
        .saved-order-cell {{ min-width:0; font-size:14px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
        .status {{ text-align:center; font-weight:700; }}
        .status.save {{ color:#2563eb; }}
        .status.cancel {{ color:#dc2626; }}
      </style>
    </head>
    <body>
      <div class="saved-order-list">
        <div class="saved-order-head">
          <div>날짜</div>
          <div>매출처</div>
          <div>포함된 출고 제품</div>
          <div style="text-align:center;">상태</div>
        </div>
        {''.join(rows_html)}
      </div>
      <script>
        document.querySelectorAll('.saved-order-row').forEach(function(row) {{
          row.addEventListener('click', function() {{
            var oid = row.getAttribute('data-order-id');
            var base = window.parent.location.pathname;
            window.parent.location.href = base + '?saved_order_id=' + encodeURIComponent(oid) + '#selected-outbound-detail';
          }});
        }});
      </script>
    </body>
    </html>
    """
    height = 42 + max(1, len(orders_df)) * 43
    components.html(html, height=height, scrolling=False)


def page_saved_outbound():
    original_renderer = saved_v2._render_saved_orders
    saved_v2._render_saved_orders = _render_saved_orders_component
    try:
        return saved_v2.page_saved_outbound()
    finally:
        saved_v2._render_saved_orders = original_renderer
