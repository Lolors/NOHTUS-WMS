from __future__ import annotations

import pandas as pd
import streamlit as st

import nohtus.pages.outbound as outbound_page
from nohtus.db import q
from nohtus.pages.outbound_business import page_outbound as _page_outbound
from nohtus.services.export_waiting import ensure_export_waiting_tables, save_export_waiting_order


def _export_title():
    country = str(st.session_state.get("export_waiting_country") or "").strip()
    export_no = str(st.session_state.get("export_waiting_number") or "").strip()
    if country and export_no:
        return f"{country}_{export_no}"
    return country or export_no or "수출대기"


def _load_editing_order():
    order_id = st.session_state.get("export_editing_order_id")
    if not order_id or st.session_state.get("_export_edit_loaded") == int(order_id):
        return
    ensure_export_waiting_tables()
    order = q("SELECT country,export_no,title,status FROM export_waiting_orders WHERE id=?", (int(order_id),))
    if order.empty or str(order.iloc[0]["status"]) != "waiting":
        st.session_state.pop("export_editing_order_id", None)
        return
    items = q(
        """SELECT source_inventory_id AS id,source_location AS 로케이션,company AS 사업장,
                  product_name AS 제품명,lot AS LOT,exp_date AS 유통기한,qty AS 요청수량
           FROM export_waiting_items WHERE order_id=? ORDER BY id""",
        (int(order_id),),
    )
    st.session_state["export_waiting_country"] = str(order.iloc[0]["country"] or "")
    st.session_state["export_waiting_number"] = str(order.iloc[0]["export_no"] or "")
    st.session_state["outbound_cart"] = items.to_dict("records") if not items.empty else []
    st.session_state["out_cart_editor_token"] = int(st.session_state.get("out_cart_editor_token", 0) or 0) + 1
    st.session_state["_export_edit_loaded"] = int(order_id)


def page_export_waiting():
    """출고지시 화면을 재사용하되 완료 시 재고를 추적 가능한 수출대기 건으로 저장한다."""
    ensure_export_waiting_tables()
    _load_editing_order()

    original_save_outbound_order = outbound_page.save_outbound_order
    original_update_outbound_order = outbound_page.update_outbound_order
    original_q = outbound_page.q
    original_title = st.title
    original_caption = st.caption
    original_markdown = st.markdown
    original_button = st.button
    original_success = st.success
    original_rerun = st.rerun
    original_text_input = st.text_input
    original_checkbox = st.checkbox
    original_info = st.info

    st.session_state.pop("editing_order_id", None)
    st.session_state.pop("editing_order_title", None)
    st.session_state["_outbound_screen_mode"] = "export_waiting"

    export_completed = {"done": False, "message": ""}
    export_fields_rendered = {"done": False}

    def patched_save_outbound_order(cart, title="", memo=""):
        result = save_export_waiting_order(
            cart,
            country=st.session_state.get("export_waiting_country"),
            export_no=st.session_state.get("export_waiting_number"),
            editing_order_id=st.session_state.get("export_editing_order_id"),
        )
        export_completed["done"] = True
        export_completed["message"] = (
            f"수출대기 {'수정' if st.session_state.get('export_editing_order_id') else '등록'} 완료: "
            f"{result['title']} / {result['row_count']}개 재고행 / 총 {result['total_qty']}EA → 로케이션 P"
        )
        return 0

    def patched_update_outbound_order(order_id, title, cart):
        return patched_save_outbound_order(cart, title)

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
            if "출고지시 저장 시 해당 제조번호/유통기한/로케이션의 현재고가 즉시 차감됩니다." in body:
                body = "등록 완료 시 선택 재고는 같은 사업장의 P로 이동하며, 취소 시 품목별 원래 위치로 복구됩니다."
            else:
                body = body.replace("출고지시", "수출대기")
        return original_caption(body, *args, **kwargs)

    def patched_markdown(body, *args, **kwargs):
        if isinstance(body, str):
            stripped = body.strip()
            if stripped == "### 매출처":
                result = original_markdown("### 수출 정보", *args, **kwargs)
                if not export_fields_rendered["done"]:
                    export_fields_rendered["done"] = True
                    c1, c2 = st.columns(2, gap="medium")
                    with c1:
                        original_text_input("수출번호", placeholder="수출번호를 입력하세요", key="export_waiting_number")
                    with c2:
                        original_text_input("국가", placeholder="국가를 입력하세요", key="export_waiting_country")
                return result
            body = body.replace("### 출고지시 장바구니", "### 수출대기 장바구니")
        return original_markdown(body, *args, **kwargs)

    def patched_text_input(label, *args, **kwargs):
        key = kwargs.get("key")
        if key in {"out_customer_term", "out_customer_manual_name"}:
            return ""
        if isinstance(label, str) and label == "출고지시서 제목":
            st.session_state["export_waiting_auto_title"] = _export_title()
            return original_text_input("수출대기 제목", disabled=True, key="export_waiting_auto_title")
        return original_text_input(label, *args, **kwargs)

    def patched_checkbox(label, *args, **kwargs):
        key = kwargs.get("key")
        if key == "out_customer_direct":
            return False
        if key in {"out_ignore_company", "out_manual_pick"}:
            return True
        if isinstance(label, str) and label == "사업장 구분 없이 특정 재고 선택":
            return True
        return original_checkbox(label, *args, **kwargs)

    def patched_info(body, *args, **kwargs):
        text = str(body or "")
        if any(x in text for x in ["거래처를 검색하거나 직접입력을 체크하세요", "매출처를 선택하면 해당 사업장 재고가 표시됩니다", "직접입력 매출처", "저장된 매출처"]):
            return None
        return original_info(body, *args, **kwargs)

    def patched_button(label, *args, **kwargs):
        if isinstance(label, str):
            label = {"지시완료 저장": "수출대기 수정 완료" if st.session_state.get("export_editing_order_id") else "수출대기 등록 완료",
                     "선택 재고 장바구니에 담기": "선택 재고 수출대기 장바구니에 담기"}.get(label, label)
        return original_button(label, *args, **kwargs)

    def patched_success(body, *args, **kwargs):
        return original_success(str(body).replace("출고지시", "수출대기") if isinstance(body, str) else body, *args, **kwargs)

    def patched_rerun(*args, **kwargs):
        if export_completed["done"]:
            st.session_state["_outbound_last_success"] = export_completed["message"]
            export_completed["done"] = False
            for key in ["export_waiting_number", "export_waiting_country", "export_waiting_auto_title", "export_editing_order_id", "_export_edit_loaded"]:
                st.session_state.pop(key, None)
        return original_rerun(*args, **kwargs)

    outbound_page.save_outbound_order = patched_save_outbound_order
    outbound_page.update_outbound_order = patched_update_outbound_order
    outbound_page.q = patched_q
    st.title, st.caption, st.markdown = patched_title, patched_caption, patched_markdown
    st.text_input, st.checkbox, st.info = patched_text_input, patched_checkbox, patched_info
    st.button, st.success, st.rerun = patched_button, patched_success, patched_rerun
    try:
        return _page_outbound()
    finally:
        outbound_page.save_outbound_order = original_save_outbound_order
        outbound_page.update_outbound_order = original_update_outbound_order
        outbound_page.q = original_q
        st.title, st.caption, st.markdown = original_title, original_caption, original_markdown
        st.text_input, st.checkbox, st.info = original_text_input, original_checkbox, original_info
        st.button, st.success, st.rerun = original_button, original_success, original_rerun
