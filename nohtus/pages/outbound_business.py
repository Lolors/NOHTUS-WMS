import streamlit as st

import nohtus.pages.outbound as outbound_page


def _render_last_sale_notice():
    with st.expander("최근거래일 갱신", expanded=False):
        st.info("최근거래일 갱신용 매출 파일 업로드는 [기초 > 거래처 관리] 메뉴에서 진행하세요.")


def page_outbound():
    original_renderer = outbound_page._render_last_sale_importer
    outbound_page._render_last_sale_importer = _render_last_sale_notice
    try:
        return outbound_page.page_outbound()
    finally:
        outbound_page._render_last_sale_importer = original_renderer
