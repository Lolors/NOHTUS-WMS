from datetime import datetime
from html import escape

import streamlit as st

from nohtus.db import q
from nohtus.services.outbound_orders import save_outbound_order, update_outbound_order
from nohtus.services.outbound_runtime import (
    cancel_saved_order, load_outbound_order, outbound_excel_bytes, outbound_pdf_bytes,
)


def _save_outbound_cart_action(cart, title):
    """장바구니 출고지시 저장/수정 공통 처리."""
    if st.session_state.get("editing_order_id"):
        update_outbound_order(st.session_state["editing_order_id"], title, cart)
        msg = f"출고지시서 #{st.session_state['editing_order_id']} 수정 저장 완료"
        st.session_state.pop("editing_order_id", None)
        st.session_state.pop("editing_order_title", None)
    else:
        oid = save_outbound_order(cart, title)
        msg = f"출고지시서 #{oid} 저장 완료"
    st.session_state["outbound_cart"] = []
    st.session_state["_outbound_reset_inputs_pending"] = True
    st.session_state["_outbound_last_success"] = msg
    st.rerun()

def _status_text_html(status):
    status = str(status or "저장됨")
    color = "#475569"
    if status == "취소됨":
        color = "#dc2626"
    elif status == "수정됨":
        color = "#65a30d"
    return f"<span style='font-weight:400;color:{color};'>{escape(status)}</span>"


def render_saved_orders(orders_df, selected_order_id=None):
    """저장된 출고지시서를 1컬럼 표 형태로 렌더링하고 선택된 id를 반환한다."""
    if orders_df is None or orders_df.empty:
        st.info("저장된 출고지시가 없습니다.")
        return None

    st.markdown("""
    <style>
    .saved-order-table{width:100%;border:1px solid #dbe4f0;border-radius:14px;overflow:hidden;background:#fff;margin-top:4px;}
    .saved-order-head{display:grid;grid-template-columns:78px 120px minmax(360px,1fr) 90px;gap:0;align-items:center;background:#f1f5f9;color:#334155;font-weight:800;border-bottom:1px solid #dbe4f0;}
    .saved-order-head>div{padding:10px 12px;font-size:13px;}
    .saved-order-row{display:grid;grid-template-columns:78px 120px minmax(360px,1fr) 90px;gap:0;align-items:center;border-bottom:1px solid #edf2f7;min-height:42px;}
    .saved-order-row:last-child{border-bottom:none;}
    .saved-order-cell{padding:9px 12px;font-size:13px;color:#111827;font-weight:400;min-width:0;}
    .saved-order-title{text-align:left;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
    .saved-order-date{color:#334155;}
    .saved-order-status{text-align:center;}
    div[data-testid="stButton"] > button.saved-order-num-btn{justify-content:center!important;text-align:center!important;}
    </style>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class='saved-order-table'>
      <div class='saved-order-head'>
        <div style='text-align:center;'>번호</div>
        <div>날짜</div>
        <div style='text-align:left;'>제목</div>
        <div style='text-align:center;'>상태</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    for r in orders_df.itertuples():
        oid = int(r.id)
        title = str(r.title or "-")
        created = str(r.created_at or "")[:10]
        status = str(r.status or "저장됨")
        row_cols = st.columns([0.78, 1.2, 5.2, 0.9], gap="small")
        with row_cols[0]:
            if st.button(f"#{oid}", key=f"open_order_{oid}", use_container_width=True, type=("primary" if int(selected_order_id or 0) == oid else "secondary")):
                st.session_state["selected_saved_order_id"] = oid
                st.rerun()
        with row_cols[1]:
            st.markdown(f"<div class='saved-order-cell saved-order-date'>{escape(created)}</div>", unsafe_allow_html=True)
        with row_cols[2]:
            st.markdown(f"<div class='saved-order-cell saved-order-title' title='{escape(title)}'>{escape(title)}</div>", unsafe_allow_html=True)
        with row_cols[3]:
            st.markdown(f"<div class='saved-order-cell saved-order-status'>{_status_text_html(status)}</div>", unsafe_allow_html=True)
    return st.session_state.get("selected_saved_order_id") or (int(orders_df.iloc[0]["id"]) if not orders_df.empty else None)


def _run_cancel_order(order_id):
    """출고지시 취소 실행 후 상태 정리."""
    item_count, restored_count = cancel_saved_order(int(order_id))
    st.session_state.pop("confirm_cancel_order_id", None)
    st.session_state.pop("selected_saved_order_id", None)
    st.session_state["cancel_order_done_msg"] = f"출고지시서 #{int(order_id)} 취소 완료: {item_count}개 품목 / 원복 {restored_count}건"


def _show_cancel_order_confirm_inline(order_id):
    """Streamlit 버전이 낮아 dialog API가 없을 때만 쓰는 예비 확인 카드.
    실제 모달은 st.dialog/st.experimental_dialog를 우선 사용한다.
    """
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


_dialog_api = getattr(st, "dialog", None) or getattr(st, "experimental_dialog", None)

if _dialog_api:
    @_dialog_api("⚠ 출고지시 취소 확인")
    def _show_cancel_order_confirm(order_id):
        """화면 중앙 모달에서 출고지시 취소 여부를 확인한다.
        제목은 dialog 타이틀만 굵게 두고, 본문은 일반 굵기로 둔다.
        """
        st.markdown("""
        <style>
        div[data-testid="stDialog"] div[data-testid="stMarkdownContainer"] p,
        div[data-testid="stDialog"] div[data-testid="stMarkdownContainer"] div {
            font-weight:400!important;
        }
        div[data-testid="stDialog"] div[data-testid="stHorizontalBlock"]{
            justify-content:center!important;
        }
        div[data-testid="stDialog"] div[data-testid="stButton"] > button{
            min-height:46px!important;
            min-width:180px!important;
            border-radius:10px!important;
            font-weight:800!important;
            white-space:nowrap!important;
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
else:
    def _show_cancel_order_confirm(order_id):
        _show_cancel_order_confirm_inline(order_id)



def page_saved_outbound():
    st.markdown("<h1 style='text-align:left;margin-bottom:0.2em;'>저장된 출고지시</h1>", unsafe_allow_html=True)
    if st.session_state.get("cancel_order_done_msg"):
        st.success(st.session_state.pop("cancel_order_done_msg"))
    st.caption("날짜 범위와 제목 검색으로 출고지시서를 필터링합니다.")
    st.markdown("""
    <style>
    section[data-testid="stSidebar"] div[data-testid="stButton"] > button,
    section[data-testid="stSidebar"] div[data-testid="stButton"] > button[kind="primary"],
    section[data-testid="stSidebar"] div[data-testid="stButton"] > button[kind="secondary"] {
        text-align:left!important; justify-content:flex-start!important;
    }
    section[data-testid="stSidebar"] div[data-testid="stButton"] > button p {text-align:left!important;width:100%!important;}
    </style>
    """, unsafe_allow_html=True)

    use_date_range = st.checkbox("날짜 범위 사용", value=False, key="saved_use_date_range")
    f1, f2, f3 = st.columns([1, 1, 2], gap="large")
    with f1:
        start_date = st.date_input("시작일", value=st.session_state.get("saved_start_date", datetime.now().date()), disabled=not use_date_range, key="saved_start_date")
    with f2:
        end_date = st.date_input("종료일", value=st.session_state.get("saved_end_date", datetime.now().date()), disabled=not use_date_range, key="saved_end_date")
    with f3:
        search_term = st.text_input("검색", placeholder="저장된 제목 일부 입력", key="saved_outbound_search")

    all_orders = q("SELECT id, created_at, order_date, title, status FROM outbound_orders ORDER BY id DESC")
    if all_orders.empty:
        st.info("저장된 출고지시가 없습니다.")
        return

    filtered = all_orders.copy()
    if use_date_range:
        if start_date and end_date and start_date > end_date:
            st.error("시작일은 종료일보다 늦을 수 없습니다.")
            return
        if start_date:
            filtered = filtered[filtered["order_date"] >= str(start_date)]
        if end_date:
            filtered = filtered[filtered["order_date"] <= str(end_date)]
    if search_term.strip():
        term = search_term.strip().lower()
        filtered = filtered[filtered["title"].fillna("").str.lower().str.contains(term, regex=False)]
    if filtered.empty:
        st.warning("조건에 맞는 출고지시서가 없습니다.")
        return

    total = len(filtered)
    per_page = 15
    max_page = max(1, (total + per_page - 1) // per_page)
    page_no = max(1, min(int(st.session_state.get("saved_order_page", 1)), max_page))
    st.session_state["saved_order_page"] = page_no
    orders = filtered.iloc[(page_no - 1) * per_page: page_no * per_page].copy()

    st.markdown(f"#### 출고지시서 {total}건")
    list_col, _ = st.columns([7, 3], gap="large")
    with list_col:
        selected_id = st.session_state.get("selected_saved_order_id")
        selected_id = render_saved_orders(orders, selected_id)
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

    st.markdown("---")
    selected_col, _spacer = st.columns([7, 3], gap="large")
    with selected_col:
        st.markdown(f"### 선택된 출고지시서 #{int(order_id)}")
        item_df = q("""
            SELECT id AS 품목ID, inventory_id AS 재고ID, location AS 로케이션, product_name AS 제품명,
                   lot AS LOT, exp_date AS 유통기한, qty AS 요청수량, company AS 사업장, warehouse_name AS 전산상명칭
            FROM outbound_order_items WHERE order_id=? ORDER BY id
        """, (int(order_id),))
        if item_df.empty:
            st.info("이 출고지시서에는 품목이 없습니다.")
        else:
            view_items = item_df[["로케이션", "제품명", "LOT", "유통기한", "요청수량"]]
            st.dataframe(view_items, hide_index=True, use_container_width=True)
            rows_for_download = view_items.to_dict("records")
            title_for_download = str(order_row.iloc[0]["title"] or f"출고지시서 #{int(order_id)}")
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
                st.session_state["editing_order_title"] = str(order_row.iloc[0]["title"] or "")
                st.session_state["page"] = "출고지시"
                st.rerun()
        with c_cancel:
            if st.button("출고지시 취소하기", type="primary", use_container_width=True, key=f"cancel_order_{int(order_id)}", disabled=(order_status == "취소됨")):
                st.session_state["confirm_cancel_order_id"] = int(order_id)
                st.rerun()

        if st.session_state.get("confirm_cancel_order_id") == int(order_id):
            _show_cancel_order_confirm(int(order_id))
