from __future__ import annotations

import pandas as pd
import streamlit as st

from nohtus.config import COMPANIES
from nohtus.db import connect, q
from nohtus.dates import display_date_only
from nohtus.services.export_waiting import cancel_export_waiting_order, confirm_export_waiting_order, ensure_export_waiting_tables

STATUS_LABELS = {"waiting": "수출대기", "confirmed": "수출확정", "cancelled": "취소됨"}


def _customer_options(company, term):
    with connect() as con:
        columns = {r[1] for r in con.execute("PRAGMA table_info(customers)").fetchall()}
    if "customer_name" not in columns:
        return pd.DataFrame(columns=["customer_code", "customer_name", "company"])
    code_col = next((c for c in ["customer_code", "erp_code", "code"] if c in columns), None)
    company_col = "company" if "company" in columns else None
    select_code = f"COALESCE({code_col},'')" if code_col else "''"
    select_company = company_col if company_col else "''"
    clauses, params = ["TRIM(COALESCE(customer_name,''))<>''"], []
    if company_col and company:
        clauses.append("company=?"); params.append(company)
    if str(term or "").strip():
        clauses.append("customer_name LIKE ?"); params.append(f"%{str(term).strip()}%")
    sql = (f"SELECT {select_code} AS customer_code, customer_name, {select_company} AS company "
           f"FROM customers WHERE {' AND '.join(clauses)} ORDER BY customer_name LIMIT 100")
    return q(sql, tuple(params))


def _order_items(order_id):
    df = q("""SELECT company AS 사업장,source_location AS 원래로케이션,waiting_location AS 현재로케이션,
                    product_name AS 제품명,lot AS LOT,exp_date AS 유통기한,qty AS 수량
             FROM export_waiting_items WHERE order_id=?
             ORDER BY company,product_name,lot,exp_date,source_location""", (int(order_id),))
    if not df.empty:
        df["유통기한"] = df["유통기한"].apply(display_date_only)
    return df


def page_saved_export_waiting():
    ensure_export_waiting_tables()
    st.title("저장된 수출대기")
    st.caption("수출대기 건을 수정·취소하거나 ERP 수출 매출처를 선택해 수출확정합니다.")
    msg = st.session_state.pop("_export_waiting_message", None)
    if msg: st.success(msg)

    orders = q("""SELECT id,export_no,country,buyer,transport_method,title,status,erp_company,erp_customer_name,
                         created_at,updated_at,confirmed_at,cancelled_at
                  FROM export_waiting_orders ORDER BY id DESC""")
    if orders.empty:
        st.info("저장된 수출대기 건이 없습니다."); return

    view = orders.copy()
    view["상태"] = view["status"].map(STATUS_LABELS).fillna(view["status"])
    view = view.rename(columns={"id":"번호","country":"국가","buyer":"바이어","transport_method":"운송방식","export_no":"수출번호","title":"제목",
                                "erp_company":"ERP사업장","erp_customer_name":"ERP매출처","created_at":"등록일"})
    view["바이어"] = view["바이어"].fillna("").astype(str).replace("", "미지정")
    view["운송방식"] = view["운송방식"].fillna("").astype(str).replace("", "미지정")
    st.dataframe(view[["번호","상태","국가","바이어","운송방식","수출번호","제목","ERP사업장","ERP매출처","등록일"]], hide_index=True, use_container_width=True)

    labels = [f"#{int(r.id)} | {STATUS_LABELS.get(r.status,r.status)} | {r.title}" for r in orders.itertuples()]
    selected = orders.iloc[labels.index(st.selectbox("수출대기 건 선택", labels))]
    order_id, status = int(selected["id"]), str(selected["status"])
    st.markdown(f"### {selected['title']}")
    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("상태", STATUS_LABELS.get(status,status))
    c2.metric("국가", str(selected["country"] or "-"))
    c3.metric("바이어", str(selected["buyer"] or "미지정"))
    c4.metric("운송방식", str(selected["transport_method"] or "미지정"))
    c5.metric("수출번호", str(selected["export_no"] or "-"))
    items = _order_items(order_id)
    st.dataframe(items, hide_index=True, use_container_width=True)
    total_qty = int(items["수량"].sum()) if not items.empty else 0
    st.caption(f"총 {len(items)}개 재고행 / {total_qty}EA")

    if status == "cancelled":
        st.error("취소된 건입니다. 모든 품목은 등록 당시 원래 로케이션으로 복구되었습니다."); return
    if status == "confirmed":
        st.success(f"수출확정 완료 | {selected['erp_company'] or '-'} / {selected['erp_customer_name'] or '-'}"); return

    edit_col,cancel_col = st.columns(2)
    with edit_col:
        if st.button("수출대기 수정", type="primary", use_container_width=True):
            st.session_state["export_editing_order_id"] = order_id
            st.session_state.pop("_export_edit_loaded", None)
            st.session_state["page"] = "수출대기 등록"
            st.rerun()
    with cancel_col:
        if st.button("수출대기 취소", use_container_width=True):
            st.session_state["confirm_export_cancel_id"] = order_id

    if st.session_state.get("confirm_export_cancel_id") == order_id:
        st.warning("취소하면 모든 품목이 각각 등록 전 원래 로케이션으로 돌아갑니다.")
        no_col,yes_col = st.columns(2)
        with no_col:
            if st.button("취소하지 않기", use_container_width=True):
                st.session_state.pop("confirm_export_cancel_id", None); st.rerun()
        with yes_col:
            if st.button("원래 위치로 복구하고 취소", type="primary", use_container_width=True):
                try:
                    cancel_export_waiting_order(order_id)
                    st.session_state.pop("confirm_export_cancel_id", None)
                    st.session_state["_export_waiting_message"] = f"{selected['title']} 수출대기를 취소하고 원래 위치로 복구했습니다."
                    st.rerun()
                except Exception as exc: st.error(str(exc))

    st.markdown("---"); st.markdown("### 수출확정")
    st.caption("ERP 사업장과 실제 수출 매출처를 선택하면 P 재고가 최종 차감됩니다.")
    default_company = str(items.iloc[0]["사업장"] or "") if not items.empty else ""
    default_index = COMPANIES.index(default_company) if default_company in COMPANIES else 0
    erp_company = st.selectbox("ERP 매출 사업장", COMPANIES, index=default_index, key=f"export_confirm_company_{order_id}")
    term = st.text_input("ERP 수출 매출처 검색", placeholder="매출처명 일부를 입력하세요", key=f"export_customer_term_{order_id}")
    customers = _customer_options(erp_company, term)
    if customers.empty:
        st.warning("해당 사업장의 ERP 매출처가 없습니다. 거래처 관리에서 ERP 매출처 목록을 먼저 등록하거나 갱신하세요."); return
    customer_labels = [f"{str(r.customer_code or '').strip() or '-'} | {r.customer_name}" for r in customers.itertuples()]
    customer = customers.iloc[customer_labels.index(st.selectbox("ERP 수출 매출처", customer_labels, key=f"export_customer_select_{order_id}"))]
    st.info(f"확정 대상: {selected['title']} → {erp_company} / {customer['customer_name']}")
    if st.button("수출확정", type="primary", use_container_width=True):
        try:
            confirm_export_waiting_order(order_id, erp_company=erp_company,
                                         customer_code=customer.get("customer_code", ""),
                                         customer_name=customer.get("customer_name", ""))
            st.session_state["_export_waiting_message"] = f"{selected['title']} 수출확정 완료: P 재고 {total_qty}EA를 차감했습니다."
            st.rerun()
        except Exception as exc: st.error(str(exc))
