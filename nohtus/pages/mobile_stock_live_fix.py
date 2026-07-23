import html

import streamlit as st

import nohtus.pages.mobile_stock as mobile_stock


DETAIL_STATE_KEY = "mobile_search_detail_product"


def _inject_mobile_search_css():
    st.markdown(
        """
        <style>
        @media (max-width: 768px) {
            div[data-testid="stTextInput"] input {
                height: 48px !important;
                border-radius: 14px !important;
                border: 1px solid #d9dee7 !important;
                background: #ffffff !important;
                box-shadow: none !important;
                padding: 0 16px !important;
                font-size: 15px !important;
            }
            div[data-testid="stTextInput"] input:focus {
                border-color: #8aa4d6 !important;
                box-shadow: 0 0 0 2px rgba(92, 124, 250, .08) !important;
            }
            .mobile-search-section {
                margin: 18px 0 8px;
                font-size: 14px;
                font-weight: 700;
                color: #202636;
            }
            .mobile-result-list {
                overflow: hidden;
                border: 1px solid #e2e6ed;
                border-radius: 14px;
                background: #ffffff;
            }
            .mobile-result-row {
                position: relative;
                min-height: 66px;
                padding: 12px 90px 11px 15px;
                border-bottom: 1px solid #edf0f4;
                background: #ffffff;
            }
            .mobile-result-row.last-row {
                border-bottom: 0;
            }
            .mobile-result-name {
                margin-bottom: 4px;
                font-size: 14px;
                font-weight: 700;
                line-height: 1.35;
                color: #182033;
            }
            .mobile-result-company {
                overflow: hidden;
                font-size: 12px;
                line-height: 1.4;
                color: #727b8d;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .mobile-result-total {
                position: absolute;
                top: 50%;
                right: 34px;
                transform: translateY(-50%);
                font-size: 13px;
                font-weight: 700;
                color: #253148;
                white-space: nowrap;
            }
            .mobile-result-arrow {
                position: absolute;
                top: 50%;
                right: 14px;
                transform: translateY(-50%);
                font-size: 22px;
                font-weight: 300;
                color: #adb4c1;
            }
            .mobile-result-click div[data-testid="stButton"] {
                position: relative;
                z-index: 2;
                margin-top: -66px !important;
                margin-bottom: 0 !important;
            }
            .mobile-result-click div[data-testid="stButton"] button {
                height: 66px !important;
                min-height: 66px !important;
                padding: 0 !important;
                border: 0 !important;
                border-radius: 0 !important;
                background: transparent !important;
                color: transparent !important;
                box-shadow: none !important;
            }
            .mobile-result-click div[data-testid="stButton"] button:hover,
            .mobile-result-click div[data-testid="stButton"] button:focus,
            .mobile-result-click div[data-testid="stButton"] button:active {
                border: 0 !important;
                background: rgba(92, 124, 250, .035) !important;
                box-shadow: none !important;
            }
            .mobile-back-button div[data-testid="stButton"] button {
                min-height: 38px !important;
                margin-bottom: 4px !important;
                padding: 0 4px !important;
                border: 0 !important;
                background: transparent !important;
                color: #46546d !important;
                box-shadow: none !important;
                justify-content: flex-start !important;
                font-size: 13px !important;
                font-weight: 600 !important;
            }
            .mobile-recent-chip div[data-testid="stButton"] button {
                min-height: 38px !important;
                border-radius: 999px !important;
                border: 1px solid #e1e5ec !important;
                background: #ffffff !important;
                justify-content: flex-start !important;
                padding: 0 14px !important;
                font-size: 13px !important;
                font-weight: 500 !important;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _result_meta(name):
    rows = mobile_stock.mobile_stock_rows(name)
    total_qty = int(rows["qty"].sum()) if not rows.empty else 0
    company_totals = (
        rows.groupby("company")["qty"].sum()
        if not rows.empty
        else mobile_stock.pd.Series(dtype=float)
    )
    summary = " · ".join(
        f"{html.escape(str(company))} {int(qty):,}"
        for company, qty in company_totals.items()
        if int(qty or 0) > 0
    )
    return rows, total_qty, summary


def _render_result_list(candidates):
    st.markdown('<div class="mobile-result-list">', unsafe_allow_html=True)
    for index, name in enumerate(candidates):
        _, total_qty, summary = _result_meta(name)
        last_class = " last-row" if index == len(candidates) - 1 else ""
        st.markdown(
            f"""
            <div class="mobile-result-row{last_class}">
                <div class="mobile-result-name">{html.escape(str(name))}</div>
                <div class="mobile-result-company">{summary or '재고 없음'}</div>
                <div class="mobile-result-total">{total_qty:,}개</div>
                <div class="mobile-result-arrow">›</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown('<div class="mobile-result-click">', unsafe_allow_html=True)
        clicked = st.button(
            f"{name} 열기",
            key=f"mobile_result_{name}",
            use_container_width=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)
        if clicked:
            st.session_state[DETAIL_STATE_KEY] = name
            mobile_stock._remember_recent_search(name)
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)


def _render_detail_view(username, product_name):
    st.markdown('<div class="mobile-back-button">', unsafe_allow_html=True)
    go_back = st.button("‹ 검색 결과", key="mobile_search_back")
    st.markdown("</div>", unsafe_allow_html=True)
    if go_back:
        st.session_state.pop(DETAIL_STATE_KEY, None)
        st.rerun()

    mobile_stock._render_product_detail(username, product_name)


def _render_mobile_search_without_widget_state_conflict(username):
    """Render live search as a compact result list and a separate detail view."""
    _inject_mobile_search_css()

    detail_product = str(st.session_state.get(DETAIL_STATE_KEY, "") or "").strip()
    if detail_product:
        _render_detail_view(username, detail_product)
        return

    st.title("재고 검색")
    term = mobile_stock._live_search_input()

    if not term.strip():
        recent = st.session_state.get("mobile_recent_searches", [])
        if recent:
            st.markdown('<div class="mobile-search-section">최근 검색어</div>', unsafe_allow_html=True)
            for name in recent:
                st.markdown('<div class="mobile-recent-chip">', unsafe_allow_html=True)
                clicked = st.button(
                    f"◷  {name}",
                    key=f"recent_{name}",
                    use_container_width=True,
                )
                st.markdown("</div>", unsafe_allow_html=True)
                if clicked:
                    st.session_state[DETAIL_STATE_KEY] = name
                    mobile_stock._remember_recent_search(name)
                    st.rerun()
        return

    candidates = mobile_stock.mobile_product_candidates(term, limit=20)
    if not candidates:
        st.caption("검색 결과가 없습니다.")
        return

    st.markdown(
        f'<div class="mobile-search-section">검색 결과 {len(candidates)}건</div>',
        unsafe_allow_html=True,
    )
    _render_result_list(candidates)


def page_mobile_stock_finder():
    """Run the mobile stock page with the compact list/detail search renderer."""
    original_renderer = mobile_stock._render_mobile_search
    mobile_stock._render_mobile_search = _render_mobile_search_without_widget_state_conflict
    try:
        return mobile_stock.page_mobile_stock_finder()
    finally:
        mobile_stock._render_mobile_search = original_renderer
