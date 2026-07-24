from __future__ import annotations

from io import BytesIO

import pandas as pd
import streamlit as st

import nohtus.pages.purchase_history as purchase_page
import nohtus.pages.purchase_history_all_products as all_products
from nohtus.db import connect, q


NOTUS_COLUMN_ALIASES = {
    "거래일자": "매입일자",
    "품목명/규격": "제품명",
    "단가": "실단가",
}


def _render_search_matches(options):
    """검색어와 일부 일치하는 제품을 즉시 목록으로 보여주고 모두 조회 대상으로 사용한다."""
    keyword = st.text_input(
        "제품 검색",
        key="purchase_single_search",
        placeholder="제품명 일부 입력",
    )

    if not str(keyword or "").strip():
        return []

    matched = purchase_page._filter_product_options(options, keyword)
    if not matched:
        st.info("검색어와 일치하는 제품명이 없습니다.")
        return []

    result_df = pd.DataFrame({"검색결과": matched})
    st.dataframe(
        result_df,
        use_container_width=True,
        hide_index=True,
        height=min(420, 38 + len(result_df) * 35),
    )
    return [(idx + 1, product_name) for idx, product_name in enumerate(matched)]


def _read_purchase_excel_for_company(payload, company):
    """노투스 파일은 7행을 헤더로 읽고 전용 컬럼명을 공통 매입 컬럼명으로 변환한다."""
    header_row = 6 if company == "노투스" else 0
    sheets = pd.read_excel(BytesIO(payload), sheet_name=None, header=header_row)
    frames = []
    first_data_row = header_row + 2

    for sheet_name, frame in sheets.items():
        if frame is None or frame.empty:
            continue

        frame = frame.copy()
        frame.columns = [purchase_page._normalize_header(c) for c in frame.columns]

        if company == "노투스":
            frame = frame.rename(columns=NOTUS_COLUMN_ALIASES)

        frame["업로드시트"] = sheet_name
        frame["업로드행번호"] = range(first_data_row, first_data_row + len(frame))
        frames.append(frame)

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def _replace_company_purchase_data(company):
    """새 파일 업로드 전에 선택 사업장의 기존 매입가 데이터와 업로드 이력을 삭제한다."""
    with connect() as con:
        con.execute("DELETE FROM purchase_history WHERE business_name=?", (company,))
        con.execute("DELETE FROM purchase_uploads WHERE business_name=?", (company,))
        con.commit()


def _render_latest_upload_info():
    """사업장별로 현재 조회 데이터의 마지막 파일 업데이트 시각을 표시한다."""
    purchase_page._ensure_purchase_storage()
    uploads = q(
        """
        SELECT business_name, file_name, imported_at, row_count
        FROM purchase_uploads
        WHERE id IN (
            SELECT MAX(id)
            FROM purchase_uploads
            GROUP BY business_name
        )
        ORDER BY CASE business_name
            WHEN '노투스팜' THEN 1
            WHEN '노투스' THEN 2
            WHEN 'NOH' THEN 3
            ELSE 4
        END
        """
    )

    st.markdown("#### 파일 업데이트 현황")
    if uploads.empty:
        st.caption("아직 업로드된 매입가 파일이 없습니다.")
        return

    for row in uploads.itertuples(index=False):
        company = str(getattr(row, "business_name", "") or "-")
        file_name = str(getattr(row, "file_name", "") or "파일명 없음")
        imported_at = str(getattr(row, "imported_at", "") or "시간 확인 불가")
        row_count = int(getattr(row, "row_count", 0) or 0)
        st.caption(f"{company} · 마지막 업데이트 {imported_at} · {file_name} · {row_count:,}건")


def page_purchase_history():
    original_render_query_items = purchase_page._render_query_items
    original_render_import_box = purchase_page._render_import_box
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
            _replace_company_purchase_data(company)
            return original_import_purchase_history(uploaded_file, company)
        finally:
            purchase_page._read_purchase_excel = original_reader

    def patched_render_import_box():
        upload_col, status_col = st.columns(2, gap="large")
        with upload_col:
            original_render_import_box()
        with status_col:
            _render_latest_upload_info()

    purchase_page._render_query_items = _render_search_matches
    purchase_page._render_import_box = patched_render_import_box
    purchase_page._import_purchase_history = patched_import_purchase_history
    st.file_uploader = patched_file_uploader
    try:
        return all_products.page_purchase_history()
    finally:
        purchase_page._render_query_items = original_render_query_items
        purchase_page._render_import_box = original_render_import_box
        purchase_page._import_purchase_history = original_import_purchase_history
        st.file_uploader = original_file_uploader
