from __future__ import annotations

import pandas as pd
import streamlit as st

import nohtus.pages.outbound as outbound_page
from nohtus.db import q
from nohtus.pages.outbound_business import page_outbound as _page_outbound
from nohtus.services.export_waiting import TRANSPORT_METHODS, ensure_export_waiting_tables, save_export_waiting_order

_ALL_COMPANY_SELECTION_KEYS = ("out_all_company_manual_pick", "out_ignore_company", "out_manual_pick")


def _export_title():
    country = str(st.session_state.get("export_waiting_country") or "").strip()
    buyer = str(st.session_state.get("export_waiting_buyer") or "").strip() or "미지정"
    transport_method = str(st.session_state.get("export_waiting_transport_method") or "").strip() or "미지정"
    return "-".join([part for part in (country, buyer, transport_method) if part]) or "수출대기"


def _load_editing_order():
    order_id = st.session_state.get("export_editing_order_id")
    if not order_id or st.session_state.get("_export_edit_loaded") == int(order_id):
        return
    ensure_export_waiting_tables()
    order = q("SELECT country,buyer,transport_method,export_no,title,status FROM export_waiting_orders WHERE id=?", (int(order_id),))
    if order.empty or str(order.iloc[0]["status"]) != "waiting":
        st.session_state.pop("export_editing_order_id", None)
        return
    items = q("""SELECT source_inventory_id AS id,source_location AS 로케이션,company AS 사업장,
                   product_name AS 제품명,lot AS LOT,exp_date AS 유통기한,qty AS 요청수량
            FROM export_waiting_items WHERE order_id=? ORDER BY id""", (int(order_id),))
    st.session_state["export_waiting_country"] = str(order.iloc[0]["country"] or "")
    st.session_state["export_waiting_buyer"] = str(order.iloc[0].get("buyer") or "")
    method = str(order.iloc[0].get("transport_method") or "").strip()
    st.session_state["export_waiting_transport_method"] = method if method in TRANSPORT_METHODS else "미지정"
    st.session_state["export_waiting_number"] = str(order.iloc[0]["export_no"] or "")
    st.session_state["outbound_cart"] = items.to_dict("records") if not items.empty else []
    st.session_state["out_cart_editor_token"] = int(st.session_state.get("out_cart_editor_token", 0) or 0) + 1
    st.session_state["_export_edit_loaded"] = int(order_id)


def page_export_waiting():
    ensure_export_waiting_tables()
    _load_editing_order()
    for key in _ALL_COMPANY_SELECTION_KEYS:
        st.session_state[key] = True

    original_save = outbound_page.save_outbound_order
    original_update = outbound_page.update_outbound_order
    original_q = outbound_page.q
    original_title, original_caption, original_markdown = st.title, st.caption, st.markdown
    original_button, original_success, original_rerun = st.button, st.success, st.rerun
    original_text_input, original_checkbox, original_info = st.text_input, st.checkbox, st.info

    st.session_state.pop("editing_order_id", None)
    st.session_state.pop("editing_order_title", None)
    st.session_state["_outbound_screen_mode"] = "export_waiting"
    completed = {"done": False, "message": ""}
    fields_rendered = {"done": False}

    def patched_save(cart, title="", memo=""):
        result = save_export_waiting_order(
            cart,
            country=st.session_state.get("export_waiting_country"),
            buyer=st.session_state.get("export_waiting_buyer"),
            transport_method=st.session_state.get("export_waiting_transport_method") or "미지정",
            export_no=st.session_state.get("export_waiting_number"),
            editing_order_id=st.session_state.get("export_editing_order_id"),
        )
        completed["done"] = True
        completed["message"] = f"수출대기 등록 완료: {result['title']} / 총 {result['total_qty']}EA → 로케이션 P"
        return 0

    def patched_q(sql, params=()):
        normalized = " ".join(str(sql or "").lower().split())
        if " from customers " in f" {normalized} ":
            return pd.DataFrame()
        return original_q(sql, params)

    def patched_title(body, *args, **kwargs):
        if isinstance(body, str) and body.strip() == "출고지시":
            body = "수출대기 수정" if st.session_state.get("export_editing_order_id") else "수출대기 등록"
        return original_title(body, *args, **kwargs)

    def patched_caption(body, *args, **kwargs):
        if isinstance(body, str):
            if "출고지시 저장 시" in body:
                body = "등록 완료 시 선택 재고는 같은 사업장의 P로 이동합니다. 바이어와 운송방식은 선택사항입니다."
            else:
                body = body.replace("출고지시", "수출대기")
        return original_caption(body, *args, **kwargs)

    def patched_markdown(body, *args, **kwargs):
        if isinstance(body, str) and body.strip() == "### 매출처":
            result = original_markdown("### 수출 정보", *args, **kwargs)
            if not fields_rendered["done"]:
                fields_rendered["done"] = True
                c1, c2, c3, c4 = st.columns(4, gap="medium")
                with c1:
                    original_text_input("국가", placeholder="국가를 입력하세요", key="export_waiting_country")
                with c2:
                    original_text_input("바이어 (선택)", placeholder="미입력 가능", key="export_waiting_buyer")
                with c3:
                    st.selectbox("운송방식 (선택)", TRANSPORT_METHODS, key="export_waiting_transport_method")
                with c4:
                    original_text_input("수출번호", placeholder="수출번호를 입력하세요", key="export_waiting_number")
            return result
        if isinstance(body, str):
            body = body.replace("### 출고지시 장바구니", "### 수출대기 장바구니")
        return original_markdown(body, *args, **kwargs)

    def patched_text_input(label, *args, **kwargs):
        key = kwargs.get("key")
        if key in {"out_customer_term", "out_customer_manual_name"}:
            return ""
        if label == "출고지시서 제목":
            st.session_state["export_waiting_auto_title"] = _export_title()
            return original_text_input("수출대기 제목", disabled=True, key="export_waiting_auto_title")
        return original_text_input(label, *args, **kwargs)

    def patched_checkbox(label, *args, **kwargs):
        key = kwargs.get("key")
        if key == "out_customer_direct":
            return False
        if key in _ALL_COMPANY_SELECTION_KEYS or label == "사업장 구분 없이 특정 재고 선택":
            if key:
                st.session_state[key] = True
            return True
        return original_checkbox(label, *args, **kwargs)

    def patched_info(body, *args, **kwargs):
        text = str(body or "")
        if any(x in text for x in ["거래처를 검색", "매출처를 선택", "직접입력 매출처", "저장된 매출처"]):
            return None
        return original_info(body, *args, **kwargs)

    def patched_button(label, *args, **kwargs):
        label = {"지시완료 저장": "수출대기 수정 완료" if st.session_state.get("export_editing_order_id") else "수출대기 등록 완료",
                 "선택 재고 장바구니에 담기": "선택 재고 수출대기 장바구니에 담기"}.get(label, label)
        return original_button(label, *args, **kwargs)

    def patched_rerun(*args, **kwargs):
        if completed["done"]:
            st.session_state["_outbound_last_success"] = completed["message"]
            completed["done"] = False
            for key in ["export_waiting_number", "export_waiting_country", "export_waiting_buyer", "export_waiting_transport_method", "export_waiting_auto_title", "export_editing_order_id", "_export_edit_loaded"]:
                st.session_state.pop(key, None)
        return original_rerun(*args, **kwargs)

    outbound_page.save_outbound_order = patched_save
    outbound_page.update_outbound_order = lambda order_id, title, cart: patched_save(cart, title)
    outbound_page.q = patched_q
    st.title, st.caption, st.markdown = patched_title, patched_caption, patched_markdown
    st.text_input, st.checkbox, st.info = patched_text_input, patched_checkbox, patched_info
    st.button, st.success, st.rerun = patched_button, lambda body, *a, **k: original_success(str(body).replace("출고지시", "수출대기"), *a, **k), patched_rerun
    try:
        return _page_outbound()
    finally:
        outbound_page.save_outbound_order, outbound_page.update_outbound_order, outbound_page.q = original_save, original_update, original_q
        st.title, st.caption, st.markdown = original_title, original_caption, original_markdown
        st.text_input, st.checkbox, st.info = original_text_input, original_checkbox, original_info
        st.button, st.success, st.rerun = original_button, original_success, original_rerun
