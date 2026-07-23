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
    """수정 중인 출고지시서에 저장된 매출처 정보를 가져온다."""
    order_id = st.session_state.get("editing_order_id")
    if not order_id:
        return {}
    _ensure_outbound_customer_columns()
    df = q(
        """
        SELECT customer_name, customer_company
        FROM outbound_orders
        WHERE id=?
        """,
        (int(order_id),),
    )
    if df.empty:
        return {}
    row = df.iloc[0]
    return {
        "customer_name": str(row.get("customer_name") or "").strip(),
        "company": str(row.get("customer_company") or "").strip(),
    }


def _prefill_customer_from_saved_order():
    """수정 진입 시 저장된 매출처 정보를 화면에 복원한다.

    새로 저장되는 지시서는 outbound_orders.customer_name/customer_company를 사용한다.
    과거 저장 데이터처럼 컬럼 값이 비어 있는 경우에만 제목에서 보조 복원한다.
    """
    if not st.session_state.get("editing_order_id"):
        return
    if str(st.session_state.get("out_customer_term") or "").strip() or str(st.session_state.get("out_customer_manual_name") or "").strip():
        return

    stored = _stored_customer_for_editing_order()
    customer = str(stored.get("customer_name") or "").strip()
    company = str(stored.get("company") or "").strip()

    if not customer:
        title = str(st.session_state.get("editing_order_title") or "").strip()
        customer = title.split(" - ", 1)[0].strip() if title else ""

    if customer:
        st.session_state["out_customer_term"] = customer
        st.session_state["out_customer_manual_name"] = customer
    if customer or company:
        st.session_state["out_selected_customer"] = {
            "customer_name": customer,
            "company": company,
        }


def _current_customer_payload(selected_customer=None):
    """현재 화면 또는 수정 저장 시 유지할 매출처 정보를 만든다."""
    if bool(st.session_state.get("out_customer_direct")):
        return {
            "customer_name": str(st.session_state.get("out_customer_manual_name") or "").strip(),
            "company": "",
        }
    if selected_customer is not None:
        return {
            "customer_name": str(selected_customer.get("customer_name") or "").strip(),
            "company": str(selected_customer.get("company") or "").strip(),
        }
    saved = st.session_state.get("out_selected_customer", {}) or {}
    return {
        "customer_name": str(saved.get("customer_name") or "").strip(),
        "company": str(saved.get("company") or "").strip(),
    }


def _save_outbound_customer(order_id, customer_payload):
    _ensure_outbound_customer_columns()
    customer_name = str((customer_payload or {}).get("customer_name") or "").strip()
    customer_company = str((customer_payload or {}).get("company") or "").strip()
    with connect() as con:
        con.execute(
            """
            UPDATE outbound_orders
            SET customer_name=?, customer_company=?
            WHERE id=?
            """,
            (customer_name, customer_company, int(order_id)),
        )
        con.commit()


def _save_outbound_cart_with_customer(cart, title, customer_payload):
    """장바구니 저장/수정 시 매출처 정보를 출고지시서에 함께 저장한다."""


    _ensure_outbound_customer_columns()
    editing_id = st.session_state.get("editing_order_id")
    if editing_id:
        update_outbound_order(int(editing_id), title, cart)
        _save_outbound_customer(int(editing_id), customer_payload)
        msg = f"출고지시서 #{int(editing_id)} 수정 저장 완료"
        st.session_state.pop("editing_order_id", None)
        st.session_state.pop("editing_order_title", None)
    else:
        oid = save_outbound_order(cart, title)
        _save_outbound_customer(int(oid), customer_payload)
        msg = f"출고지시서 #{int(oid)} 저장 완료"

    for k in [
        "outbound_cart", "out_customer_term", "out_customer_select", "_out_customer_label",
        "out_selected_customer", "out_customer_direct", "out_customer_manual_name",
        "out_product_term", "out_req_qty", "out_rec_editor", "out_manual_editor",
        "out_ignore_company", "out_manual_pick", "pending_outbound_save",
        "pending_outbound_expiry_warnings",
    ]:
        st.session_state.pop(k, None)
    st.session_state["outbound_cart"] = []
    st.session_state["out_cart_editor_token"] = int(st.session_state.get("out_cart_editor_token", 0) or 0) + 1
    st.session_state["_outbound_reset_inputs_pending"] = True
    st.session_state["_outbound_last_success"] = msg
    st.rerun()


def _normalize_customer_name(value):
    return str(value or "").strip()


def _parse_sales_excel(uploaded_file, *, company, header_row, date_col, customer_col):
    """매출 엑셀에서 거래처별 최근거래일을 추출한다."""
    if uploaded_file is None:
        return pd.DataFrame(columns=["customer_name", "company", "last_sale_date"])
    df = pd.read_excel(uploaded_file, header=header_row, dtype=object)
    df.columns = [str(c).strip() for c in df.columns]
    if date_col not in df.columns or customer_col not in df.columns:
        raise ValueError(f"{company} 매출 파일에서 '{date_col}', '{customer_col}' 컬럼을 찾을 수 없습니다. 현재 컬럼: {', '.join(df.columns)}")

    work = df[[date_col, customer_col]].copy()
    work[customer_col] = work[customer_col].apply(_normalize_customer_name)
    work = work[work[customer_col] != ""]
    work[date_col] = pd.to_datetime(work[date_col], errors="coerce")
    work = work.dropna(subset=[date_col])
    if work.empty:
        return pd.DataFrame(columns=["customer_name", "company", "last_sale_date"])

    result = (
        work.groupby(customer_col, as_index=False)[date_col]
            .max()
            .rename(columns={customer_col: "customer_name", date_col: "last_sale_date"})
    )
    result["company"] = company
    result["last_sale_date"] = result["last_sale_date"].dt.strftime("%Y-%m-%d")
    return result[["customer_name", "company", "last_sale_date"]]


def _upsert_customer_last_sales(rows_df):
    _ensure_customer_last_sales_table()
    if rows_df is None or rows_df.empty:
        return 0
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    count = 0
    with connect() as con:
        cur = con.cursor()
        for r in rows_df.itertuples(index=False):
            customer_name = _normalize_customer_name(getattr(r, "customer_name", ""))
            company = str(getattr(r, "company", "") or "").strip()
            last_sale_date = str(getattr(r, "last_sale_date", "") or "").strip()
            if not customer_name or not last_sale_date:
                continue
            old = cur.execute(
                "SELECT id, last_sale_date FROM customer_last_sales WHERE customer_name=? AND company=?",
                (customer_name, company),
            ).fetchone()
            if old:
                old_date = str(old[1] or "")
                final_date = max(old_date, last_sale_date) if old_date else last_sale_date
                cur.execute(
                    """
                    UPDATE customer_last_sales
                    SET last_sale_date=?, source_company=?, updated_at=?
                    WHERE id=?
                    """,
                    (final_date, company, now, int(old[0])),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO customer_last_sales(customer_name, company, last_sale_date, source_company, updated_at)
                    VALUES(?,?,?,?,?)
                    """,
                    (customer_name, company, last_sale_date, company, now),
                )
            count += 1
        con.commit()
    return count


def _customer_last_sale_maps():
    _ensure_customer_last_sales_table()
    df = q(
        """
        SELECT customer_name, company, last_sale_date
        FROM customer_last_sales
        WHERE TRIM(COALESCE(customer_name,''))<>''
          AND TRIM(COALESCE(last_sale_date,''))<>''
        """
    )
    exact = {}
    by_name = {}
    if df.empty:
        return exact, by_name
    for r in df.itertuples(index=False):
        customer = _normalize_customer_name(getattr(r, "customer_name", ""))
        company = str(getattr(r, "company", "") or "").strip()
        last_date = str(getattr(r, "last_sale_date", "") or "").strip()
        if not customer or not last_date:
            continue
        exact[(customer, company)] = max(exact.get((customer, company), ""), last_date)
        by_name[customer] = max(by_name.get(customer, ""), last_date)
    return exact, by_name


def _days_ago_label(date_text):
    try:
        d = datetime.strptime(str(date_text), "%Y-%m-%d").date()
    except Exception:
        return ""
    days = (date.today() - d).days
    if days < 0:
        return "예정"
    if days == 0:
        return "오늘"
    return f"{days}일 전"


def _last_sale_text(customer_name, company, exact_map, name_map):
    customer = _normalize_customer_name(customer_name)
    company = str(company or "").strip()
    last_date = exact_map.get((customer, company)) or name_map.get(customer) or ""
    if not last_date:
        return "최근거래 없음"
    ago = _days_ago_label(last_date)
    return f"최근거래 {last_date} ({ago})" if ago else f"최근거래 {last_date}"


def _customer_select_label(row, exact_map, name_map):
    customer = str(getattr(row, "customer_name", "") or "").strip()
    company = str(getattr(row, "company", "") or "").strip()
    return f"{customer} | {company or '-'} | {_last_sale_text(customer, company, exact_map, name_map)}"


def _render_last_sale_importer():
    with st.expander("최근거래일 갱신", expanded=False):
        st.caption("노투스팜 매출은 1행 헤더, 노투스 매출은 7행 헤더 기준으로 거래처별 마지막 거래일만 저장합니다.")
        np_file = st.file_uploader("노투스팜 매출 파일", type=["xls", "xlsx"], key="last_sale_np_file")
        nt_file = st.file_uploader("노투스 매출 파일", type=["xls", "xlsx"], key="last_sale_nt_file")
        if st.button("최근거래일 갱신", use_container_width=True, key="last_sale_import_btn"):
            try:
                frames = []
                if np_file is not None:
                    frames.append(_parse_sales_excel(np_file, company="노투스팜", header_row=0, date_col="매출일자", customer_col="거래처명"))
                if nt_file is not None:
                    frames.append(_parse_sales_excel(nt_file, company="노투스", header_row=6, date_col="거래일자", customer_col="거래처명"))
                if not frames:
                    st.warning("갱신할 매출 파일을 업로드하세요.")
                else:
                    merged = pd.concat(frames, ignore_index=True)
                    count = _upsert_customer_last_sales(merged)
                    st.success(f"최근거래일 갱신 완료: {count}개 거래처 반영")
                    st.rerun()
            except Exception as e:
                st.error(str(e))


def _inventory_query_for_outbound(selected_product, selected_company, ignore_company=False):
    selected_product = str(selected_product or "").strip()
    selected_company = str(selected_company or "").strip()
    if not selected_product:
        return pd.DataFrame()
    if ignore_company:
        return q(
            """
            SELECT *
            FROM inventory
            WHERE product_name=? AND qty>0
            ORDER BY company, location, lot, exp_date
            """,
            (selected_product,),
        )
    if selected_company and selected_company in COMPANIES:
        return q(
            """
            SELECT *
            FROM inventory
            WHERE product_name=? AND company=? AND qty>0
            ORDER BY location, lot, exp_date
            """,
            (selected_product, selected_company),
        )
    return pd.DataFrame()


def _manual_pick_rows(pick_df, editor_df):
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
        pending_rows.append({
            "id": int(src.get("id")),
            "로케이션": src.get("location", ""),
            "사업장": src.get("company", ""),
            "제품명": src.get("product_name", ""),
            "LOT": src.get("lot", "-") or "-",
            "유통기한": display_date_only(src.get("exp_date", "-")),
            "요청수량": min(qty2, available),
        })
    return pending_rows


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
      /* 출고지시 상단 카드: 총재고 숫자와 출고 요청 수량 입력값의 시각 크기를 맞춤 */
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
            manual_name = st.text_input(
                "직접입력 매출처명",
                placeholder="매출처명을 직접 입력하세요",
                key="out_customer_manual_name",
            ).strip()
            if manual_name:
                st.session_state["out_selected_customer"] = {"customer_name": manual_name, "company": ""}
                st.info(f"직접입력 매출처: {manual_name}")
            else:
                st.info("매출처명을 직접 입력하세요.")
        else:
            if cust_term.strip():
                like = f"%{cust_term.strip()}%"
                cust_df = q("""SELECT * FROM customers WHERE customer_name LIKE ? ORDER BY customer_name, company, id LIMIT 50""", (like,))
            else:
                cust_df = q("""SELECT * FROM customers ORDER BY customer_name, company, id LIMIT 50""")
            if not cust_df.empty:
                labels = [_customer_select_label(r, exact_sales_map, name_sales_map) for r in cust_df.itertuples()]
                default_label = st.session_state.get("_out_customer_label")
                default_idx = labels.index(default_label) if default_label in labels else 0
                label = st.selectbox("거래처 선택", labels, index=default_idx, key="out_customer_select")
                st.session_state["_out_customer_label"] = label
                selected_customer = cust_df.iloc[labels.index(label)]
                st.session_state["out_selected_customer"] = selected_customer.to_dict()
                selected_company = str(selected_customer.get("company") or "").strip()
                last_sale = _last_sale_text(selected_customer.get("customer_name"), selected_company, exact_sales_map, name_sales_map)
                st.markdown(f"**사업장 :** {selected_company or '-'} &nbsp;&nbsp;&nbsp; **최근거래 :** {last_sale.replace('최근거래 ', '')} &nbsp;&nbsp;&nbsp; **유형 :** {selected_customer.get('customer_type') or '-'} &nbsp;&nbsp;&nbsp; **담당자 :** {selected_customer.get('manager') or '-'}")
                with st.expander("거래처 상세정보", expanded=False):
                    st.write(f"주소 : {selected_customer.get('address') or '-'}")
                    st.write(f"연락처 : {selected_customer.get('phone') or '-'}")
            else:
                stored_customer = _current_customer_payload()
                if stored_customer.get("customer_name"):
                    selected_company = stored_customer.get("company", "")
                    last_sale = _last_sale_text(stored_customer.get("customer_name"), selected_company, exact_sales_map, name_sales_map)
                    st.info(f"저장된 매출처: {stored_customer.get('customer_name')} | {selected_company or '-'} | {last_sale}")
                else:
                    st.info("거래처를 검색하거나 직접입력을 체크하세요.")

        st.markdown("### 재고 선택 옵션")
        ignore_company = st.checkbox("사업장 구분 없이", value=False, key="out_ignore_company")
        manual_pick = st.checkbox("특정 재고 선택", value=False, key="out_manual_pick")
        if ignore_company:
            st.caption("매출처 사업장과 관계없이 노투스팜/노투스/NOH/비자료 재고를 모두 선택할 수 있습니다.")
        if manual_pick:
            st.caption("유통기한 우선 추천 없이 표시된 재고 중 원하는 사업장/LOT/유통기한/로케이션을 직접 선택합니다.")

    with top_right:
        st.markdown("### 제품 선택")
        term = st.text_input("제품 검색", placeholder="제품명/전산상 명칭/별칭을 입력하세요", key="out_product_term")
        opts = product_options(term)
        if opts.empty:
            st.info("제품을 검색하세요.")
        else:
            selected_product = st.selectbox("제품 선택", opts["standard_name"].dropna().astype(str).drop_duplicates().tolist())
            if ignore_company:
                st.caption("추천 범위: 전체 사업장 재고")
            elif selected_company and selected_company in COMPANIES:
                st.caption(f"추천 범위: {selected_company} 재고")
            elif selected_customer is not None:
                st.warning("선택한 매출처의 사업장이 비어 있거나 WMS 사업장과 일치하지 않습니다. 거래처 관리에서 사업장을 확인하세요.")
            total_col, req_col = st.columns([1, 1], gap="medium")
            with total_col:
                df_total = q("SELECT COALESCE(SUM(qty),0) AS qty FROM inventory WHERE product_name=? AND qty>0", (selected_product,))
                total_qty = int(df_total.iloc[0]["qty"] or 0) if not df_total.empty else 0
                st.metric("총재고", f"{total_qty} EA")
            with req_col:
                st.markdown('<div class="out-req-label">출고 요청 수량</div>', unsafe_allow_html=True)
                req = st.number_input("출고 요청 수량", min_value=1, step=1, key="out_req_qty", label_visibility="collapsed")
            if not manual_pick:
                expiry_short_first = st.checkbox("유통기한 짧은 것 먼저", value=True, key="out_expiry_short_first")

    stock_left, rec_right = st.columns([1, 1], gap="large")

    with stock_left:
        st.markdown("### 현재 출고 가능 재고")
        if selected_product:
            pick_df = _inventory_query_for_outbound(selected_product, selected_company, ignore_company=ignore_company)
            if pick_df.empty:
                if ignore_company:
                    st.warning("전체 사업장에 출고 지시 가능한 재고가 없습니다.")
                elif selected_company:
                    st.warning(f"{selected_company}에 출고 지시 가능한 재고가 없습니다.")
                else:
                    st.info("매출처를 선택하면 해당 사업장 재고가 표시됩니다. 직접입력 매출처는 사업장 정보가 없으므로 필요한 경우 '사업장 구분 없이'를 체크하세요.")
            else:
                view = pick_df[["company", "lot", "exp_date", "location", "qty"]].copy()
                view = view.rename(columns={"company":"사업장", "lot":"LOT", "exp_date":"유통기한", "location":"로케이션", "qty":"수량"})
                view["유통기한"] = view["유통기한"].apply(display_date_only)
                view = view.sort_values(["사업장", "LOT", "유통기한", "로케이션"])
                st.dataframe(view, hide_index=True, use_container_width=True)
        else:
            st.info("제품을 선택하면 현재 출고 가능 재고가 표시됩니다.")

    with rec_right:
        if manual_pick:
            st.markdown("### 특정 재고 선택")
            if selected_product and not pick_df.empty:
                manual = pick_df[["company", "lot", "exp_date", "location", "qty"]].copy().reset_index(drop=True)
                manual.insert(0, "선택", False)
                manual["요청수량"] = 0
                manual = manual.rename(columns={"company":"사업장", "lot":"LOT", "exp_date":"유통기한", "location":"로케이션", "qty":"현재수량"})
                manual["유통기한"] = manual["유통기한"].apply(display_date_only)
                edited = st.data_editor(
                    manual[["선택", "사업장", "로케이션", "LOT", "유통기한", "현재수량", "요청수량"]],
                    hide_index=True,
                    use_container_width=True,
                    num_rows="fixed",
                    disabled=["사업장", "로케이션", "LOT", "유통기한", "현재수량"],
                    column_config={
                        "선택": st.column_config.CheckboxColumn("선택"),
                        "요청수량": st.column_config.NumberColumn("요청수량", min_value=0, step=1),
                    },
                    key="out_manual_editor",
                )
                if st.button("선택 재고 장바구니에 담기", type="primary", use_container_width=True):
                    pending_rows = _manual_pick_rows(pick_df, edited)
                    if not pending_rows:
                        st.warning("선택된 재고 또는 요청수량이 없습니다.")
                    else:
                        warn_rows = _cart_expiry_warnings(pending_rows)
                        if warn_rows:
                            st.session_state["pending_outbound_add_rows"] = pending_rows
                            st.session_state["pending_outbound_add_warnings"] = warn_rows
                            st.rerun()
                        else:
                            added = _add_rows_to_outbound_cart(pending_rows)
                            st.success(f"{added}개 행을 출고지시 장바구니에 담았습니다.")
                            st.rerun()
            else:
                st.info("제품과 재고가 표시되면 원하는 재고를 직접 선택할 수 있습니다.")
        else:
            st.markdown("### 이번 품목 출고 추천")
            if selected_product and not pick_df.empty and req:
                available = int(pick_df["qty"].sum())
                if available < int(req):
                    st.error(f"재고 부족: 요청 {int(req)}EA / 가능 {available}EA / 부족 {int(req)-available}EA")
                rec_rows, shortage = recommend_picks(pick_df, int(req), expiry_short_first=expiry_short_first)
                if rec_rows:
                    rec = pd.DataFrame(rec_rows)
                    rec_display_cols = ["로케이션", "사업장", "제품명", "LOT", "유통기한", "요청수량"]
                    edited = st.data_editor(
                        rec[rec_display_cols],
                        hide_index=True,
                        use_container_width=True,
                        num_rows="fixed",
                        disabled=["로케이션", "사업장", "제품명", "LOT", "유통기한"],
                        column_config={"요청수량": st.column_config.NumberColumn("요청수량", min_value=0, step=1)},
                        key="out_rec_editor",
                    )
                    if st.button("장바구니에 담기", type="primary", use_container_width=True):
                        pending_rows = []
                        for idx, row in rec.iterrows():
                            qty2 = int(edited.iloc[idx]["요청수량"] or 0)
                            if qty2 > 0:
                                pending_rows.append({
                                    "id": int(row["id"]),
                                    "로케이션": row["로케이션"],
                                    "사업장": row["사업장"],
                                    "제품명": row["제품명"],
                                    "LOT": row["LOT"],
                                    "유통기한": row["유통기한"],
                                    "요청수량": qty2,
                                })
                        warn_rows = _cart_expiry_warnings(pending_rows)
                        if warn_rows:
                            st.session_state["pending_outbound_add_rows"] = pending_rows
                            st.session_state["pending_outbound_add_warnings"] = warn_rows
                            st.rerun()
                        else:
                            added = _add_rows_to_outbound_cart(pending_rows)
                            st.success(f"{added}개 행을 출고지시 장바구니에 담았습니다.")
                            st.rerun()
                else:
                    st.info("추천할 재고가 없습니다.")
            else:
                st.info("매출처와 제품, 출고 요청 수량을 입력하면 추천이 표시됩니다.")

    st.markdown("---")
    st.markdown("### 출고지시 장바구니")
    cart = get_cart()
    if not cart:
        st.info("아직 담긴 품목이 없습니다. 제품을 검색해서 장바구니에 담으세요.")
    else:
        cart_df = pd.DataFrame(cart)
        for c in ["로케이션", "사업장", "제품명", "LOT", "유통기한", "요청수량"]:
            if c not in cart_df.columns:
                cart_df[c] = ""
        display_cols = ["로케이션", "사업장", "제품명", "LOT", "유통기한", "요청수량"]
        edited_cart = st.data_editor(
            cart_df[display_cols],
            hide_index=True,
            use_container_width=True,
            num_rows="dynamic",
            disabled=["로케이션", "사업장", "제품명", "LOT", "유통기한"],
            column_config={"요청수량": st.column_config.NumberColumn("요청수량", min_value=0, step=1)},
            key=f"out_cart_editor_{st.session_state.get('out_cart_editor_token', 0)}",
        )
        new_cart = []
        for i in range(min(len(cart), len(edited_cart))):
            item = dict(cart[i])
            item["요청수량"] = int(edited_cart.iloc[i]["요청수량"] or 0)
            if item["요청수량"] > 0:
                new_cart.append(item)
        if len(new_cart) != len(cart) or any(int(a.get("요청수량", 0)) != int(b.get("요청수량", 0)) for a, b in zip(new_cart, cart)):
            st.session_state["outbound_cart"] = new_cart
            st.session_state["out_cart_editor_token"] = int(st.session_state.get("out_cart_editor_token", 0) or 0) + 1
            st.rerun()
        customer_payload = _current_customer_payload(selected_customer)
        customer_name = customer_payload.get("customer_name", "")
        fallback_title = datetime.now().strftime("출고지시 %Y-%m-%d %H:%M")
        default_title = st.session_state.get("editing_order_title") or build_outbound_order_title(customer_name, cart, fallback_title)
        title = st.text_input("출고지시서 제목", value=default_title, placeholder="예: A병원 디센바(1V) 외 2품목")
        b1, b2 = st.columns(2)
        with b1:
            if st.button("지시완료 저장", type="primary", use_container_width=True):
                try:
                    _save_outbound_cart_with_customer(cart, title, customer_payload)
                except Exception as e:
                    st.error(str(e))
        with b2:
            if st.button("장바구니 비우기", use_container_width=True):
                st.session_state["outbound_cart"] = []
                st.session_state.pop("editing_order_id", None)
                st.session_state.pop("editing_order_title", None)
                st.rerun()
        dl1, dl2 = st.columns(2)
        with dl1:
            st.download_button(
                "출고지시서 엑셀 다운로드",
                data=outbound_excel_bytes(cart, title or "출고지시서"),
                file_name=f"NOHTUS_출고지시서_{date.today().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        with dl2:
            pdf_data = outbound_pdf_bytes(cart, title or "출고지시서")
            st.download_button(
                "출고지시서 PDF 다운로드",
                data=pdf_data,
                file_name=f"NOHTUS_출고지시서_{date.today().strftime('%Y%m%d')}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )

    if st.session_state.get("pending_outbound_add_rows"):
        warn_rows = st.session_state.get("pending_outbound_add_warnings", [])
        pending_rows = st.session_state.get("pending_outbound_add_rows", [])
        dialog_api = getattr(st, "dialog", None) or getattr(st, "experimental_dialog", None)
        if dialog_api:
            @dialog_api("⚠ 유통기한 경고")
            def _confirm_expiry_add_dialog():
                st.markdown("""
                <style>
                div[data-testid="stDialog"] div[data-testid="stButton"] > button{
                    min-height:46px!important;
                    min-width:180px!important;
                    border-radius:10px!important;
                    font-weight:800!important;
                    white-space:nowrap!important;
                }
                </style>
                <div style='font-size:16px;line-height:1.7;color:#334155;margin:6px 0 14px 0;font-weight:400;'>
                    유통기한이 만료되었거나 1개월 미만 남은 품목입니다.<br>
                    그래도 출고지시 장바구니에 담으시겠습니까?
                </div>
                """, unsafe_allow_html=True)
                st.dataframe(pd.DataFrame(warn_rows), hide_index=True, use_container_width=True)
                _left, c1, c2, _right = st.columns([1.0, 1.2, 1.7, 1.0], gap="medium")
                with c1:
                    if st.button("아니오", use_container_width=True, key="add_expiry_no"):
                        st.session_state.pop("pending_outbound_add_rows", None)
                        st.session_state.pop("pending_outbound_add_warnings", None)
                        st.rerun()
                with c2:
                    if st.button("예, 담습니다", type="primary", use_container_width=True, key="add_expiry_yes"):
                        added = _add_rows_to_outbound_cart(pending_rows)
                        st.session_state.pop("pending_outbound_add_rows", None)
                        st.session_state.pop("pending_outbound_add_warnings", None)
                        st.session_state["_outbound_last_success"] = f"{added}개 행을 출고지시 장바구니에 담았습니다."
                        st.rerun()
            _confirm_expiry_add_dialog()
        else:
            st.warning("유통기한이 만료되었거나 1개월 미만 남은 품목입니다. 그래도 출고지시 장바구니에 담으시겠습니까?")
            st.dataframe(pd.DataFrame(warn_rows), hide_index=True, use_container_width=True)
            c1, c2 = st.columns(2)
            with c1:
                if st.button("아니오", key="add_expiry_no_inline"):
                    st.session_state.pop("pending_outbound_add_rows", None)
                    st.session_state.pop("pending_outbound_add_warnings", None)
                    st.rerun()
            with c2:
                if st.button("예, 담습니다", type="primary", key="add_expiry_yes_inline"):
                    added = _add_rows_to_outbound_cart(pending_rows)
                    st.session_state.pop("pending_outbound_add_rows", None)
                    st.session_state.pop("pending_outbound_add_warnings", None)
                    st.success(f"{added}개 행을 출고지시 장바구니에 담았습니다.")
                    st.rerun()
