from __future__ import annotations

import streamlit as st

import nohtus.pages.purchase_history as purchase_page
import nohtus.pages.purchase_history_all_products as all_products


def _render_search_matches(options):
    """선택박스 없이 검색어와 일치하는 모든 제품을 한 번에 조회한다."""
    keyword = st.text_input(
        "제품 검색",
        key="purchase_single_search",
        placeholder="제품명 일부 입력",
    )

    if not str(keyword or "").strip():
        st.caption("제품명을 입력하면 일치하는 모든 과거 매입내역을 조회합니다.")
        return []

    matched = purchase_page._filter_product_options(options, keyword)
    if not matched:
        st.caption("검색어와 일치하는 제품명이 없습니다.")
        return []

    st.caption(f"검색된 제품 {len(matched)}개 · 조회 시 관련 매입내역을 모두 표시합니다.")
    return [(idx + 1, product_name) for idx, product_name in enumerate(matched)]


def _file_uploader_with_legacy_excel(label, *args, **kwargs):
    """매입내역 업로더에서 구형 .xls와 신형 .xlsx를 모두 허용한다."""
    if kwargs.get("key") == "purchase_history_upload":
        kwargs["type"] = ["xls", "xlsx"]
    return st.file_uploader(label, *args, **kwargs)


def page_purchase_history():
    original_render_query_items = purchase_page._render_query_items
    original_file_uploader = st.file_uploader

    def patched_file_uploader(label, *args, **kwargs):
        if kwargs.get("key") == "purchase_history_upload":
            kwargs["type"] = ["xls", "xlsx"]
        return original_file_uploader(label, *args, **kwargs)

    purchase_page._render_query_items = _render_search_matches
    st.file_uploader = patched_file_uploader
    try:
        return all_products.page_purchase_history()
    finally:
        purchase_page._render_query_items = original_render_query_items
        st.file_uploader = original_file_uploader
