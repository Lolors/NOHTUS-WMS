from datetime import date
from html import escape

import streamlit as st

from nohtus.db import connect, q
from nohtus.dates import display_date_only
from nohtus.services.outbound import cancel_saved_order, load_outbound_order, outbound_excel_bytes, outbound_pdf_bytes


def _ensure_outbound_customer_columns():
    with connect() as con:
        cur = con.cursor()
        cols = {r[1] for r in cur.execute("PRAGMA table_info(outbound_orders)").fetchall()}
        if "customer_name" not in cols:
            cur.execute("ALTER TABLE outbound_orders ADD COLUMN customer_name TEXT")
        if "customer_company" not in cols:
            cur.execute("ALTER TABLE outbound_orders ADD COLUMN customer_company TEXT")
        con.commit()


def _valid_outbound_exists_sql(alias_order="o", alias_item="i"):
    return f"""
    EXISTS (
        SELECT 1
        FROM transactions t
        WHERE substr(t.created_at,1,10)={alias_order}.order_date
          AND t.tx_type IN ('출고지시','출고지시수정','출고')
          AND COALESCE(t.from_company,'')=COALESCE({alias_item}.company,'')
          AND t.product_name={alias_item}.product_name
          AND COALESCE(t.lot,'-')=COALESCE({alias_item}.lot,'-')
          AND COALESCE(t.exp_date,'-')=COALESCE({alias_item}.exp_date,'-')
          AND COALESCE(t.from_location,'')=COALESCE({alias_item}.location,'')
          AND CAST(t.qty AS INTEGER)=CAST({alias_item}.qty AS INTEGER)
          AND COALESCE(t.memo,'') LIKE '%' || '출고지시서 #' || CAST({alias_order}.id AS TEXT) || '%'
    )
    """


def _order_items_summary(order_id, max_items=3):
    df = q(
        f"""
        SELECT i.product_name, SUM(i.qty) AS qty
        FROM outbound_order_items i
        JOIN outbound_orders o ON o.id=i.order_id
        WHERE i.order_id=?
          AND {_valid_outbound_exists_sql('o', 'i')}
        GROUP BY i.product_name
        ORDER BY MIN(i.id)
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


def _status_text_html(status):
    status = str(status or "저장됨")
    if status == "취소됨":
        return "<span style='color:#dc2626;font-weight:800;'>취소됨</span>"
    if status == "수정됨":
        return "<span style='color:#16a34a;font-weight:800;'>수정됨</span>"
    return "<span style='color:#2563eb;font-weight:800;'>저장됨</span>"


def _md_link(text, oid):
    safe = str(text or "-").replace("[", "\\[").replace("]", "\\]")
    return f"[{safe}](?saved_order_id={int(oid)}#selected-outbound-detail)"


def _render_saved_orders(orders_df, selected_order_id):
    st.markdown(
        """
        <style>
        .saved-order-head{display:grid;grid-template-columns:.65fr .9fr 1.7fr 4.5fr .9fr;gap:8px;align-items:center;padding:8px 10px;border-bottom:1px solid #e5e7eb;color:#64748b;font-size:13px;font-weight:800;}
        .saved-order-cell{height:31px;display:flex;align-items:center;color:#111827;font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
        .saved-order-status{justify-content:center;}
        .saved-order-selected{background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;padding:7px 10px;margin:2px 0;color:#111827;font-size:14px;}
        .saved-order-selected-grid{display:grid;grid-template-columns:.65fr .9fr 1.7fr 4.5fr .9fr;gap:8px;align-items:center;}
        .saved-order-sep{height:1px;background:#f1f5f9;margin:3px 0 5px;}
        div[data-testid="stMarkdownContainer"] a{color:#111827;text-decoration:none;}
        div[data-testid="stMarkdownContainer"] a:hover{text-decoration:underline;text-underline-offset:3px;background:#f8fafc;}
        </style>
        <div class='saved-order-head'>
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
        items_text = _order_items_summary(oid)
        selected = int(selected_order_id or 0) == oid
        if selected:
            st.markdown(
                f"""
                <div class='saved-order-selected'>
                  <div class='saved-order-selected-grid'>
                    <div>#{oid}</div>
                    <div>{escape(created)}</div>
                    <div title='{escape(customer)}'>{escape(customer)}</div>
                    <div title='{escape(items_text)}'>{escape(items_text)}</div>
                    <div style='text-align:center;'>{_status_text_html(status)}</div>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            cols = st.columns([0.65, 0.9, 1.7, 4.5, 0.9], gap="small")
            with cols[0]:
                st.markdown(_md_link(f"#{oid}", oid))
            with cols[1]:
                st.markdown(_md_link(created, oid))
            with cols[2]:
                st.markdown(_md_link(customer, oid))
            with cols[3]:
                st.markdown(_md_link(items_text, oid))
            with cols[4]:
                st.markdown(f"<div class='saved-order-cell saved-order-status'>{_status_text_html(status)}</div>", unsafe_allow_html=True)
        st.markdown("<div class='saved-order-sep'></div>", unsafe_allow_html=True)


def _cancel_order(order_id):
    item_count, restored_count = cancel_saved_order(int(order_id))
    st.session_state.pop("confirm_cancel_order_id", None)
    st.session_state.pop("selected_saved_order_id", None)
    st.session_state["cancel_order_done_msg"] = f"출고지시서 #{int(order_id)} 취소 완료: {item_count}개 품목 / 원복 {restored_count}건"


def _prepare_edit_customer_session(order_row):
    customer_name = str(order_row.get("customer_name") or "").strip()
    customer_company = str(order_row.get("customer_company") or "").strip()
    if not customer_name:
        title = str(order_row.get("title") or "").strip()
        customer_name = title.split(" - ", 1)[0].strip() if title else ""
    for key in ["out_customer_term", "out_customer_select", "_out_customer_label", "out_selected_customer", "out_customer_direct", "out_customer_manual_name"]:
        st.session_state.pop(key, None)
    if customer_name:
        st.session_state["out_customer_term"] = customer_name
        st.session_state["out_selected_customer"] = {"customer_name": customer_name, "company": customer_company}
        st.session_state["out_customer_direct"] = False
        st.session_state["out_customer_manual_name"] = customer_name


def _query_selected_order_id():
    try:
        value = st.query_params.get("saved_order_id", "")
        if isinstance(value, list):
            value = value[0] if value else ""
        return int(value) if str(value).strip().isdigit() else None
    except Exception:
        return None


def page_saved_outbound():
    _ensure_outbound_customer_columns()
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

    all_orders = q(
        f"""
        SELECT DISTINCT o.id, o.created_at, o.order_date, COALESCE(o.title,'') AS title,
               COALESCE(o.customer_name,'') AS customer_name,
               COALESCE(o.customer_company,'') AS customer_company,
               o.status
        FROM outbound_orders o
        JOIN outbound_order_items i ON o.id=i.order_id
        WHERE IFNULL(o.status,'')<>'취소됨'
          AND {_valid_outbound_exists_sql('o', 'i')}
        ORDER BY o.id DESC
        """
    )
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
        if ids:
            placeholders = ",".join(["?"] * len(ids))
            items_df = q(
                f"""
                SELECT DISTINCT i.order_id
                FROM outbound_order_items i
                JOIN outbound_orders o ON o.id=i.order_id
                WHERE i.order_id IN ({placeholders})
                  AND i.product_name LIKE ?
                  AND {_valid_outbound_exists_sql('o', 'i')}
                """,
                tuple(ids + [f"%{search_term.strip()}%"]),
            )
            matched_ids = items_df["order_id"].astype(int).tolist() if not items_df.empty else []
            filtered = filtered[filtered["id"].astype(int).isin(matched_ids)]

    if filtered.empty:
        st.warning("조건에 맞는 출고지시서가 없습니다.")
        return

    query_order_id = _query_selected_order_id()
    if query_order_id and query_order_id in set(filtered["id"].astype(int).tolist()):
        st.session_state["selected_saved_order_id"] = int(query_order_id)

    total = len(filtered)
    per_page = 10
    max_page = max(1, (total + per_page - 1) // per_page)
    page_no = max(1, min(int(st.session_state.get("saved_order_page", 1)), max_page))
    st.session_state["saved_order_page"] = page_no
    orders = filtered.iloc[(page_no - 1) * per_page: page_no * per_page].copy()

    valid_ids = set(filtered["id"].astype(int).tolist())
    order_id = st.session_state.get("selected_saved_order_id")
    if not order_id or int(order_id) not in valid_ids:
        order_id = int(orders.iloc[0]["id"])
        st.session_state["selected_saved_order_id"] = order_id

    st.markdown(f"#### 출고지시서 {total}건")
    list_col, _ = st.columns([7, 3], gap="large")
    with list_col:
        _render_saved_orders(orders, order_id)
        if max_page > 1:
            p1, p2, p3 = st.columns([1, 3, 1])
            with p1:
                if st.button("이전", disabled=(page_no <= 1), key="page_prev", use_container_width=True):
                    st.session_state["saved_order_page"] = page_no - 1
                    st.rerun()
            with p2:
                st.markdown(f"<div style='text-align:center;color:#64748b;font-weight:700;margin:8px 0;'>{page_no} / {max_page}</div>", unsafe_allow_html=True)
            with p3:
                if st.button("다음", disabled=(page_no >= max_page), key="page_next", use_container_width=True):
                    st.session_state["saved_order_page"] = page_no + 1
                    st.rerun()

    order_row = all_orders[all_orders["id"] == int(order_id)]
    if order_row.empty:
        st.session_state.pop("selected_saved_order_id", None)
        return

    order_status = str(order_row.iloc[0]["status"] or "저장됨")
    customer_name = str(order_row.iloc[0].get("customer_name") or "-")

    st.markdown("<div id='selected-outbound-detail'></div>", unsafe_allow_html=True)
    st.markdown("---")
    selected_col, _spacer = st.columns([7, 3], gap="large")
    with selected_col:
        st.markdown(f"### 선택된 출고지시서 #{int(order_id)} · {escape(customer_name)}")
        item_df = q(
            f"""
            SELECT i.id AS 품목ID, i.inventory_id AS 재고ID, i.location AS 로케이션, i.product_name AS 제품명,
                   i.lot AS LOT, i.exp_date AS 유통기한, i.qty AS 요청수량, i.company AS 사업장, i.warehouse_name AS 전산상명칭
            FROM outbound_order_items i
            JOIN outbound_orders o ON o.id=i.order_id
            WHERE i.order_id=?
              AND {_valid_outbound_exists_sql('o', 'i')}
            ORDER BY i.id
            """,
            (int(order_id),),
        )
        if item_df.empty:
            st.info("이 출고지시서에는 유효한 품목이 없습니다.")
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
                        _cancel_order(int(order_id))
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))
