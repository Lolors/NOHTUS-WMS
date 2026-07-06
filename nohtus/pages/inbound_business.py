import streamlit as st

import nohtus.pages.inbound as inbound_page


def page_inbound():
    original_text_input = st.text_input

    def safe_text_input(*args, **kwargs):
        value = original_text_input(*args, **kwargs)
        return "" if value is None else value

    st.text_input = safe_text_input
    try:
        return inbound_page.page_inbound()
    finally:
        st.text_input = original_text_input
