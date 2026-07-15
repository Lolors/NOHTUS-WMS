from __future__ import annotations

import streamlit as st

import nohtus.pages.outbound as outbound_page
from nohtus.pages.outbound_business import page_outbound as _page_outbound
from nohtus.services.export_waiting import move_cart_to_export_waiting


def page_export_waiting():
    """출고지시 화면을 재사용하되 완료 시 재고를 수출대기 위치 P로 이동한다."""
    original_save_outbound_order = outbound_page.save_outbound_order
    original_update_outbound_order = outbound_page.update_outbound_order
    original_title = st.title
    original_caption = st.caption
    original_markdown = st.markdown
    original_button = st.button
    original_success = st.success
    original_rerun = st.rerun

    st.session_state.pop("editing_order_id", None)
    st.session_state.pop("editing_order_title", None)
    st.session_state["_outbound_screen_mode"] = "export_waiting"

    export_completed = {"done": False, "message": ""}

    def patched_save_outbound_order(cart, title="", memo=""):
        customer = outbound_page._current_customer_payload()
        result = move_cart_to_export_waiting(
            cart,
            title=title,
            customer_name=customer.get("customer_name", ""),
        )
        export_completed["done"] = True
        export_completed["message"] = (
            f"수출대기 등록 완료: {result['row_count']}개 재고행 / "
            f"총 {result['total_qty']}EA → 로케이션 P"
        )
        return 0

    def patched_update_outbound_order(order_id, title, cart):
        return patched_save_outbound_order(cart, title)

    def patched_title(body, *args, **kwargs):
        if isinstance(body, str) and body.strip() == "출고지시":
            body = "수출대기 등록"
        return original_title(body, *args, **kwargs)

    def patched_caption(body, *args, **kwargs):
        if isinstance(body, str):
            if "출고지시 저장 시 해당 제조번호/유통기한/로케이션의 현재고가 즉시 차감됩니다." in body:
                body = "등록 완료 시 선택한 재고는 차감되지 않고 같은 사업장의 수출대기 로케이션 P로 이동됩니다."
            else:
                body = body.replace("출고지시", "수출대기")
        return original_caption(body, *args, **kwargs)

    def patched_markdown(body, *args, **kwargs):
        if isinstance(body, str):
            body = body.replace("### 출고지시 장바구니", "### 수출대기 장바구니")
        return original_markdown(body, *args, **kwargs)

    def patched_button(label, *args, **kwargs):
        if isinstance(label, str):
            replacements = {
                "지시완료 저장": "수출대기 등록 완료",
                "선택 재고 장바구니에 담기": "선택 재고 수출대기 장바구니에 담기",
            }
            label = replacements.get(label, label)
        return original_button(label, *args, **kwargs)

    def patched_success(body, *args, **kwargs):
        if isinstance(body, str):
            body = body.replace("출고지시", "수출대기")
        return original_success(body, *args, **kwargs)

    def patched_rerun(*args, **kwargs):
        if export_completed["done"]:
            st.session_state["_outbound_last_success"] = export_completed["message"]
            export_completed["done"] = False
        return original_rerun(*args, **kwargs)

    outbound_page.save_outbound_order = patched_save_outbound_order
    outbound_page.update_outbound_order = patched_update_outbound_order
    st.title = patched_title
    st.caption = patched_caption
    st.markdown = patched_markdown
    st.button = patched_button
    st.success = patched_success
    st.rerun = patched_rerun
    try:
        return _page_outbound()
    finally:
        outbound_page.save_outbound_order = original_save_outbound_order
        outbound_page.update_outbound_order = original_update_outbound_order
        st.title = original_title
        st.caption = original_caption
        st.markdown = original_markdown
        st.button = original_button
        st.success = original_success
        st.rerun = original_rerun
