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
            (
                str((customer_payload or {}).get("customer_name") or "").strip(),
                str((customer_payload or {}).get("company") or "").strip(),
                int(order_id),
            ),
        )
        con.commit()


def _current_customer_payload(selected_customer):
    selected_customer = selected_customer or st.session_state.get("out_selected_customer") or {}
    return {
        "customer_name": str(selected_customer.get("customer_name") or "").strip(),
        "company": str(selected_customer.get("company") or "").strip(),
    }


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


def _customer_select_label(row, exact_map, name_map):
    name = str(getattr(row, "customer_name", "") or "").strip()
    company = str(getattr(row, "company", "") or "").strip()
    manager = str(getattr(row, "manager", "") or "").strip()
    last_sale = exact_map.get((name, company)) or name_map.get(name) or "-"
    parts = [name]
    if company:
        parts.append(company)
    if manager:
        parts.append(manager)
    parts.append(f"최근거래 {last_sale}")
    return " | ".join(parts)


def _inventory_query_for_outbound(selected_product, selected_company, ignore_company=False):
    params = [selected_product]
    where = ["product_name=?", "COALESCE(qty,0)>0", "location<>'P'"]
    if not ignore_company:
        if not selected_company:
            return pd.DataFrame()
        where.append("company=?")
        params.append(selected_company)
    return q(
        f"""SELECT id,company,product_name,warehouse_name,lot,exp_date,location,qty,
                    COALESCE(is_shippable,1) AS is_shippable
             FROM inventory
             WHERE {' AND '.join(where)}
             ORDER BY company,exp_date,lot,location""",
        tuple(params),
    )


def _manual_pick_rows(pick_df):
    if pick_df is None or pick_df.empty:
        return pd.DataFrame()
    rows = pick_df.copy()
    rows = rows.rename(
        columns={
            "company": "사업장",
            "product_name": "제품명",
            "lot": "LOT",
            "exp_date": "유통기한",
            "location": "로케이션",
            "qty": "현재수량",
        }
    )
    rows["유통기한"] = rows["유통기한"].apply(display_date_only)
    rows.insert(0, "선택", False)
    rows["요청수량"] = 0
    return rows[["선택", "id", "사업장", "제품명", "LOT", "유통기한", "로케이션", "현재수량", "요청수량"]]


def _recommended_rows(pick_df, req, expiry_short_first=True):
    if pick_df is None or pick_df.empty:
        return pd.DataFrame()
    recommended = recommend_picks(pick_df, int(req or 0), expiry_short_first=expiry_short_first)
    if recommended is None or recommended.empty:
        return pd.DataFrame()
    rows = recommended.copy()
    rows = rows.rename(
        columns={
            "company": "사업장",
            "product_name": "제품명",
            "lot": "LOT",
            "exp_date": "유통기한",
            "location": "로케이션",
            "qty": "현재수량",
            "pick_qty": "요청수량",
        }
    )
    rows["유통기한"] = rows["유통기한"].apply(display_date_only)
    return rows[["id", "사업장", "제품명", "LOT", "유통기한", "로케이션", "현재수량", "요청수량"]]


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

    if selected_product:
        pick_df = _inventory_query_for_outbound(selected_product, selected_company, ignore_company=ignore_company)

    stock_left, rec_right = st.columns([1, 1], gap="large")

    with stock_left:
        st.markdown("### 현재 출고 가능 재고")
        if selected_product:
            if pick_df.empty:
                if ignore_company:
                    st.warning("전체 사업장에 출고 지시 가능한 재고가 없습니다.")
                elif selected_company:
                    st.warning(f"{selected_company}에 출고 지시 가능한 재고가 없습니다.")
                else:
                    st.info("매출처를 선택하면 해당 사업장 재고가 표시됩니다. 직접입력 매출처는 사업장 정보가 없으므로 필요한 경우 '사업장 구분 없이'를 체크하세요.")
            else:
                view = pick_df[["company", "lot", "exp_date", "location", "qty"]].copy()
                view = view.rename(columns={"company": "사업장", "lot": "LOT", "exp_date": "유통기한", "location": "로케이션", "qty": "수량"})
                view["유통기한"] = view["유통기한"].apply(display_date_only)
                view = view.sort_values(["사업장", "LOT", "유통기한", "로케이션"])
                st.dataframe(view, hide_index=True, use_container_width=True)
        else:
            st.info("제품을 선택하면 현재 출고 가능 재고가 표시됩니다.")

    with rec_right:
        if manual_pick:
            st.markdown("### 특정 재고 직접 선택")
            manual = _manual_pick_rows(pick_df)
            if not manual.empty:
                edited = st.data_editor(
                    manual,
                    hide_index=True,
                    use_container_width=True,
                    disabled=["id", "사업장", "제품명", "LOT", "유통기한", "로케이션", "현재수량"],
                    column_config={
                        "선택": st.column_config.CheckboxColumn("선택"),
                        "id": None,
                        "요청수량": st.column_config.NumberColumn("요청수량", min_value=0, step=1),
                    },
                    key="out_manual_editor",
                )
                if st.button("선택 재고 장바구니에 담기", type="primary", use_container_width=True):
                    pending_rows = []
                    for _, row in edited.iterrows():
                        qty2 = int(row.get("요청수량") or 0)
                        if bool(row.get("선택")) and qty2 > 0:
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
                st.info("직접 선택할 재고가 없습니다.")
        else:
            st.markdown("### 추천 출고 재고")
            if selected_product and req:
                rec = _recommended_rows(pick_df, req, expiry_short_first=expiry_short_first)
                if not rec.empty:
                    edited = st.data_editor(
                        rec,
                        hide_index=True,
                        use_container_width=True,
                        num_rows="fixed",
                        disabled=["id", "사업장", "제품명", "LOT", "유통기한", "로케이션", "현재수량"],
                        column_config={"id": None, "요청수량": st.column_config.NumberColumn("요청수량", min_value=0, step=1)},
                        key="out_rec_editor",
                    )
                    if st.button("장바구니에 담기", type="primary", use_container_width=True):
                        pending_rows = []
                        for _, row in edited.iterrows():
                            qty2 = int(row.get("요청수량") or 0)
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
                    st.session_state["_outbound_last_success"] = f"{added}개 행을 출고지시 장바구니에 담았습니다."
                    st.rerun()
