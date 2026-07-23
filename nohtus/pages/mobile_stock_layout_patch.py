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
            div[data-testid="stAppViewContainer"] .main .block-container {
                padding-top: 0 !important;
                margin-top: 0 !important;
            }
            header[data-testid="stHeader"] {
                height: 0 !important;
                min-height: 0 !important;
            }
            .mobile-tab-row {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 0;
                margin: 0 0 12px;
                border-bottom: 1px solid #e5e7eb;
            }
            .mobile-tab-row div[data-testid="stButton"] {
                margin: 0 !important;
            }
            .mobile-tab-row div[data-testid="stButton"] button {
                width: 100% !important;
                min-height: 42px !important;
                border: 0 !important;
                border-radius: 0 !important;
                background: transparent !important;
                box-shadow: none !important;
                color: #64748b !important;
                font-size: 14px !important;
                font-weight: 600 !important;
                border-bottom: 2px solid transparent !important;
            }
            .mobile-tab-row .active div[data-testid="stButton"] button {
                color: #111827 !important;
                font-weight: 800 !important;
                border-bottom-color: #ff4b4b !important;
            }
            .mobile-result-row {
                min-height: 74px !important;
                padding: 10px 132px 9px 70px !important;
            }
            .mobile-result-thumb {
                background: #f8fafc !important;
            }
            .mobile-result-total {
                right: 70px !important;
                top: 50% !important;
                transform: translateY(-50%) !important;
                font-size: 17px !important;
                font-weight: 800 !important;
                color: #1f2937 !important;
            }
            .mobile-result-arrow { display: none !important; }

            div[class*="st-key-mobile_stock_result_"] div[data-testid="stButton"],
            div[class*="st-key-mobile_expiry_result_"] div[data-testid="stButton"] {
                width: 52px !important;
                margin-left: auto !important;
            }
            div[class*="st-key-mobile_stock_result_"] div[data-testid="stButton"] button,
            div[class*="st-key-mobile_expiry_result_"] div[data-testid="stButton"] button {
                width: 52px !important;
                height: 32px !important;
                min-height: 32px !important;
                padding: 0 !important;
                border: 0 !important;
                border-radius: 0 !important;
                background: transparent !important;
                color: #2563eb !important;
                box-shadow: none !important;
                font-size: 13px !important;
                font-weight: 700 !important;
            }
            .mobile-result-click div[data-testid="stButton"] {
                margin-top: -54px !important;
                margin-bottom: 20px !important;
                padding-right: 4px !important;
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
            f'<img src="{thumbnail_uri}" alt="{html.escape(str(name))}">' if thumbnail_uri else ""
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


def _render_tabs():
    current = st.session_state.get("mobile_stock_mode", "재고 검색")
    left, right = st.columns(2, gap="small")
    with left:
        st.markdown(f'<div class="mobile-tab-row"><div class="{"active" if current == "재고 검색" else ""}">', unsafe_allow_html=True)
        stock_clicked = st.button("재고 검색", key="mobile_tab_stock", use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)
    with right:
        st.markdown(f'<div class="mobile-tab-row"><div class="{"active" if current == "임박재고" else ""}">', unsafe_allow_html=True)
        expiry_clicked = st.button("임박재고", key="mobile_tab_expiry", use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)
    if stock_clicked and current != "재고 검색":
        st.session_state["mobile_stock_mode"] = "재고 검색"
        st.rerun()
    if expiry_clicked and current != "임박재고":
        st.session_state["mobile_stock_mode"] = "임박재고"
        st.rerun()
    return st.session_state.get("mobile_stock_mode", "재고 검색")


def _render_stock_without_title(username):
    detail_product = str(st.session_state.get(base.DETAIL_STATE_KEY, "") or "").strip()
    if detail_product:
        base._render_detail_view(username, detail_product)
        return

    term = base._live_input("mobile_product_term_live", "mobile_product_term", "제품명 또는 별칭 검색")
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


def page_mobile_stock_finder():
    original_inject = base._inject_mobile_search_css
    original_result = base._render_result_list
    original_recent = base._render_recent_links
    original_expiry = base._render_expiry_inventory
    original_search = base._render_mobile_search
    base._inject_mobile_search_css = _inject_mobile_search_css
    base._render_result_list = _render_result_list
    base._render_recent_links = _render_recent_links
    base._render_expiry_inventory = _render_expiry_inventory
    base._render_mobile_search = _render_stock_without_title
    try:
        _inject_mobile_search_css()
        mode = _render_tabs()
        if mode == "임박재고":
            _render_expiry_inventory()
        else:
            _render_stock_without_title("기본")
    finally:
        base._inject_mobile_search_css = original_inject
        base._render_result_list = original_result
        base._render_recent_links = original_recent
        base._render_expiry_inventory = original_expiry
        base._render_mobile_search = original_search
