import html

import streamlit as st

import nohtus.pages.mobile_stock as mobile_stock
import nohtus.pages.mobile_stock_live_fix as base


_ORIGINAL_INJECT_CSS = base._inject_mobile_search_css
_ORIGINAL_RENDER_RECENT_LINKS = base._render_recent_links


def _inject_mobile_search_css():
    _ORIGINAL_INJECT_CSS()
    st.markdown(
        """
        <style>
        header[data-testid="stHeader"] {
            height: 0 !important;
            min-height: 0 !important;
        }
        div[data-testid="stAppViewContainer"] .main .block-container {
            padding-top: 0 !important;
            margin-top: 0 !important;
        }
        @media (max-width: 768px) {
            div[data-testid="stAppViewContainer"] .main .block-container {
                padding: 0 .65rem 1.5rem !important;
            }

            div[data-testid="stTabs"] [data-baseweb="tab-list"] {
                gap: 0 !important;
                border-bottom: 1px solid #e5e7eb !important;
                margin-bottom: 10px !important;
            }
            div[data-testid="stTabs"] button[data-baseweb="tab"] {
                flex: 1 1 0 !important;
                justify-content: center !important;
                min-height: 42px !important;
                padding: 0 8px !important;
                font-size: 14px !important;
                font-weight: 650 !important;
            }
            div[data-testid="stTabs"] button[aria-selected="true"] {
                font-weight: 800 !important;
            }

            .mobile-result-grid div[data-testid="stVerticalBlockBorderWrapper"] {
                border: 0 !important;
                border-bottom: 1px solid #edf0f4 !important;
                border-radius: 0 !important;
                box-shadow: none !important;
                background: #fff !important;
                padding: 0 !important;
            }
            .mobile-result-grid div[data-testid="stVerticalBlockBorderWrapper"]:last-child {
                border-bottom: 0 !important;
            }
            .mobile-result-grid div[data-testid="stHorizontalBlock"] {
                align-items: center !important;
                gap: .45rem !important;
                min-height: 72px !important;
                padding: 7px 4px !important;
            }
            .mobile-result-grid div[data-testid="stImage"] {
                width: 48px !important;
                height: 48px !important;
                margin: 0 !important;
            }
            .mobile-result-grid div[data-testid="stImage"] img {
                width: 48px !important;
                height: 48px !important;
                object-fit: contain !important;
                border-radius: 8px !important;
                background: #fff !important;
            }
            .mobile-empty-thumb {
                width: 48px;
                height: 48px;
                border-radius: 8px;
                background: #f8fafc;
            }
            .mobile-result-name {
                font-size: 14px;
                line-height: 1.32;
                font-weight: 750;
                color: #182033;
                margin-bottom: 4px;
                word-break: keep-all;
            }
            .mobile-result-company {
                font-size: 11.5px;
                line-height: 1.35;
                color: #727b8d;
                overflow: hidden;
                white-space: nowrap;
                text-overflow: ellipsis;
            }
            .mobile-result-qty {
                width: 100%;
                text-align: center;
                font-size: 17px;
                line-height: 1;
                font-weight: 850;
                color: #1f2937;
                white-space: nowrap;
            }
            .mobile-result-grid div[data-testid="stButton"] button {
                width: 100% !important;
                min-height: 32px !important;
                height: 32px !important;
                padding: 0 4px !important;
                border: 0 !important;
                border-radius: 0 !important;
                background: transparent !important;
                color: #2563eb !important;
                box-shadow: none !important;
                font-size: 13px !important;
                font-weight: 750 !important;
            }

            div[class*="st-key-recent_stock_"] div[data-testid="stButton"],
            div[class*="st-key-recent_expiry_"] div[data-testid="stButton"] {
                margin: -6px 0 !important;
            }
            div[class*="st-key-recent_stock_"] div[data-testid="stButton"] button,
            div[class*="st-key-recent_expiry_"] div[data-testid="stButton"] button {
                min-height: 21px !important;
                height: 21px !important;
                padding: 0 !important;
                line-height: 1 !important;
            }

            .mobile-expiry-check-row {
                margin-top: -8px;
                margin-bottom: 2px;
            }
            div[class*="st-key-mobile_expiry_exclude_bidata"] {
                display: flex !important;
                justify-content: flex-end !important;
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
    st.markdown('<div class="mobile-result-grid">', unsafe_allow_html=True)
    for index, name in enumerate(candidates):
        _, total_qty, summary = meta_getter(name)
        with st.container(border=True):
            photo_col, info_col, qty_col, open_col = st.columns(
                [0.72, 3.25, 1.15, 0.78],
                gap="small",
                vertical_alignment="center",
            )
            with photo_col:
                thumbnail_uri = base._product_thumbnail_uri(name)
                if thumbnail_uri:
                    st.image(thumbnail_uri, width=48)
                else:
                    st.markdown('<div class="mobile-empty-thumb"></div>', unsafe_allow_html=True)
            with info_col:
                st.markdown(
                    f'<div class="mobile-result-name">{html.escape(str(name))}</div>'
                    f'<div class="mobile-result-company">{summary or "재고 없음"}</div>',
                    unsafe_allow_html=True,
                )
            with qty_col:
                st.markdown(
                    f'<div class="mobile-result-qty">{total_qty:,}개</div>',
                    unsafe_allow_html=True,
                )
            with open_col:
                if st.button("열기", key=f"{key_prefix}_{index}_{name}", use_container_width=True):
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


def _render_stock_tab():
    detail_product = str(st.session_state.get(base.DETAIL_STATE_KEY, "") or "").strip()
    if detail_product:
        base._render_detail_view("기본", detail_product)
        return

    term = base._live_input(
        "mobile_product_term_live",
        "mobile_product_term",
        "제품명 또는 별칭 검색",
    )
    if not term.strip():
        recent = st.session_state.get("mobile_recent_searches", [])
        if recent:
            _render_recent_links(recent, base.DETAIL_STATE_KEY, "recent_stock")
        return

    candidates = mobile_stock.mobile_product_candidates(term, limit=20)
    if not candidates:
        st.caption("검색 결과가 없습니다.")
        return

    st.markdown(
        f'<div class="mobile-search-section">검색 결과 {len(candidates)}건</div>',
        unsafe_allow_html=True,
    )
    _render_result_list(candidates, base._stock_meta, base.DETAIL_STATE_KEY, "mobile_stock_result")


def _render_expiry_tab():
    period = st.radio(
        "기간",
        ["전체", "3개월 이내", "6개월 이내", "1년 이내"],
        horizontal=True,
        label_visibility="collapsed",
        key="mobile_expiry_period",
    )

    term = base._live_input(
        "mobile_expiry_search_live",
        "mobile_expiry_search_value",
        "제품명 또는 별칭 검색",
    )

    st.markdown('<div class="mobile-expiry-check-row">', unsafe_allow_html=True)
    _, check_col = st.columns([3.4, 1.6], gap="small")
    with check_col:
        exclude_bidata = st.checkbox(
            "비자료 제외",
            value=True,
            key="mobile_expiry_exclude_bidata",
        )
    st.markdown("</div>", unsafe_allow_html=True)

    df = base._filtered_expiry_df(period, exclude_bidata)
    detail_product = str(st.session_state.get(base.EXPIRY_DETAIL_STATE_KEY, "") or "").strip()
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
    base._inject_mobile_search_css = _inject_mobile_search_css
    base._render_result_list = _render_result_list
    base._render_recent_links = _render_recent_links
    try:
        _inject_mobile_search_css()
        stock_tab, expiry_tab = st.tabs(["재고 검색", "임박재고"])
        with stock_tab:
            _render_stock_tab()
        with expiry_tab:
            _render_expiry_tab()
    finally:
        base._inject_mobile_search_css = original_inject
        base._render_result_list = original_result
        base._render_recent_links = original_recent
