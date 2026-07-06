import pandas as pd
import streamlit as st

import nohtus.pages.outbound as outbound_page


def _hide_last_sale_importer():
    return None


def page_outbound():
    original_renderer = outbound_page._render_last_sale_importer
    original_save_with_customer = outbound_page._save_outbound_cart_with_customer
    original_text_input = st.text_input
    original_checkbox = st.checkbox
    original_data_editor = st.data_editor
    original_markdown = st.markdown
    original_caption = st.caption
    original_manual_pick_rows = outbound_page._manual_pick_rows

    st.markdown(
        """
        <style>
        div[data-testid="stCheckbox"] label, div[data-testid="stCheckbox"] p {
            white-space: nowrap !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    checkbox_skip_values = {}

    def all_company_manual_pick_value():
        return bool(st.session_state.get("out_all_company_manual_pick", False))

    def patched_save_outbound_cart_with_customer(cart, title, customer_payload):
        outbound_page._ensure_outbound_customer_columns()
        editing_id = st.session_state.get("editing_order_id")
        if editing_id:
            outbound_page.update_outbound_order(int(editing_id), title, cart)
            outbound_page._save_outbound_customer(int(editing_id), customer_payload)
            msg = f"출고지시서 #{int(editing_id)} 수정 저장 완료"
            st.session_state.pop("editing_order_id", None)
            st.session_state.pop("editing_order_title", None)
        else:
            oid = outbound_page.save_outbound_order(cart, title)
            outbound_page._save_outbound_customer(int(oid), customer_payload)
            msg = f"출고지시서 #{int(oid)} 저장 완료"

        for k in [
            "outbound_cart",
            "out_customer_term",
            "out_customer_select",
            "_out_customer_label",
            "out_selected_customer",
            "out_customer_direct",
            "out_customer_manual_name",
            "out_product_term",
            "out_req_qty",
            "out_rec_editor",
            "out_manual_editor",
            "out_ignore_company",
            "out_manual_pick",
            "out_all_company_manual_pick",
            "out_expiry_short_first",
            "pending_outbound_save",
            "pending_outbound_expiry_warnings",
            "pending_outbound_add_rows",
            "pending_outbound_add_warnings",
        ]:
            st.session_state.pop(k, None)
        st.session_state["outbound_cart"] = []
        st.session_state["out_cart_editor_token"] = int(st.session_state.get("out_cart_editor_token", 0) or 0) + 1
        st.session_state["_outbound_reset_inputs_pending"] = True
        st.session_state["_outbound_last_success"] = msg
        st.rerun()

    def patched_markdown(body, *args, **kwargs):
        if isinstance(body, str) and body.strip() == "### 재고 선택 옵션":
            return None
        result = original_markdown(body, *args, **kwargs)
        if isinstance(body, str) and body.strip() == "### 제품 선택":
            value = original_checkbox(
                "사업장 구분 없이 특정 재고 선택",
                value=all_company_manual_pick_value(),
                key="out_all_company_manual_pick",
            )
            checkbox_skip_values["out_ignore_company"] = bool(value)
            checkbox_skip_values["out_manual_pick"] = bool(value)
        return result

    def patched_caption(body, *args, **kwargs):
        if isinstance(body, str) and (
            "매출처 사업장과 관계없이" in body
            or "유통기한 우선 추천 없이" in body
            or "추천 범위: 전체 사업장 재고" in body
        ):
            return None
        return original_caption(body, *args, **kwargs)

    def patched_text_input(label, *args, **kwargs):
        if kwargs.get("key") == "out_customer_term":
            search_col, direct_col = st.columns([8, 2], gap="small")
            with search_col:
                value = original_text_input(label, *args, **kwargs)
            with direct_col:
                st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
                direct_value = original_checkbox("직접입력", value=False, key="out_customer_direct")
            checkbox_skip_values["out_customer_direct"] = bool(direct_value)
            return value
        return original_text_input(label, *args, **kwargs)

    def patched_checkbox(label, *args, **kwargs):
        key = kwargs.get("key")
        if key in checkbox_skip_values:
            return checkbox_skip_values[key]
        if key in ["out_ignore_company", "out_manual_pick"]:
            return all_company_manual_pick_value()
        return original_checkbox(label, *args, **kwargs)

    def patched_data_editor(data, *args, **kwargs):
        if kwargs.get("key") == "out_manual_editor" and isinstance(data, pd.DataFrame):
            work = data.copy()
            if "요청수량" in work.columns:
                work = work.drop(columns=["요청수량"])
            edited = original_data_editor(work, *args, **kwargs)
            if isinstance(edited, pd.DataFrame):
                result = edited.copy()
                result["요청수량"] = 0
                selected_indexes = [idx for idx, row in result.iterrows() if bool(row.get("선택", False))]
                remain = int(st.session_state.get("out_req_qty", 0) or 0)
                for idx in selected_indexes:
                    available = int(result.at[idx, "현재수량"] or 0) if "현재수량" in result.columns else remain
                    use_qty = min(remain, available) if remain > 0 else 0
                    result.at[idx, "요청수량"] = use_qty
                    remain -= use_qty
                    if remain <= 0:
                        break
                return result
            return edited
        return original_data_editor(data, *args, **kwargs)

    outbound_page._render_last_sale_importer = _hide_last_sale_importer
    outbound_page._save_outbound_cart_with_customer = patched_save_outbound_cart_with_customer
    outbound_page._manual_pick_rows = original_manual_pick_rows
    st.markdown = patched_markdown
    st.caption = patched_caption
    st.text_input = patched_text_input
    st.checkbox = patched_checkbox
    st.data_editor = patched_data_editor
    try:
        return outbound_page.page_outbound()
    finally:
        outbound_page._render_last_sale_importer = original_renderer
        outbound_page._save_outbound_cart_with_customer = original_save_with_customer
        outbound_page._manual_pick_rows = original_manual_pick_rows
        st.markdown = original_markdown
        st.caption = original_caption
        st.text_input = original_text_input
        st.checkbox = original_checkbox
        st.data_editor = original_data_editor
