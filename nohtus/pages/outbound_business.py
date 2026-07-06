import pandas as pd
import streamlit as st

import nohtus.pages.outbound as outbound_page


def _hide_last_sale_importer():
    return None


def page_outbound():
    original_renderer = outbound_page._render_last_sale_importer
    original_text_input = st.text_input
    original_checkbox = st.checkbox
    original_data_editor = st.data_editor
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
        if key == "out_ignore_company":
            manual_value = original_checkbox("특정 재고 선택", value=False, key="out_manual_pick")
            checkbox_skip_values["out_manual_pick"] = bool(manual_value)
            return False
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
    outbound_page._manual_pick_rows = original_manual_pick_rows
    st.text_input = patched_text_input
    st.checkbox = patched_checkbox
    st.data_editor = patched_data_editor
    try:
        return outbound_page.page_outbound()
    finally:
        outbound_page._render_last_sale_importer = original_renderer
        outbound_page._manual_pick_rows = original_manual_pick_rows
        st.text_input = original_text_input
        st.checkbox = original_checkbox
        st.data_editor = original_data_editor
