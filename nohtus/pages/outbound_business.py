import streamlit as st

import nohtus.pages.outbound as outbound_page


def _hide_last_sale_importer():
    return None


def page_outbound():
    original_renderer = outbound_page._render_last_sale_importer
    original_text_input = st.text_input
    original_checkbox = st.checkbox

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
            c1, spacer, c2, blank = st.columns([1.25, 0.08, 1.25, 5.4], gap="small")
            with c1:
                ignore_value = original_checkbox(label, *args, **kwargs)
            with c2:
                manual_value = original_checkbox("특정 재고 선택", value=False, key="out_manual_pick")
            checkbox_skip_values["out_manual_pick"] = bool(manual_value)
            return ignore_value
        return original_checkbox(label, *args, **kwargs)

    outbound_page._render_last_sale_importer = _hide_last_sale_importer
    st.text_input = patched_text_input
    st.checkbox = patched_checkbox
    try:
        return outbound_page.page_outbound()
    finally:
        outbound_page._render_last_sale_importer = original_renderer
        st.text_input = original_text_input
        st.checkbox = original_checkbox
