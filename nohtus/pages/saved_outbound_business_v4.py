from __future__ import annotations

from datetime import date
from html import escape

import streamlit as st
import streamlit.components.v1 as components

import nohtus.pages.saved_outbound_business_v2 as saved_v2
from nohtus.dates import display_date_only
from nohtus.services.outbound import load_outbound_order, outbound_excel_bytes, outbound_pdf_bytes


BUTTON_W = 48
BUTTON_H = 28
ROW_H = 46
PER_PAGE = 10


def _order_has_history_sql(alias_order="o"):
    return f"""
    EXISTS (
        SELECT 1
        FROM transactions t
        WHERE t.tx_type IN ('출고지시','출고지시수정','출고')
          AND COALESCE(t.memo,'') LIKE '%' || '출고지시서 #' || CAST({alias_order}.id AS TEXT) || '%'
    )
    """


def _status_text_html(status):
    status = str(status or "저장됨")
    if status == "취소됨":
        return "<span style='color:#dc2626;font-weight:800;'>취소됨</span>"
    if status == "수정됨":
        return "<span style='color:#16a34a;font-weight:800;'>수정됨</span>"
    return "<span style='color:#2563eb;font-weight:800;'>저장됨</span>"


def _selected_number_chip(label):
    return f"<span class='saved-order-no-chip selected'>{escape(str(label))}</span>"


def _cell(content, *, title="", class_name=""):
    title_attr = f" title='{escape(str(title))}'" if title else ""
    return f"<div class='saved-order-cell {class_name}'{title_attr}>{content}</div>"


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


def _order_items_summary(order_id, max_items=3):
    df = saved_v2.q(
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


def _load_orders():
    return saved_v2.q(
        f"""
        SELECT DISTINCT o.id, o.created_at, o.order_date, COALESCE(o.title,'') AS title,
               COALESCE(o.customer_name,'') AS customer_name,
               COALESCE(o.customer_company,'') AS customer_company,
               o.status
        FROM outbound_orders o
        JOIN outbound_order_items i ON o.id=i.order_id
        WHERE IFNULL(o.status,'')<>'취소됨'
          AND {_order_has_history_sql('o')}
        ORDER BY o.id DESC
        """
    )


def _attach_daily_sequence(df):
    if df.empty:
        return df
    result = df.copy()
    seq_source = result.sort_values(["order_date", "created_at", "id"], ascending=[True, True, True]).copy()
    seq_source["daily_no"] = seq_source.groupby("order_date").cumcount() + 1
    seq_map = dict(zip(seq_source["id"].astype(int), seq_source["daily_no"].astype(int)))
    result["daily_no"] = result["id"].astype(int).map(seq_map).fillna(0).astype(int)
    result["display_no"] = result["daily_no"].astype(str)
    return result


def _filter_orders(all_orders, start_date, end_date, customer_term, search_term):
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
        if ids:
            placeholders = ",".join(["?"] * len(ids))
            items_df = saved_v2.q(
                f"""
                SELECT DISTINCT order_id
                FROM outbound_order_items
                WHERE order_id IN ({placeholders})
                  AND product_name LIKE ?
                """,
                tuple(ids + [f"%{search_term.strip()}%"]),
            )
            matched_ids = items_df["order_id"].astype(int).tolist() if not items_df.empty else []
            filtered = filtered[filtered["id"].astype(int).isin(matched_ids)]
    return filtered


def _render_saved_orders(orders_df, selected_order_id):
    st.markdown(
        f"""
        <style>
        .saved-order-head-clean{{display:grid;grid-template-columns:.65fr .9fr 1.7fr 4.5fr .9fr;gap:8px;align-items:center;padding:8px 10px;border-bottom:1px solid #e5e7eb;color:#64748b;font-size:13px;font-weight:800;}}
        .saved-order-cell{{height:{ROW_H}px;display:flex;align-items:center;min-width:0;color:#111827;font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;line-height:1.2;}}
        .saved-order-status{{justify-content:center;text-align:center;}}
        .saved-order-sep{{height:1px;background:#f6f7f9;margin:1px 0 3px;}}
        .saved-order-no-chip{{display:inline-flex;align-items:center;justify-content:center;width:{BUTTON_W}px;min-width:{BUTTON_W}px;max-width:{BUTTON_W}px;height:{BUTTON_H}px;min-height:{BUTTON_H}px;max-height:{BUTTON_H}px;padding:0;border:1px solid #d1d5db;background:#fff;color:#334155;border-radius:6px;font-size:13px;font-weight:500;box-sizing:border-box;line-height:1;}}
        .saved-order-no-chip.selected{{border-color:#93c5fd;background:#dbeafe;color:#1d4ed8;font-weight:700;}}
        </style>
        <div class='saved-order-head-clean'>
          <div>번호</div><div>날짜</div><div>매출처</div><div>포함된 출고 제품</div><div style='text-align:center;'>상태</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    for r in orders_df.itertuples(index=False):
        oid = int(getattr(r, "id"))
        created = str(getattr(r, "order_date", "") or getattr(r, "created_at", ""))[:10]
        customer = str(getattr(r, "customer_name", "") or "-")
        status = str(getattr(r, "status", "저장됨") or "저장됨")
        display_no = str(getattr(r, "display_no", "") or getattr(r, "daily_no", "") or oid)
        items_text = _order_items_summary(oid)
        selected = int(selected_order_id or 0) == oid
        cols = st.columns([0.65, 0.9, 1.7, 4.5, 0.9], gap="small")
        with cols[0]:
            if selected:
                st.markdown(_cell(_selected_number_chip(display_no)), unsafe_allow_html=True)
            else:
                if st.button(display_no, key=f"open_order_no_{oid}", use_container_width=False, type="secondary"):
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


def _render_page_input(current_page, total_pages):
    if total_pages <= 1:
        return current_page
    st.markdown(
        """
        <style>
        div[data-testid="stNumberInput"]{width:138px!important;margin:10px auto 2px auto!important;overflow:visible!important;}
        div[data-testid="stNumberInput"] input{height:54px!important;min-height:54px!important;text-align:center!important;font-size:16px!important;}
        div[data-testid="stNumberInput"] button{display:flex!important;visibility:visible!important;opacity:1!important;width:32px!important;min-width:32px!important;height:27px!important;min-height:27px!important;padding:0!important;}
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
    return int(selected_page)


def _prepare_edit_customer_session(order_row):
    return saved_v2._prepare_edit_customer_session(order_row)


def _order_display_label(order_row):
    order_date = str(order_row.get("order_date") or "")[:10]
    daily_no = int(order_row.get("daily_no") or 0)
    if order_date and daily_no:
        return f"{order_date} / {daily_no}번"
    return f"출고지시서 #{int(order_row.get('id'))}"


def page_saved_outbound():
    saved_v2._ensure_outbound_customer_columns()
    st.markdown("<h1 style='text-align:left;margin-bottom:0.2em;'>저장된 출고지시</h1>", unsafe_allow_html=True)
    if st.session_state.get("cancel_order_done_msg"):
        st.success(st.session_state.pop("cancel_order_done_msg"))
    st.caption("날짜, 매출처, 제품 검색으로 출고지시서를 필터링합니다.")

    today = date.today()
    filter_outer, _blank = st.columns([7, 3], gap="large")
    with filter_outer:
        f1, f2, f3, f4 = st.columns([1.5, 1.5, 3, 4], gap="small")
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

    all_orders = _attach_daily_sequence(_load_orders())
    if all_orders.empty:
        st.info("저장된 출고지시가 없습니다.")
        return

    filtered = _filter_orders(all_orders, start_date, end_date, customer_term, search_term)
    if filtered.empty:
        st.warning("조건에 맞는 출고지시서가 없습니다.")
        return

    total = len(filtered)
    total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    page_no = max(1, min(int(st.session_state.get("saved_order_page", 1) or 1), total_pages))
    st.session_state["saved_order_page"] = page_no
    orders = filtered.iloc[(page_no - 1) * PER_PAGE: page_no * PER_PAGE].copy()

    valid_ids = set(filtered["id"].astype(int).tolist())
    order_id = st.session_state.get("selected_saved_order_id")
    if not order_id or int(order_id) not in valid_ids:
        order_id = int(orders.iloc[0]["id"])
        st.session_state["selected_saved_order_id"] = order_id

    st.markdown(f"#### 출고지시서 {total}건")
    list_col, _ = st.columns([7, 3], gap="large")
    with list_col:
        _render_saved_orders(orders, order_id)
        selected_page = _render_page_input(page_no, total_pages)
        if selected_page != page_no:
            st.session_state["saved_order_page"] = selected_page
            st.rerun()

    order_row = all_orders[all_orders["id"] == int(order_id)]
    if order_row.empty:
        st.session_state.pop("selected_saved_order_id", None)
        return

    order_status = str(order_row.iloc[0]["status"] or "저장됨")
    customer_name = str(order_row.iloc[0].get("customer_name") or "-")
    display_label = _order_display_label(order_row.iloc[0])

    st.markdown("<div id='selected-outbound-detail'></div>", unsafe_allow_html=True)
    st.markdown("---")
    selected_col, _spacer = st.columns([7, 3], gap="large")
    with selected_col:
        st.markdown(f"### 선택된 출고지시서 {escape(display_label)} · {escape(customer_name)}")
        item_df = saved_v2.q(
            f"""
            SELECT i.id AS 품목ID, i.inventory_id AS 재고ID, i.location AS 로케이션, i.product_name AS 제품명,
                   i.lot AS LOT, i.exp_date AS 유통기한, i.qty AS 요청수량, i.company AS 사업장, i.warehouse_name AS 전산상명칭
            FROM outbound_order_items i
            JOIN outbound_orders o ON o.id=i.order_id
            WHERE i.order_id=?
              AND {saved_v2._valid_outbound_exists_sql('o', 'i')}
            ORDER BY i.id
            """,
            (int(order_id),),
        )
        if item_df.empty:
            st.info("이 출고지시서에는 유효한 품목이 없습니다.")
        else:
            item_df["유통기한"] = item_df["유통기한"].apply(display_date_only)
            view_items = item_df[["사업장", "로케이션", "제품명", "LOT", "유통기한", "요청수량"]]
            st.dataframe(view_items, hide_index=True, use_container_width=True)
            rows_for_download = view_items.to_dict("records")
            title_for_download = f"{customer_name} 출고지시서 {display_label}"
            d1, d2 = st.columns(2)
            with d1:
                st.download_button("선택 지시서 엑셀 다운로드", data=outbound_excel_bytes(rows_for_download, title_for_download), file_name=f"NOHTUS_출고지시서_{int(order_id)}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
            with d2:
                try:
                    st.download_button("선택 지시서 PDF 다운로드", data=outbound_pdf_bytes(rows_for_download, title_for_download), file_name=f"NOHTUS_출고지시서_{int(order_id)}.pdf", mime="application/pdf", use_container_width=True)
                except Exception as e:
                    st.warning(f"PDF 생성 실패: {e}")

        e1, e2 = st.columns(2)
        with e1:
            if st.button("출고지시서 수정하기", type="primary", use_container_width=True, disabled=(order_status == "취소됨")):
                st.session_state["outbound_cart"] = load_outbound_order(int(order_id))
                st.session_state["editing_order_id"] = int(order_id)
                st.session_state["editing_order_title"] = str(order_row.iloc[0].get("title") or "")
                _prepare_edit_customer_session(order_row.iloc[0])
                st.session_state["page"] = "출고지시"
                st.rerun()
        with e2:
            if st.button("출고지시 취소하기", type="primary", use_container_width=True, key=f"cancel_order_{int(order_id)}", disabled=(order_status == "취소됨")):
                st.session_state["confirm_cancel_order_id"] = int(order_id)
                st.rerun()

        if st.session_state.get("confirm_cancel_order_id") == int(order_id):
            st.warning("정말로 취소하시겠습니까? 제품의 수량은 출고지시 이전으로 복원됩니다.")
            c1, c2, _ = st.columns([1, 1.6, 5])
            with c1:
                if st.button("아니오", use_container_width=True, key=f"cancel_no_{int(order_id)}"):
                    st.session_state.pop("confirm_cancel_order_id", None)
                    st.rerun()
            with c2:
                if st.button("예, 취소합니다", type="primary", use_container_width=True, key=f"cancel_yes_{int(order_id)}"):
                    try:
                        saved_v2._cancel_order(int(order_id))
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))
    _scroll_selected_detail_once()
