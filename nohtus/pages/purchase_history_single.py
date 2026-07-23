from __future__ import annotations

from io import BytesIO

import pandas as pd
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


def _read_purchase_excel_for_company(payload, company):
    """노투스 파일은 7행을 헤더로, 그 외 사업장은 1행을 헤더로 읽는다."""
    header_row = 6 if company == "노투스" else 0
    sheets = pd.read_excel(BytesIO(payload), sheet_name=None, header=header_row)
    frames = []
    first_data_row = header_row + 2

    for sheet_name, frame in sheets.items():
        if frame is None or frame.empty:
            continue
        frame = frame.copy()
        frame.columns = [purchase_page._normalize_header(c) for c in frame.columns]
        frame["업로드시트"] = sheet_name
        frame["업로드행번호"] = range(first_data_row, first_data_row + len(frame))
        frames.append(frame)

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def page_purchase_history():
    original_render_query_items = purchase_page._render_query_items
    original_file_uploader = st.file_uploader
    original_import_purchase_history = purchase_page._import_purchase_history

    def patched_file_uploader(label, *args, **kwargs):
        if kwargs.get("key") == "purchase_history_upload":
            kwargs["type"] = ["xls", "xlsx"]
        return original_file_uploader(label, *args, **kwargs)

    def patched_import_purchase_history(uploaded_file, company):
        original_reader = purchase_page._read_purchase_excel

        def company_reader(payload):
            return _read_purchase_excel_for_company(payload, company)

        purchase_page._read_purchase_excel = company_reader
        try:
            return original_import_purchase_history(uploaded_file, company)
        finally:
            purchase_page._read_purchase_excel = original_reader

    purchase_page._render_query_items = _render_search_matches
    purchase_page._import_purchase_history = patched_import_purchase_history
    st.file_uploader = patched_file_uploader
    try:
        return all_products.page_purchase_history()
    finally:
        purchase_page._render_query_items = original_render_query_items
        purchase_page._import_purchase_history = original_import_purchase_history
        st.file_uploader = original_file_uploader
