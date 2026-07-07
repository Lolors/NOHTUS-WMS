"""Saved outbound orders page for NOHTUS WMS.

저장된 출고지시 화면을 app.py에서 분리한 페이지 모듈이다.
"""

from __future__ import annotations

from datetime import date
from html import escape

import streamlit as st

from nohtus.db import q
from nohtus.dates import display_date_only
from nohtus.services.outbound import cancel_saved_order, load_outbound_order, outbound_excel_bytes, outbound_pdf_bytes


def _ensure_outbound_customer_columns():
    from nohtus.db import connect
    with connect() as con:
        cur = con.cursor()
        cols = {r[1] for r in cur.execute("PRAGMA table_info(outbound_orders)").fetchall()}
        if "customer_name" not in cols:
            cur.execute("ALTER TABLE outbound_orders ADD COLUMN customer_name TEXT")
        if "customer_company" not in cols:
            cur.execute("ALTER TABLE outbound_orders ADD COLUMN customer_company TEXT")
        con.commit()


def _run_cancel_order(order_id):
    item_count, restored_count = cancel_saved_order(int(order_id))
    st.session_state.pop("confirm_cancel_order_id", None)
    st.session_state.pop("selected_saved_order_id", None)
    st.session_state["cancel_order_done_msg"] = f"출고지시서 #{int(order_id)} 취소 완료: {item_count}개 품목 / 원복 {restored_count}건"


def _show_cancel_order_confirm_inline(order_id):
    st.markdown("""
    <div style='border:1px solid #e5e7eb;background:#ffffff;border-radius:16px;padding:18px 20px;margin:12px auto;max-width:560px;box-shadow:0 18px 40px rgba(15,23,42,.12);'>
      <div style='font-weight:900;color:#111827;font-size:19px;margin-bottom:10px;'>⚠ 출고지시 취소 확인</div>
      <div style='color:#334155;font-weight:400;line-height:1.7;'>정말로 취소하시겠습니까?<br>제품의 수량은 출고지시 이전으로 복원됩니다.</div>
    </div>
    """, unsafe_allow_html=True)
    _left, c1, c2, _right = st.columns([1.2, 1, 1.7, 1.2])
    with c1:
        if st.button("아니오", use_container_width=True, key=f"cancel_no_{int(order_id)}"):
            st.session_state.pop("confirm_cancel_order_id", None)
            st.rerun()
    with c2:
        if st.button("예, 취소합니다", type="primary", use_container_width=True, key=f"cancel_yes_{int(order_id)}"):
            try:
                _run_cancel_order(int(order_id))
                st.rerun()
            except Exception as e:
                st.error(str(e))


def _show_cancel_order_confirm(order_id):
    dialog_api = getattr(st, "dialog", None) or getattr(st, "experimental_dialog", None)
    if not dialog_api:
        _show_cancel_order_confirm_inline(order_id)
        return

    @dialog_api("⚠ 출고지시 취소 확인")
    def _dialog():
        st.markdown("""
        <style>
        div[data-testid="stDialog"] div[data-testid="stMarkdownContainer"] p,
        div[data-testid="stDialog"] div[data-testid="stMarkdownContainer"] div {font-weight:400!important;}
        div[data-testid="stDialog"] div[data-testid="stHorizontalBlock"]{justify-content:center!important;}
        div[data-testid="stDialog"] div[data-testid="stButton"] > button{
            min-height:46px!important;min-width:180px!important;border-radius:10px!important;font-weight:800!important;white-space:nowrap!important;
        }
        </style>
        <div style='font-size:16px;line-height:1.7;color:#334155;margin:6px 0 18px 0;font-weight:400;'>
            정말로 취소하시겠습니까?<br>
            제품의 수량은 출고지시 이전으로 복원됩니다.
        </div>
        """, unsafe_allow_html=True)
        _left, c1, c2, _right = st.columns([1.0, 1.0, 1.7, 1.0], gap="medium")
        with c1:
            if st.button("아니오", use_container_width=True, key=f"cancel_no_{int(order_id)}"):
                st.session_state.pop("confirm_cancel_order_id", None)
                st.rerun()
        with c2:
            if st.button("예, 취소합니다", type="primary", use_container_width=True, key=f"cancel_yes_{int(order_id)}"):
                try:
                    _run_cancel_order(int(order_id))
                    st.rerun()
                except Exception as e:
                    st.error(str(e))
    _dialog()


def _status_color(status):
    colors = {
        "수정됨": "#16a34a",
        "취소됨": "#dc2626",
        "저장됨": "#334155",
    }
    return colors.get(str(status or "저장됨"), "#475569")


def _status_button_type(status, selected):
    if selected:
        return "primary"
    return "secondary"


def _order_items_summary(order_id, max_items=3):
    df = q(
        """
        SELECT product_name, SUM(qty) AS qty
        FROM outbound_order_items
        WHERE order_id=?
        GROUP BY product_name
        ORDER BY MIN(id)
        """,
        (int(order_id),),
    )
    if df.empty:
        return "-"
    names = [str(r.product_name or "-") for r in df.itertuples(index=False)]
    shown = names[:max_items]
    remain = max(0, len(names) - len(shown))
    text = ", ".join(shown)
    if remain:
        text += f" 외 {remain}품목"
    return text


def _short_cell_text(value, max_len=34):
    text = str(value or "-")
    return text if len(text) <= max_len else text[:max_len - 1] + "…"


def _select_saved_order(order_id):
    st.session_state["selected_saved_order_id"] = int(order_id)
    st.rerun()


def _render_saved_orders(orders_df, selected_order_id):
    st.markdown("""
    <style>
    .saved-order-head{display:grid;grid-template-columns:.75fr 1.05fr 1.6fr 4.2fr .9fr;gap:6px;align-items:center;padding:5px 8px;border-bottom:1px solid #e5e7eb;color:#64748b;font-size:12.5px;font-weight:800;}
    .saved-order-cell{min-height:34px;display:flex;align-items:center;border-bottom:1px solid #f1f5f9;color:#111827;font-size:13px;line-height:1.25;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;padding:2px 0;}
    .saved-order-number{justify-content:center;font-weight:800;color:#334155;}
    .saved-order-date{color:#475569;}
    .saved-order-title{font-weight:600;white-space:normal;}
    .saved-order-status-note{height:0;margin:0;padding:0;overflow:hidden;}
    div[data-testid="stButton"] > button[kind="secondary"]{min-height:32px;padding-top:4px!important;padding-bottom:4px!important;}
    div[data-testid="stButton"] > button[kind="primary"]{min-height:32px;padding-top:4px!important;padding-bottom:4px!important;}
    </style>
    <div class='saved-order-head'>
      <div style='text-align:center;'>번호</div>
      <div>날짜</div>
      <div>매출처</div>
      <div>포함된 출고 제품</div>
      <div style='text-align:center;'>상태</div>
    </div>
    """, unsafe_allow_html=True)

    for r in orders_df.itertuples(index=False):
        oid = int(getattr(r, "id"))
        created = str(getattr(r, "order_date", "") or getattr(r, "created_at", ""))[:10]
        customer = str(getattr(r, "customer_name", "") or "-")
        status = str(getattr(r, "status", "저장됨") or "저장됨")
        items_text = _order_items_summary(oid)
        selected = int(selected_order_id or 0) == oid
        row_cols = st.columns([0.75, 1.05, 1.6, 4.2, 0.9], gap="small")
        with row_cols[0]:
            st.markdown(f"<div class='saved-order-cell saved-order-number'>{oid}</div>", unsafe_allow_html=True)
        with row_cols[1]:
            st.markdown(f"<div class='saved-order-cell saved-order-date'>{escape(_short_cell_text(created, 12))}</div>", unsafe_allow_html=True)
        with row_cols[2]:
            st.markdown(f"<div class='saved-order-cell'>{escape(_short_cell_text(customer, 18))}</div>", unsafe_allow_html=True)
        with row_cols[3]:
            st.markdown(f"<div class='saved-order-cell saved-order-title'>{escape(items_text)}</div>", unsafe_allow_html=True)
        with row_cols[4]:
            st.markdown(
                f"<div class='saved-order-status-note' style='color:{_status_color(status)}'>{escape(status)}</div>",
                unsafe_allow_html=True,
            )
            if st.button(status, key=f"open_order_status_{oid}", use_container_width=True, type=_status_button_type(status, selected)):
                _select_saved_order(oid)
    return st.session_state.get("selected_saved_order_id") or (int(orders_df.iloc[0]["id"]) if not orders_df.empty else None)


def page_saved_outbound():
    _ensure_outbound_customer_columns()
    st.markdown("<h1 style='text-align:left;margin-bottom:0.2em;'>저장된 출고지시</h1>", unsafe_allow_html=True)
    if st.session_state.get("cancel_order_done_msg"):
        st.success(st.session_state.pop("cancel_order_done_msg"))
    st.caption("날짜, 매출처, 제품 검색으로 출고지시서를 필터링합니다.")

    today = date.today()
    filter_outer, _blank = st.columns([7, 3], gap="large")
    with filter_outer:
        f1, f2, f3, f4 = st.columns([2, 2, 3, 3], gap="small")
        with f1:
            start_date = st.date_input("시작일", value=st.session_state.get("saved_start_date", today), key="saved_start_date")
        with f2:
            end_date = st.date_input("종료일", value=st.session_state.get("saved_end_date", today), key="saved_end_date")
        with f3:
            customer_term = st.text_input("매출처", placeholder="매출처명 일부 입력", key="saved_customer_search")
        with f4:
            search_term = st.text_input("검색", placeholder="제품명 일부 입력", key="saved_outbound_search")

    if start_date and end_date and start_date > end_date:
        st.error("시작일은 종료일보다 늦을 수 없습니다.")
        return

    all_orders = q("""
        SELECT id, created_at, order_date, COALESCE(title,'') AS title,
               COALESCE(customer_name,'') AS customer_name,
               COALESCE(customer_company,'') AS customer_company,
               status
        FROM outbound_orders
        ORDER BY id DESC
    """)
    if all_orders.empty:
        st.info("저장된 출고지시가 없습니다.")
        return

    filtered = all_orders.copy()
    if start_date:
        filtered = filtered[filtered["order_date"] >= str(start_date)]
    if end_date:
        filtered = filtered[filtered["order_date"] <= str(end_date)]
    if customer_term.strip():
        needle = customer_term.strip().lower()
        filtered = filtered[filtered["customer_name"].fillna("").astype(str).str.lower().str.contains(needle, regex=False)]
    if search_term.strip() and not filtered.empty:
        ids = filtered["id"].astype(int).tolist()
        matched_ids = []
        if ids:
            placeholders = ",".join(["?"] * len(ids))
            items_df = q(f"""
                SELECT DISTINCT order_id
                FROM outbound_order_items
                WHERE order_id IN ({placeholders})
                  AND product_name LIKE ?
            """, tuple(ids + [f"%{search_term.strip()}%"]))
            matched_ids = items_df["order_id"].astype(int).tolist() if not items_df.empty else []
        filtered = filtered[filtered["id"].astype(int).isin(matched_ids)]

    if filtered.empty:
        st.warning("조건에 맞는 출고지시서가 없습니다.")
        return

    total = len(filtered)
    per_page = 10
    max_page = max(1, (total + per_page - 1) // per_page)
    page_no = max(1, min(int(st.session_state.get("saved_order_page", 1)), max_page))
    st.session_state["saved_order_page"] = page_no
    orders = filtered.iloc[(page_no - 1) * per_page: page_no * per_page].copy()

    st.markdown(f"#### 출고지시서 {total}건")
    list_col, selected_col = st.columns([5, 5], gap="large")
    with list_col:
        selected_id = st.session_state.get("selected_saved_order_id")
        _render_saved_orders(orders, selected_id)
        if max_page > 1:
            nav_cols = st.columns([1, 3, 1])
            with nav_cols[0]:
                if st.button("이전", disabled=(page_no <= 1), key="page_prev", use_container_width=True):
                    st.session_state["saved_order_page"] = page_no - 1
                    st.rerun()
            with nav_cols[1]:
                st.markdown(f"<div style='text-align:center;color:#64748b;font-weight:700;margin:8px 0;'>{page_no} / {max_page}</div>", unsafe_allow_html=True)
            with nav_cols[2]:
                if st.button("다음", disabled=(page_no >= max_page), key="page_next", use_container_width=True):
                    st.session_state["saved_order_page"] = page_no + 1
                    st.rerun()

    valid_ids = set(filtered["id"].astype(int).tolist())
    order_id = st.session_state.get("selected_saved_order_id")
    if not order_id or int(order_id) not in valid_ids:
        order_id = int(orders.iloc[0]["id"])
        st.session_state["selected_saved_order_id"] = order_id

    order_row = all_orders[all_orders["id"] == int(order_id)]
    if order_row.empty:
        st.session_state.pop("selected_saved_order_id", None)
        return
    order_status = str(order_row.iloc[0]["status"] or "저장됨")

    with selected_col:
        customer_name = str(order_row.iloc[0].get("customer_name") or "-")
        st.markdown(f"### 선택된 출고지시서 #{int(order_id)} · {escape(customer_name)}")
        item_df = q("""
            SELECT id AS 품목ID, inventory_id AS 재고ID, location AS 로케이션, product_name AS 제품명,
                   lot AS LOT, exp_date AS 유통기한, qty AS 요청수량, company AS 사업장, warehouse_name AS 전산상명칭
            FROM outbound_order_items WHERE order_id=? ORDER BY id
        """, (int(order_id),))
        if item_df.empty:
            st.info("이 출고지시서에는 품목이 없습니다.")
        else:
            item_df["유통기한"] = item_df["유통기한"].apply(display_date_only)
            view_items = item_df[["로케이션", "제품명", "LOT", "유통기한", "요청수량"]]
            st.dataframe(view_items, hide_index=True, use_container_width=True)
            rows_for_download = view_items.to_dict("records")
            title_for_download = f"{customer_name} 출고지시서 #{int(order_id)}"
            d1, d2 = st.columns(2)
            with d1:
                st.download_button("선택 지시서 엑셀 다운로드", data=outbound_excel_bytes(rows_for_download, title_for_download), file_name=f"NOHTUS_출고지시서_{int(order_id)}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
            with d2:
                try:
                    st.download_button("선택 지시서 PDF 다운로드", data=outbound_pdf_bytes(rows_for_download, title_for_download), file_name=f"NOHTUS_출고지시서_{int(order_id)}.pdf", mime="application/pdf", use_container_width=True)
                except Exception as e:
                    st.warning(f"PDF 생성 실패: {e}")

        c_edit, c_cancel = st.columns(2)
        with c_edit:
            if st.button("출고지시서 수정하기", type="primary", use_container_width=True, disabled=(order_status == "취소됨")):
                st.session_state["outbound_cart"] = load_outbound_order(int(order_id))
                st.session_state["editing_order_id"] = int(order_id)
                st.session_state["editing_order_title"] = str(order_row.iloc[0].get("title") or "")
                st.session_state["page"] = "출고지시"
                st.rerun()
        with c_cancel:
            if st.button("출고지시 취소하기", type="primary", use_container_width=True, key=f"cancel_order_{int(order_id)}", disabled=(order_status == "취소됨")):
                st.session_state["confirm_cancel_order_id"] = int(order_id)
                st.rerun()

        if st.session_state.get("confirm_cancel_order_id") == int(order_id):
            _show_cancel_order_confirm(int(order_id))
