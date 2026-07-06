import streamlit as st

from nohtus.services.products import product_options

def page_search():
    st.title("제품 검색")
    term = st.text_input("검색어")
    opts = product_options(term)
    st.dataframe(opts.rename(columns={"standard_name":"표준제품명","warehouse_name":"전산상 명칭","aliases":"별칭"}), hide_index=True, use_container_width=True)
