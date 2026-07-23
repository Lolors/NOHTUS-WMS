import html

import streamlit as st

import nohtus.pages.mobile_stock as mobile_stock
import nohtus.pages.mobile_stock_live_fix as base


_ORIGINAL_INJECT_CSS = base._inject_mobile_search_css
_ORIGINAL_RENDER_RESULT_LIST = base._render_result_list
_ORIGINAL_RENDER_RECENT_LINKS = base._render_recent_links
_ORIGINAL_RENDER_EXPIRY = base._render_expiry_inventory


def _inject_mobile_search_css():
    _ORIGINAL_INJECT_CSS()
    st.markdown(
        """
        <style>
        @media (max-width: 768px) {
            .mobile-result-row {
                min-height: 74px !important;
                padding-right: 150px !important;
            }
            .mobile-result-total {
                right: 72px !important;
                font-size: 17px !important;
                font-weight: 800 !important;
                color: #1f2937 !important;
            }
            .mobile-result-arrow { display: none !important; }

            div[class*="st-key-mobile_stock_result_"] div[data-testid="stButton"],
            div[class*="st-key-mobile_expiry_result_"] div[data-testid="stButton"] {
                width: 54px !important;
                margin-left: auto !important;
            }
            div[class*="st-key-mobile_stock_result_"] div[data-testid="stButton"] button,
            div[class*="st-key-mobile_expiry_result_"] div[data-testid="stButton"] button {
                width: 54px !important;
                height: 34px !important;
                min-height: 34px !important;
                padding: 0 10px !important;
                border: 1px solid #d8dde6 !important;
                border-radius: 9px !important;
                background: #ffffff !important;
                color: #334155 !important;
                box-shadow: none !important;
                font-size: 12px !important;
                font-weight: 700 !important;
            }
            .mobile-result-click div[data-testid="stButton"] {
                margin-top: -54px !important;
                margin-bottom: 20px !important;
                padding-right: 8px !important;
            }
            .mobile-result-click div[data-testid="stButton"] button {
                color: #334155 !important;
                background: #ffffff !important;
            }

            div[class*="st-key-recent_stock_"] div[data-testid="stButton"],
            div[class*="st-key-recent_expiry_"] div[data-testid="stButton"] {
                margin: -5px 0 !important;
            }
            div[class*="st-key-recent_stock_"] div[data-testid="stButton"] button,
            div[class*="st-key-recent_expiry_"] div[data-testid="stButton"] button {
                min-height: 22px !important;
                height: 22px !important;
                padding: 0 !important;
                line-height: 1.1 !important;
            }

            .mobile-expiry-title {
                margin: 0 !important;
                padding: 0 !important;
                font-size: 1.55rem !important;
                line-height: 1.25 !important;
                font-weight: 700 !important;
            }
            div[class*="st-key-mobile_expiry_exclude_bidata"] {
                display: flex !important;
                justify-content: flex-end !important;
                align-items: center !important;
                padding-top: 2px !important;
            }
            div[class*="st-key-mobile_expiry_exclude_bidata"] label {
                white-space: nowrap !important;
                font-size: 13px !important;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_result_list(candidates, meta_getter, state_key, key_prefix):
    st.markdown('<div class="mobile-result-list">', unsafe_allow_html=True)
    for index, name in enumerate(candidates):
        _, total_qty, summary = meta_getter(name)
        last_class = " last-row" if index == len(candidates) - 1 else ""
        thumbnail_uri = base._product_thumbnail_uri(name)
        thumbnail_html = (
            f'<img src="{thumbnail_uri}" alt="{html.escape(str(name))}">' if thumbnail_uri else "📷"
        )
        st.markdown(
            f"""
            <div class="mobile-result-row{last_class}">
                <div class="mobile-result-thumb">{thumbnail_html}</div>
                <div class="mobile-result-name">{html.escape(str(name))}</div>
                <div class="mobile-result-company">{summary or '재고 없음'}</div>
                <div class="mobile-result-total">{total_qty:,}개</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown('<div class="mobile-result-click">', unsafe_allow_html=True)
        clicked = st.button("열기", key=f"{key_prefix}_{index}_{name}")
        st.markdown("</div>", unsafe_allow_html=True)
        if clicked:
            st.session_state[state_key] = name
            mobile_stock._remember_recent_search(name)
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)


def _render_recent_links(names, state_key, key_prefix):
    st.markdown('<div class="mobile-search-section">최근 검색어</div>', unsafe_allow_html=True)
    for index, name in enumerate(names):
        if st.button(str(name), key=f"{key_prefix}_{index}_{name}"):
            st.session_state[state_key] = name
            mobile_stock._remember_recent_search(name)
            st.rerun()


def _render_expiry_inventory():
    title_col, exclude_col = st.columns([3.4, 1.6], gap="small", vertical_alignment="center")
    with title_col:
        st.markdown('<div class="mobile-expiry-title">임박재고</div>', unsafe_allow_html=True)
    with exclude_col:
        exclude_bidata = st.checkbox(
            "비자료 제외",
            value=True,
            key="mobile_expiry_exclude_bidata",
        )

    period = st.radio(
        "기간",
        ["전체", "3개월 이내", "6개월 이내", "1년 이내"],
        horizontal=True,
        label_visibility="collapsed",
        key="mobile_expiry_period",
    )

    df = base._filtered_expiry_df(period, exclude_bidata)
    detail_product = str(st.session_state.get(base.EXPIRY_DETAIL_STATE_KEY, "") or "").strip()
    if detail_product:
        base._render_expiry_detail(detail_product, df)
        return

    term = base._live_input(
        "mobile_expiry_search_live",
        "mobile_expiry_search_value",
        "제품명 또는 별칭 검색",
    )
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
    _render_result_list(
        candidates,
        lambda name: base._expiry_meta(name, df),
        base.EXPIRY_DETAIL_STATE_KEY,
        "mobile_expiry_result",
    )


def page_mobile_stock_finder():
    original_inject = base._inject_mobile_search_css
    original_result = base._render_result_list
    original_recent = base._render_recent_links
    original_expiry = base._render_expiry_inventory
    base._inject_mobile_search_css = _inject_mobile_search_css
    base._render_result_list = _render_result_list
    base._render_recent_links = _render_recent_links
    base._render_expiry_inventory = _render_expiry_inventory
    try:
        return base.page_mobile_stock_finder()
    finally:
        base._inject_mobile_search_css = original_inject
        base._render_result_list = original_result
        base._render_recent_links = original_recent
        base._render_expiry_inventory = original_expiry
