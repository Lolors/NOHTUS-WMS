"""Outbound page for NOHTUS WMS.

Migrated from app.py. This module intentionally imports Streamlit because it
contains page rendering code.
"""

from __future__ import annotations

from nohtus.services.outbound_orders import save_outbound_order, update_outbound_order
from nohtus.services.outbound_cart import _add_rows_to_outbound_cart, _cart_expiry_warnings, _clear_outbound_inputs_before_render, get_cart
from nohtus.services.outbound import build_outbound_order_title, outbound_excel_bytes, outbound_pdf_bytes, recommend_picks
from datetime import date, datetime

import pandas as pd
import streamlit as st

from nohtus.services.products import product_options
from nohtus.config import COMPANIES
from nohtus.db import connect, q
from nohtus.dates import display_date_only


def _safe_int(value, default=0):
    try:
        return int(value or 0)
    except Exception:
        return default


def _normalize_product_options(raw_options):
    """제품 옵션 반환값을 표준제품명 문자열 목록으로 정규화한다."""
    if raw_options is None:
        return []
    if isinstance(raw_options, pd.DataFrame):
        if raw_options.empty:
            return []
        column = "standard_name" if "standard_name" in raw_options.columns else raw_options.columns[0]
        values = raw_options[column].tolist()
    elif isinstance(raw_options, pd.Series):
        values = raw_options.tolist()
    else:
        try:
            values = list(raw_options)
        except TypeError:
            values = [raw_options]
    result = []
    seen = set()
    for value in values:
        if pd.isna(value):
            continue
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _ensure_outbound_customer_columns():
    """출고지시서에 매출처 정보를 보존하기 위한 컬럼을 자동 보강한다."""
    with connect() as con:
        cur = con.cursor()
        cols = {r[1] for r in cur.execute("PRAGMA table_info(outbound_orders)").fetchall()}
        if "customer_name" not in cols:
            cur.execute("ALTER TABLE outbound_orders ADD COLUMN customer_name TEXT")
        if "customer_company" not in cols:
            cur.execute("ALTER TABLE outbound_orders ADD COLUMN customer_company TEXT")
        con.commit()


def _ensure_customer_last_sales_table():
    """거래처별 최근거래일 저장 테이블을 자동 보강한다."""
    with connect() as con:
        cur = con.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS customer_last_sales(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_name TEXT NOT NULL,
                company TEXT NOT NULL DEFAULT '',
                last_sale_date TEXT NOT NULL,
                source_company TEXT,
                updated_at TEXT,
                UNIQUE(customer_name, company)
            )
            """
        )
        con.commit()


def _stored_customer_for_editing_order():
    order_id = st.session_state.get("editing_order_id")
    if not order_id:
        return {}
    _ensure_outbound_customer_columns()
    df = q("SELECT customer_name, customer_company FROM outbound_orders WHERE id=?", (int(order_id),))
    if df.empty:
        return {}
    row = df.iloc[0]
    return {"customer_name": str(row.get("customer_name") or "").strip(), "company": str(row.get("customer_company") or "").strip()}


def _prefill_customer_from_saved_order():
    if st.session_state.get("_outbound_customer_prefilled"):
        return
    customer = _stored_customer_for_editing_order()
    if customer:
        st.session_state["out_selected_customer"] = customer
        st.session_state["out_customer_term"] = customer.get("customer_name", "")
    st.session_state["_outbound_customer_prefilled"] = True


def _save_outbound_customer(order_id, customer_payload):
    _ensure_outbound_customer_columns()
    with connect() as con:
        con.execute(
            "UPDATE outbound_orders SET customer_name=?, customer_company=? WHERE id=?",
            (str((customer_payload or {}).get("customer_name") or "").strip(), str((customer_payload or {}).get("company") or "").strip(), int(order_id)),
        )
        con.commit()


def _current_customer_payload(selected_customer):
    selected_customer = selected_customer or st.session_state.get("out_selected_customer") or {}
    return {"customer_name": str(selected_customer.get("customer_name") or "").strip(), "company": str(selected_customer.get("company") or "").strip()}


def _save_outbound_cart_with_customer(cart, title, customer_payload):
    editing_id = st.session_state.get("editing_order_id")
    if editing_id:
        update_outbound_order(int(editing_id), title, cart)
        _save_outbound_customer(int(editing_id), customer_payload)
        oid = int(editing_id)
    else:
        oid = int(save_outbound_order(cart, title))
        _save_outbound_customer(oid, customer_payload)
    st.session_state["outbound_cart"] = []
    st.session_state.pop("editing_order_id", None)
    st.session_state.pop("editing_order_title", None)
    st.session_state["_outbound_last_success"] = f"출고지시서 #{oid} 저장 완료"
    st.rerun()


def _render_last_sale_importer():
    return None


def _customer_last_sale_maps():
    _ensure_customer_last_sales_table()
    df = q("SELECT customer_name, company, last_sale_date FROM customer_last_sales")
    exact_map, name_map = {}, {}
    if not df.empty:
        for _, row in df.iterrows():
            name = str(row.get("customer_name") or "").strip()
            company = str(row.get("company") or "").strip()
            dt = str(row.get("last_sale_date") or "").strip()
            if not name:
                continue
            exact_map[(name, company)] = dt
            name_map[name] = max(name_map.get(name, ""), dt)
    return exact_map, name_map


def _days_ago_label(date_text):
    text = str(date_text or "").strip()
    if not text or text == "-":
        return ""
    parsed = None
    for fmt in ("%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d", "%Y%m%d"):
        try:
            parsed = datetime.strptime(text[:10] if fmt != "%Y%m%d" else text[:8], fmt).date()
            break
        except (TypeError, ValueError):
            continue
    if parsed is None:
        try:
            parsed = pd.to_datetime(text, errors="raise").date()
        except Exception:
            return ""
    days = (date.today() - parsed).days
    if days < 0:
        return f"{abs(days)}일 후"
    if days == 0:
        return "오늘"
    return f"{days}일 전"


def _last_sale_text(customer_name, company, exact_map, name_map):
    name = str(customer_name or "").strip()
    company = str(company or "").strip()
    last_sale = exact_map.get((name, company)) or name_map.get(name) or ""
    if not last_sale:
        return "최근거래 없음"
    ago = _days_ago_label(last_sale)
    return f"최근거래 {last_sale} ({ago})" if ago else f"최근거래 {last_sale}"


def _customer_select_label(row, exact_map, name_map):
    name = str(getattr(row, "customer_name", "") or "").strip()
    company = str(getattr(row, "company", "") or "").strip()
    manager = str(getattr(row, "manager", "") or "").strip()
    parts = [name]
    if company:
        parts.append(company)
    if manager:
        parts.append(manager)
    parts.append(_last_sale_text(name, company, exact_map, name_map))
    return " | ".join(parts)


def _customer_details(customer_name, company=""):
    params = [str(customer_name or "").strip()]
    company_sql = ""
    if company:
        company_sql = " AND COALESCE(company,'')=?"
        params.append(str(company).strip())
    rows = q(f"SELECT * FROM customers WHERE TRIM(COALESCE(customer_name,''))=?{company_sql} ORDER BY id LIMIT 1", tuple(params))
    return rows


def _show_customer_detail_dialog(customer_name, company=""):
    rows = _customer_details(customer_name, company)
    st.markdown(f"### {customer_name}")
    if rows.empty:
        st.info("등록된 거래처 상세정보가 없습니다.")
        return
    row = rows.iloc[0]
    label_map = {"customer_name":"거래처명","company":"사업장","manager":"담당자","phone":"연락처","address":"주소","memo":"메모"}
    for col, value in row.items():
        text = str(value or "").strip()
        if col == "id" or not text or text.lower() == "nan":
            continue
        st.write(f"**{label_map.get(col, col)}:** {text}")


def _open_customer_detail_dialog(customer_name, company=""):
    if hasattr(st, "dialog"):
        @st.dialog("거래처 상세정보", width="large")
        def _dialog():
            _show_customer_detail_dialog(customer_name, company)
        _dialog()
    else:
        st.session_state["_show_customer_detail"] = {"customer_name": customer_name, "company": company}


def _recent_customer_outbound_rows(customer_name, company="", limit=20):
    """선택 거래처의 최근 출고지시 품목을 최신순으로 조회한다."""

    name = str(customer_name or "").strip()
    company = str(company or "").strip()
    if not name:
        return pd.DataFrame()
    params = [name, f"%{name}%"]
    company_sql = ""
    if company:
        company_sql = " AND (COALESCE(o.customer_company,'')=? OR COALESCE(i.company,'')=?)"
        params.extend([company, company])
    params.append(int(limit))
rows = q(
        f"""
        SELECT o.order_date AS 출고일,
               COALESCE(o.customer_name, '') AS 매출처,
               COALESCE(i.company, '') AS 사업장,
               COALESCE(i.product_name, '') AS 제품명,
               COALESCE(i.lot, '-') AS LOT,

               COALESCE(i.company, '') AS 사업장,
               COALESCE(i.product_name, '') AS 제품명,
               COALESCE(i.lot, '-') AS LOT,
               COALESCE(i.exp_date, '-') AS 유통기한,
               COALESCE(i.qty, 0) AS 수량,
               COALESCE(o.title, '') AS 출고지시서
        FROM outbound_orders o
        JOIN outbound_order_items i ON i.order_id=o.id
        WHERE COALESCE(o.status,'')<>'취소됨'
          AND (TRIM(COALESCE(o.customer_name,''))=? OR COALESCE(o.title,'') LIKE ?)
          {company_sql}
        ORDER BY o.order_date DESC, COALESCE(o.created_at,'') DESC, o.id DESC, i.id DESC
        LIMIT ?
        """,
        tuple(params),
    )
    if rows.empty:
        return rows
    rows["유통기한"] = rows["유통기한"].apply(display_date_only)
    rows["수량"] = pd.to_numeric(rows["수량"], errors="coerce").fillna(0).astype(int)
    return rows[["출고일", "사업장", "제품명", "LOT", "유통기한", "수량", "출고지시서"]]


def _show_recent_customer_outbound_dialog(customer_name, company=""):
    rows = _recent_customer_outbound_rows(customer_name, company)
    st.markdown(f"### {customer_name} 최근 출고 제품")
    if company:
        st.caption(f"사업장: {company}")
    if rows.empty:
        st.info("저장된 최근 출고 제품이 없습니다.")
        return
    st.dataframe(rows, hide_index=True, use_container_width=True)


def _open_recent_customer_outbound_dialog(customer_name, company=""):
    if hasattr(st, "dialog"):
        @st.dialog("최근 출고 제품", width="large")
        def _dialog():
            _show_recent_customer_outbound_dialog(customer_name, company)
        _dialog()
    else:
        st.session_state["_show_recent_customer_outbound"] = {"customer_name": customer_name, "company": company}


def _inventory_query_for_outbound(selected_product, selected_company, ignore_company=False):
    params = [selected_product]
    where = ["product_name=?", "COALESCE(qty,0)>0", "location<>'P'"]
    if not ignore_company:
        if not selected_company:
            return pd.DataFrame()
        where.append("company=?")
        params.append(selected_company)
    return q(f"SELECT id,company,product_name,warehouse_name,lot,exp_date,location,qty,COALESCE(is_shippable,1) AS is_shippable FROM inventory WHERE {' AND '.join(where)} ORDER BY company,exp_date,lot,location", tuple(params))


def _manual_pick_rows(pick_df, editor_df=None):
    if editor_df is None:
        if pick_df is None or pick_df.empty:
            return pd.DataFrame()
        rows = pick_df.copy().rename(columns={"company":"사업장","product_name":"제품명","lot":"LOT","exp_date":"유통기한","location":"로케이션","qty":"현재수량"})
        rows["유통기한"] = rows["유통기한"].apply(display_date_only)
        rows.insert(0, "선택", False)
        rows["요청수량"] = 0
        return rows[["선택", "id", "사업장", "제품명", "LOT", "유통기한", "로케이션", "현재수량", "요청수량"]]
    pending_rows = []
    if pick_df is None or pick_df.empty or editor_df is None or editor_df.empty:
        return pending_rows
    source = pick_df.reset_index(drop=True)
    edited = editor_df.reset_index(drop=True)
    for idx, row in edited.iterrows():
        checked = bool(row.get("선택", False))
        qty2 = _safe_int(row.get("요청수량"), 0)
        if not checked or qty2 <= 0 or idx >= len(source):
            continue
        src = source.iloc[idx]
        available = _safe_int(src.get("qty"), 0)
        if available <= 0:
            continue
        pending_rows.append({"id": int(src.get("id")), "로케이션": src.get("location", ""), "사업장": src.get("company", ""), "제품명": src.get("product_name", ""), "LOT": src.get("lot", "-") or "-", "유통기한": display_date_only(src.get("exp_date", "-")), "요청수량": min(qty2, available)})
    return pending_rows


def _recommended_rows(pick_df, req, expiry_short_first=True):
    if pick_df is None or pick_df.empty:
        return pd.DataFrame()
    recommended = recommend_picks(pick_df, int(req or 0), expiry_short_first=expiry_short_first)
    if recommended is None or recommended.empty:
        return pd.DataFrame()
    rows = recommended.copy().rename(columns={"company":"사업장","product_name":"제품명","lot":"LOT","exp_date":"유통기한","location":"로케이션","qty":"현재수량","pick_qty":"요청수량"})
    rows["유통기한"] = rows["유통기한"].apply(display_date_only)
    return rows[["id", "사업장", "제품명", "LOT", "유통기한", "로케이션", "현재수량", "요청수량"]]


def page_outbound():
    _ensure_outbound_customer_columns()
    _ensure_customer_last_sales_table()
    _clear_outbound_inputs_before_render()
    _prefill_customer_from_saved_order()

    st.title("출고지시")
    st.caption("출고지시 저장 시 해당 제조번호/유통기한/로케이션의 현재고가 즉시 차감됩니다.")
    last_msg = st.session_state.pop("_outbound_last_success", None)
    if last_msg:
        st.success(last_msg)

    st.markdown("""
    <style>
      div[data-testid="stMetricValue"] {font-size: 2.35rem; text-align:center;}
      div[data-testid="stMetricLabel"] {text-align:center; width:100%; display:flex; justify-content:center;}
      div[data-testid="stMetric"] label, div[data-testid="stMetric"] [data-testid="stMetricLabel"] {width:100%; justify-content:center; text-align:center;}
      div[data-testid="stNumberInput"] input {font-size: 2.15rem !important; font-weight: 600 !important; height: 3.25rem !important; text-align:center !important; padding-left:19px !important;}
      .out-req-label {font-size: 0.92rem; color: #64748b; margin: 0 0 0.25rem 0; text-align:left !important; width:100%; display:block;}
    </style>
    """, unsafe_allow_html=True)

    top_left, top_right = st.columns([1, 1], gap="large")
    selected_customer = None
    selected_company = ""
    selected_product = None
    pick_df = pd.DataFrame()
    req = 1
    expiry_short_first = True
    ignore_company = False
    manual_pick = False
    exact_sales_map, name_sales_map = _customer_last_sale_maps()

    with top_left:
        st.markdown("### 매출처")
        _render_last_sale_importer()
        cust_term = st.text_input("매출처 검색", placeholder="거래처명을 입력하세요", key="out_customer_term")
        direct_customer = st.checkbox("직접입력", value=False, key="out_customer_direct")
        cust_df = pd.DataFrame()
        if direct_customer:
            manual_name = st.text_input("직접입력 매출처명", placeholder="매출처명을 직접 입력하세요", key="out_customer_manual_name").strip()
            if manual_name:
                st.session_state["out_selected_customer"] = {"customer_name": manual_name, "company": ""}
                st.info(f"직접입력 매출처: {manual_name}")
            else:
                st.info("매출처명을 직접 입력하세요.")
        else:
            if cust_term.strip():
                like = f"%{cust_term.strip()}%"
                cust_df = q("SELECT * FROM customers WHERE customer_name LIKE ? ORDER BY customer_name, company, id LIMIT 50", (like,))
            else:
                cust_df = q("SELECT * FROM customers ORDER BY customer_name, company, id LIMIT 50")
            if not cust_df.empty:
                labels = [_customer_select_label(r, exact_sales_map, name_sales_map) for r in cust_df.itertuples()]
                default_label = st.session_state.get("_out_customer_label")
                default_idx = labels.index(default_label) if default_label in labels else 0
                label = st.selectbox("거래처 선택", labels, index=default_idx, key="out_customer_select")
                st.session_state["_out_customer_label"] = label
                selected_row = cust_df.iloc[labels.index(label)]
                selected_customer = {"customer_name": str(selected_row.get("customer_name") or "").strip(), "company": str(selected_row.get("company") or "").strip()}
                st.session_state["out_selected_customer"] = selected_customer
            else:
                st.info("검색된 거래처가 없습니다.")
        selected_customer = selected_customer or st.session_state.get("out_selected_customer") or None
        selected_company = str((selected_customer or {}).get("company") or "").strip()
        if selected_customer:
            customer_name = str(selected_customer.get("customer_name") or "").strip()
            st.markdown("#### 거래처 상세정보")
            detail_parts = [customer_name]
            if selected_company:
                detail_parts.append(selected_company)
            st.caption(" · ".join(detail_parts))
            detail_col, recent_col = st.columns(2)
            with detail_col:
                if st.button("거래처 상세정보 보기", use_container_width=True, key=f"customer_detail_{customer_name}_{selected_company}"):
                    _open_customer_detail_dialog(customer_name, selected_company)
            with recent_col:
                if st.button("최근 출고 제품 보기", use_container_width=True, key=f"recent_customer_outbound_{customer_name}_{selected_company}"):
                    _open_recent_customer_outbound_dialog(customer_name, selected_company)

        fallback_detail = st.session_state.get("_show_customer_detail")
        if fallback_detail:
            with st.expander("거래처 상세정보", expanded=True):
                _show_customer_detail_dialog(fallback_detail.get("customer_name", ""), fallback_detail.get("company", ""))
                if st.button("닫기", key="close_customer_detail"):
                    st.session_state.pop("_show_customer_detail", None)
                    st.rerun()
        fallback_dialog = st.session_state.get("_show_recent_customer_outbound")
        if fallback_dialog:
            with st.expander("최근 출고 제품", expanded=True):
                _show_recent_customer_outbound_dialog(fallback_dialog.get("customer_name", ""), fallback_dialog.get("company", ""))
                if st.button("닫기", key="close_recent_customer_outbound"):
                    st.session_state.pop("_show_recent_customer_outbound", None)
                    st.rerun()

        if selected_customer:
            customer_name = str(selected_customer.get("customer_name") or "").strip()
            st.markdown("#### 거래처 상세정보")
            detail_parts = [customer_name]
            if selected_company:
                detail_parts.append(selected_company)
            st.caption(" · ".join(detail_parts))
            if st.button("최근 출고 제품 보기", use_container_width=True, key=f"recent_customer_outbound_{customer_name}_{selected_company}"):
                _open_recent_customer_outbound_dialog(customer_name, selected_company)

        fallback_dialog = st.session_state.get("_show_recent_customer_outbound")
        if fallback_dialog:
            with st.expander("최근 출고 제품", expanded=True):
                _show_recent_customer_outbound_dialog(
                    fallback_dialog.get("customer_name", ""),
                    fallback_dialog.get("company", ""),
                )
                if st.button("닫기", key="close_recent_customer_outbound"):
                    st.session_state.pop("_show_recent_customer_outbound", None)
                    st.rerun()

    with top_right:
        st.markdown("### 출고 제품")
        products = _normalize_product_options(product_options())
        product_term = st.text_input("제품 검색", placeholder="제품명을 입력하세요", key="out_product_term")
        term_key = product_term.strip().lower().replace(" ", "")
        filtered_products = [p for p in products if term_key in p.lower().replace(" ", "")] if term_key else products
        if filtered_products:
            selected_product = st.selectbox("제품 선택", filtered_products, index=None, placeholder="제품을 선택하세요", key="out_product_select")
        else:
            st.info("검색된 제품이 없습니다.")
        if selected_product:
            ignore_company = st.checkbox("사업장 무시하고 전체 재고에서 선택", value=False, key="out_ignore_company")
            pick_df = _inventory_query_for_outbound(selected_product, selected_company, ignore_company=ignore_company)
            total_qty = _safe_int(pick_df["qty"].sum(), 0) if not pick_df.empty else 0
            metric_col, req_col = st.columns(2, gap="large")
            with metric_col:
                st.metric("총재고", f"{total_qty:,}")
            with req_col:
                st.markdown("<div class='out-req-label'>출고 요청 수량</div>", unsafe_allow_html=True)
                req = st.number_input("출고 요청 수량", min_value=1, value=1, step=1, key="out_req_qty", label_visibility="collapsed")
            expiry_short_first = st.checkbox("유통기한 짧은 순으로 추천", value=True, key="out_expiry_short_first")
            manual_pick = st.checkbox("재고 직접 선택", value=False, key="out_manual_pick")

    st.markdown("---")
    st.markdown("### 출고할 재고")
    if not selected_customer:
        st.info("매출처를 선택하거나 직접 입력하세요.")
    elif not selected_product:
        st.info("출고 제품을 선택하세요.")
    elif pick_df.empty:
        if selected_company and not ignore_company:
            st.warning(f"{selected_company} 사업장에 출고 가능한 재고가 없습니다.")
        else:
            st.warning("출고 가능한 재고가 없습니다.")
    else:
        pending_rows = []
        if manual_pick:
            editor_source = _manual_pick_rows(pick_df)
            editor_df = st.data_editor(editor_source, hide_index=True, use_container_width=True, key="out_manual_editor", disabled=["id", "사업장", "제품명", "LOT", "유통기한", "로케이션", "현재수량"], column_config={"선택": st.column_config.CheckboxColumn(), "요청수량": st.column_config.NumberColumn(min_value=0, step=1, format="%d"), "현재수량": st.column_config.NumberColumn(format="%d")})
            pending_rows = _manual_pick_rows(pick_df, editor_df)
        else:
            rec_df = _recommended_rows(pick_df, req, expiry_short_first=expiry_short_first)
            if rec_df.empty or int(rec_df["요청수량"].sum()) < int(req):
                st.warning("요청 수량만큼 출고 가능한 재고가 부족합니다.")
            st.dataframe(rec_df, hide_index=True, use_container_width=True)
            pending_rows = rec_df.to_dict("records") if not rec_df.empty else []
        if pending_rows:
            if st.button("출고할 재고에 추가", type="primary", use_container_width=True, key="out_add_selected"):
                warnings = _cart_expiry_warnings(pending_rows)
                if warnings:
                    st.session_state["pending_outbound_add_rows"] = pending_rows
                    st.session_state["pending_outbound_add_warnings"] = warnings
                    st.rerun()
                else:
                    _add_rows_to_outbound_cart(pending_rows)
                    st.rerun()

                st.rerun()

    pending_warnings = st.session_state.get("pending_outbound_add_warnings") or []
    if pending_warnings:
        st.warning("유통기한이 짧은 제품이 포함되어 있습니다.")
        for text in pending_warnings:
            st.write(f"- {text}")
        wc1, wc2 = st.columns(2)
        with wc1:
            if st.button("추가 취소", use_container_width=True, key="out_warning_cancel"):
                st.session_state.pop("pending_outbound_add_rows", None)
                st.session_state.pop("pending_outbound_add_warnings", None)
                st.rerun()
        with wc2:
            if st.button("확인 후 추가", type="primary", use_container_width=True, key="out_warning_confirm"):
                rows = st.session_state.pop("pending_outbound_add_rows", [])
                st.session_state.pop("pending_outbound_add_warnings", None)
                _add_rows_to_outbound_cart(rows)
                st.rerun()

    cart = get_cart()
    if cart:
        st.markdown("---")
        st.markdown("### 출고지시 목록")
        cart_df = pd.DataFrame(cart)
        display_cols = ["사업장", "제품명", "LOT", "유통기한", "로케이션", "요청수량"]
        show = cart_df[[c for c in display_cols if c in cart_df.columns]].copy()
        show["삭제"] = False
        edited_cart = st.data_editor(
            show,
            hide_index=True,
            use_container_width=True,
            key=f"out_cart_editor_{st.session_state.get('out_cart_editor_token', 0)}",
            disabled=[c for c in display_cols if c != "요청수량"],
            column_config={
                "요청수량": st.column_config.NumberColumn(min_value=1, step=1, format="%d"),
                "삭제": st.column_config.CheckboxColumn(),
            },
        )

        if not edited_cart.equals(show):
            rebuilt = []
            for idx, row in edited_cart.iterrows():
                if bool(row.get("삭제", False)):
                    continue
                source = dict(cart[idx])
                source["요청수량"] = _safe_int(row.get("요청수량"), source.get("요청수량", 0))
                rebuilt.append(source)
            st.session_state["outbound_cart"] = rebuilt
            st.session_state["out_cart_editor_token"] = int(st.session_state.get("out_cart_editor_token", 0) or 0) + 1
            st.rerun()
        memo = st.text_input("메모", value=str(st.session_state.get("editing_order_title") or ""), key="out_order_memo")
        customer_payload = _current_customer_payload(selected_customer)
        title = build_outbound_order_title(customer_payload.get("customer_name"), memo)
        download_col1, download_col2 = st.columns(2)
        with download_col1:
            st.download_button("출고지시서 엑셀 다운로드", data=outbound_excel_bytes(cart, title), file_name=f"출고지시서_{date.today()}.xlsx", use_container_width=True)
        with download_col2:
            st.download_button("출고지시서 PDF 다운로드", data=outbound_pdf_bytes(cart, title), file_name=f"출고지시서_{date.today()}.pdf", mime="application/pdf", use_container_width=True)
        if st.button("출고지시 저장", type="primary", use_container_width=True, key="out_save_order"):
            warnings = _cart_expiry_warnings(cart)
            if warnings:
                st.session_state["pending_outbound_save"] = {"cart": cart, "title": title, "customer": customer_payload}
                st.session_state["pending_outbound_expiry_warnings"] = warnings
                st.rerun()
            else:
                _save_outbound_cart_with_customer(cart, title, customer_payload)

    save_warnings = st.session_state.get("pending_outbound_expiry_warnings") or []
    if save_warnings:
        st.warning("유통기한이 짧은 제품이 포함되어 있습니다. 저장 전에 확인하세요.")
        for text in save_warnings:
            st.write(f"- {text}")
        sc1, sc2 = st.columns(2)
        with sc1:
            if st.button("저장 취소", use_container_width=True, key="out_save_warning_cancel"):
                st.session_state.pop("pending_outbound_save", None)
                st.session_state.pop("pending_outbound_expiry_warnings", None)
                st.rerun()
        with sc2:
            if st.button("확인 후 저장", type="primary", use_container_width=True, key="out_save_warning_confirm"):
                pending = st.session_state.pop("pending_outbound_save", {})
                st.session_state.pop("pending_outbound_expiry_warnings", None)
                _save_outbound_cart_with_customer(pending.get("cart") or [], pending.get("title") or "", pending.get("customer") or {})
