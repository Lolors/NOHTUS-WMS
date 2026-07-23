import streamlit as st

import nohtus.pages.mobile_stock as mobile_stock
import nohtus.pages.mobile_stock_layout_patch as base


_ORIGINAL_INJECT_CSS = base._inject_mobile_search_css
_ORIGINAL_RENDER_EXPIRY_TAB = base._render_expiry_tab


def _inject_mobile_search_css():
    _ORIGINAL_INJECT_CSS()
    st.markdown(
        """
        <style>
        @media (max-width: 768px) {
            /* 검색 결과 카드의 외부·내부 여백을 더 줄인다. */
            div[class*="st-key-mobile_result_row_"] div[data-testid="stVerticalBlockBorderWrapper"] {
                margin-bottom: 4px !important;
                border-radius: 10px !important;
            }
            div[class*="st-key-mobile_result_row_"] div[data-testid="stHorizontalBlock"] {
                min-height: 98px !important;
                padding: 1px 4px !important;
                column-gap: 4px !important;
                grid-template-columns: 98px minmax(0, 1fr) 82px 48px !important;
            }
            div[class*="st-key-mobile_result_row_"] div[data-testid="column"],
            div[class*="st-key-mobile_result_row_"] div[data-testid="stElementContainer"] {
                margin-top: 0 !important;
                margin-bottom: 0 !important;
            }

            /* 제품명과 사업장별 재고를 약 3pt 키운다. */
            .mobile-result-name {
                font-size: 18px !important;
                line-height: 1.25 !important;
                margin-bottom: 5px !important;
            }
            .mobile-result-company {
                font-size: 15.5px !important;
                line-height: 1.25 !important;
            }

            /* 총수량과 열기 버튼을 같은 높이·같은 중심선에 둔다. */
            .mobile-result-qty {
                height: 34px !important;
                min-height: 34px !important;
                display: flex !important;
                align-items: center !important;
                justify-content: center !important;
                line-height: 1 !important;
                margin: 0 !important;
                padding: 0 !important;
            }
            div[class*="st-key-mobile_result_row_"] div[data-testid="stButton"] {
                height: 34px !important;
                min-height: 34px !important;
                margin: 0 !important;
                display: flex !important;
                align-items: center !important;
                justify-content: center !important;
            }
            div[class*="st-key-mobile_result_row_"] div[data-testid="stButton"] button {
                height: 34px !important;
                min-height: 34px !important;
                margin: 0 !important;
                padding: 0 !important;
                display: flex !important;
                align-items: center !important;
                justify-content: center !important;
                line-height: 1 !important;
            }
            div[class*="st-key-mobile_result_row_"] div[data-testid="stButton"] button p {
                margin: 0 !important;
                line-height: 1 !important;
            }

            /* 기간 라디오와 비자료 제외를 같은 행에 배치한다. */
            div[class*="st-key-mobile_expiry_filter_row"] {
                margin-top: 8px !important;
                margin-bottom: 4px !important;
            }
            div[class*="st-key-mobile_expiry_filter_row"] div[data-testid="stHorizontalBlock"] {
                display: grid !important;
                grid-template-columns: minmax(0, 1fr) auto !important;
                align-items: center !important;
                gap: 6px !important;
                width: 100% !important;
            }
            div[class*="st-key-mobile_expiry_filter_row"] div[data-testid="column"] {
                width: auto !important;
                min-width: 0 !important;
                padding: 0 !important;
            }
            div[class*="st-key-mobile_expiry_filter_row"] div[data-testid="column"]:last-child {
                min-width: max-content !important;
                justify-self: end !important;
            }
            div[class*="st-key-mobile_expiry_exclude_bidata"] {
                width: auto !important;
                margin: 0 0 0 auto !important;
                display: flex !important;
                justify-content: flex-end !important;
            }
            div[class*="st-key-mobile_expiry_exclude_bidata"] label {
                width: auto !important;
                margin-left: auto !important;
                white-space: nowrap !important;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_expiry_tab():
    detail_product = str(st.session_state.get(base.base.EXPIRY_DETAIL_STATE_KEY, "") or "").strip()

    with st.container(key="mobile_expiry_filter_row"):
        period_col, exclude_col = st.columns([4.2, 1.3], gap="small", vertical_alignment="center")
        with period_col:
            period = st.radio(
                "기간",
                ["3개월 이내", "6개월 이내", "1년 이내"],
                index=2,
                horizontal=True,
                label_visibility="collapsed",
                key="mobile_expiry_period",
            )
        with exclude_col:
            exclude_bidata = st.checkbox(
                "비자료 제외",
                value=True,
                key="mobile_expiry_exclude_bidata",
            )

    term = base.base._live_input(
        "mobile_expiry_search_live",
        "mobile_expiry_search_value",
        "제품명 또는 별칭 검색",
    )

    df = base.base._filtered_expiry_df(period, exclude_bidata)
    if detail_product:
        base._render_expiry_detail(detail_product, df)
        return

    if df.empty:
        st.info("조건에 맞는 임박재고가 없습니다.")
        return

    available_names = df["product_name"].dropna().astype(str).drop_duplicates().tolist()
    if not term.strip():
        candidates = available_names
    else:
        matched = mobile_stock.mobile_product_candidates(term, limit=100)
        available_set = set(available_names)
        candidates = [name for name in matched if name in available_set]

    if not candidates:
        st.caption("검색 결과가 없습니다.")
        return

    candidates = sorted(
        candidates,
        key=lambda name: (
            df.loc[df["product_name"].astype(str) == str(name), "_expiry"].min(),
            str(name),
        ),
    )
    st.markdown(
        f'<div class="mobile-search-section">검색 결과 {len(candidates)}건</div>',
        unsafe_allow_html=True,
    )
    base._render_result_list(
        candidates,
        lambda name: base.base._expiry_meta(name, df),
        base.base.EXPIRY_DETAIL_STATE_KEY,
        "mobile_expiry_result",
    )


def page_mobile_stock_finder():
    original_inject = base._inject_mobile_search_css
    original_expiry = base._render_expiry_tab
    base._inject_mobile_search_css = _inject_mobile_search_css
    base._render_expiry_tab = _render_expiry_tab
    try:
        return base.page_mobile_stock_finder()
    finally:
        base._inject_mobile_search_css = original_inject
        base._render_expiry_tab = original_expiry
