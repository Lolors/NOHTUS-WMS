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


def page_outbound():
    _clear_outbound_inputs_before_render()
    _prefill_customer_from_saved_order()

    st.title("출고지시")
    st.caption("매출처와 제품을 선택하면 재고를 추천합니다. 출고지시 저장 시 선택 재고가 즉시 차감됩니다.")

    last_success = st.session_state.pop("_outbound_last_success", None)
    if last_success:
        st.success(last_success)

    left_input, right_input = st.columns([1, 1], gap="large")

    selected_customer = None
    selected_product = None
    req = 0
    pick_df = pd.DataFrame()
    ignore_company = False
    manual_pick = False
    expiry_short_first = True

    with left_input:
        st.markdown("### 매출처")
        _render_last_sale_importer()
        customers = q("SELECT customer_name, company, manager FROM customers ORDER BY customer_name")
        exact_map, name_map = _customer_last_sale_maps()
        direct = st.checkbox("직접입력 매출처", value=False, key="out_customer_direct")
        if direct:
            manual_customer_name = st.text_input("매출처 직접입력", key="out_customer_manual_name")
            selected_customer = {"customer_name": manual_customer_name, "company": ""} if manual_customer_name else None
        else:
            term = st.text_input("매출처 검색", key="out_customer_term", placeholder="거래처명 일부 입력")
            if term:
                matched = customers[customers["customer_name"].astype(str).str.contains(term, case=False, na=False)]
                if matched.empty:
                    st.info("검색된 매출처가 없습니다.")
                else:
                    labels = [_customer_select_label(r, exact_map, name_map) for r in matched.itertuples(index=False)]
                    selected_label = st.selectbox("매출처 선택", labels, key="out_customer_select")
                    if selected_label:
                        idx = labels.index(selected_label)
                        row = matched.iloc[idx]
                        selected_customer = {
                            "customer_name": str(row.get("customer_name") or "").strip(),
                            "company": str(row.get("company") or "").strip(),
                        }
                        st.session_state["out_selected_customer"] = selected_customer
            else:
                selected_customer = st.session_state.get("out_selected_customer")

    with right_input:
        st.markdown("### 제품 선택")
        ignore_company = st.checkbox("매출처 사업장과 관계없이 전체 사업장 재고에서 선택", value=False, key="out_ignore_company")
        manual_pick = st.checkbox("유통기한 우선 추천 없이 특정 재고 직접 선택", value=False, key="out_manual_pick")
        products = product_options()
        if products:
            pcol, qcol = st.columns([4, 1])
            with pcol:
                selected_product = st.selectbox("제품", products, key="out_product_term", label_visibility="collapsed")
            with qcol:
                req = st.number_input("출고 요청 수량", min_value=1, step=1, key="out_req_qty", label_visibility="collapsed")
            if not manual_pick:
                expiry_short_first = st.checkbox("유통기한 짧은 것 먼저", value=True, key="out_expiry_short_first")

    selected_company = str((selected_customer or {}).get("company") or "").strip()
    st.caption(f"추천 범위: {'전체 사업장 재고' if ignore_company else (selected_company or '매출처 사업장 미선택')}")

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
        cart_df["_cart_row_key"] = [f"row-{idx}" for idx in range(len(cart_df))]
        display_cols = ["_cart_row_key", "로케이션", "사업장", "제품명", "LOT", "유통기한", "요청수량"]
        edited_cart = st.data_editor(
            cart_df[display_cols],
            hide_index=True,
            use_container_width=True,
            num_rows="dynamic",
            disabled=["_cart_row_key", "로케이션", "사업장", "제품명", "LOT", "유통기한"],
            column_config={
                "_cart_row_key": None,
                "요청수량": st.column_config.NumberColumn("요청수량", min_value=0, step=1),
            },
            key=f"out_cart_editor_{st.session_state.get('out_cart_editor_token', 0)}",
        )
        cart_by_key = {f"row-{idx}": dict(item) for idx, item in enumerate(cart)}
        new_cart = []
        for _, edited_row in edited_cart.iterrows():
            row_key = str(edited_row.get("_cart_row_key") or "")
            item = cart_by_key.get(row_key)
            if item is None:
                continue
            item = dict(item)
            item["요청수량"] = int(edited_row.get("요청수량") or 0)
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
