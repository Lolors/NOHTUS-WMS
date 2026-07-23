import streamlit as st

import nohtus.pages.mobile_stock_layout_patch as base


_ORIGINAL_INJECT_CSS = base._inject_mobile_search_css


def _inject_mobile_search_css():
    _ORIGINAL_INJECT_CSS()
    st.markdown(
        """
        <style>
        @media (max-width: 768px) {
            /* 검색 결과 카드의 불필요한 내부 여백을 줄인다. */
            div[class*="st-key-mobile_result_row_"] div[data-testid="stVerticalBlockBorderWrapper"] {
                margin-bottom: 6px !important;
            }
            div[class*="st-key-mobile_result_row_"] div[data-testid="stHorizontalBlock"] {
                min-height: 100px !important;
                padding: 2px 6px !important;
                column-gap: 6px !important;
                grid-template-columns: 98px minmax(0, 1fr) 82px 48px !important;
            }

            /* 총수량과 열기 버튼을 같은 높이와 수직 위치로 맞춘다. */
            .mobile-result-qty {
                height: 32px !important;
                min-height: 32px !important;
                display: flex !important;
                align-items: center !important;
                justify-content: center !important;
                line-height: 32px !important;
                margin: 0 !important;
            }
            div[class*="st-key-mobile_result_row_"] div[data-testid="stButton"],
            div[class*="st-key-mobile_result_row_"] div[data-testid="stButton"] button {
                height: 32px !important;
                min-height: 32px !important;
                margin: 0 !important;
            }

            /* 임박재고 기간 필터 위에 작은 여백을 둔다. */
            div[class*="st-key-mobile_expiry_period"] {
                margin-top: 8px !important;
            }

            /* 검색창 아래 비자료 제외를 확실히 오른쪽 끝에 고정한다. */
            div[class*="st-key-mobile_expiry_check_row"] {
                width: 100% !important;
                margin-top: -4px !important;
                margin-bottom: 0 !important;
            }
            div[class*="st-key-mobile_expiry_check_row"] div[data-testid="stHorizontalBlock"] {
                display: grid !important;
                grid-template-columns: minmax(0, 1fr) auto !important;
                width: 100% !important;
                gap: 0 !important;
                align-items: center !important;
            }
            div[class*="st-key-mobile_expiry_check_row"] div[data-testid="column"]:first-child {
                display: block !important;
                min-width: 0 !important;
            }
            div[class*="st-key-mobile_expiry_check_row"] div[data-testid="column"]:last-child {
                width: auto !important;
                min-width: max-content !important;
                justify-self: end !important;
                padding: 0 !important;
            }
            div[class*="st-key-mobile_expiry_exclude_bidata"] {
                width: auto !important;
                margin-left: auto !important;
                display: flex !important;
                justify-content: flex-end !important;
            }
            div[class*="st-key-mobile_expiry_exclude_bidata"] > div,
            div[class*="st-key-mobile_expiry_exclude_bidata"] label {
                width: auto !important;
                margin-left: auto !important;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def page_mobile_stock_finder():
    original_inject = base._inject_mobile_search_css
    base._inject_mobile_search_css = _inject_mobile_search_css
    try:
        return base.page_mobile_stock_finder()
    finally:
        base._inject_mobile_search_css = original_inject
