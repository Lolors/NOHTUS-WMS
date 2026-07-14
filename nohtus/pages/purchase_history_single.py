from __future__ import annotations

import streamlit as st

import nohtus.pages.purchase_history as purchase_page
import nohtus.pages.purchase_history_all_products as all_products


def _render_single_query_item(options):
    """매입가 조회는 한 번에 제품 하나만 선택한다."""
    current = str(st.session_state.get("purchase_single_item") or "")
    search_col, select_col = st.columns([3, 7])

    with search_col:
        keyword = st.text_input(
            "제품 검색",
            key="purchase_single_search",
            placeholder="제품명 검색",
        )

    with select_col:
        filtered = purchase_page._filter_product_options(options, keyword, current)
        option_list = [""] + filtered
        index = option_list.index(current) if current in option_list else 0
        selected = st.selectbox(
            "조회 품목",
            option_list,
            index=index,
            key="purchase_single_item",
            format_func=lambda value: "제품을 선택하세요" if value == "" else value,
        )

    return [(1, selected)] if selected else []


def page_purchase_history():
    original_render_query_items = purchase_page._render_query_items
    purchase_page._render_query_items = _render_single_query_item
    try:
        return all_products.page_purchase_history()
    finally:
        purchase_page._render_query_items = original_render_query_items
