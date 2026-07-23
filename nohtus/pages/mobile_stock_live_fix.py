import html

import streamlit as st

import nohtus.pages.mobile_stock as mobile_stock


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
            div[data-testid="stButton"] button[kind="secondary"] {
                min-height: 0 !important;
            }
            .mobile-search-section {
                margin: 18px 0 8px;
                font-size: 14px;
                font-weight: 700;
                color: #202636;
            }
            .mobile-result-card {
                position: relative;
                border: 1px solid #e2e6ed;
                border-radius: 14px;
                background: #ffffff;
                padding: 14px 44px 13px 15px;
                margin: 0;
                min-height: 68px;
                box-shadow: 0 1px 2px rgba(20, 28, 45, .03);
            }
            .mobile-result-name {
                font-size: 15px;
                font-weight: 700;
                line-height: 1.35;
                color: #182033;
                margin-bottom: 5px;
            }
            .mobile-result-meta {
                display: flex;
                flex-wrap: wrap;
                gap: 4px 10px;
                font-size: 12px;
                line-height: 1.45;
                color: #6b7485;
            }
            .mobile-result-total {
                color: #253148;
                font-weight: 700;
            }
            .mobile-result-arrow {
                position: absolute;
                right: 16px;
                top: 50%;
                transform: translateY(-50%);
                font-size: 24px;
                color: #a3aaba;
                font-weight: 300;
            }
            .mobile-result-click div[data-testid="stButton"] {
                margin-top: -72px !important;
                margin-bottom: 8px !important;
                position: relative;
                z-index: 2;
            }
            .mobile-result-click div[data-testid="stButton"] button {
                height: 68px !important;
                min-height: 68px !important;
                border: 0 !important;
                border-radius: 14px !important;
                background: transparent !important;
                color: transparent !important;
                box-shadow: none !important;
                padding: 0 !important;
            }
            .mobile-result-click div[data-testid="stButton"] button:hover,
            .mobile-result-click div[data-testid="stButton"] button:focus,
            .mobile-result-click div[data-testid="stButton"] button:active {
                background: rgba(92, 124, 250, .035) !important;
                border: 0 !important;
                box-shadow: none !important;
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


def _render_result_card(name, rows):
    total_qty = int(rows["qty"].sum()) if not rows.empty else 0
    company_totals = (
        rows.groupby("company")["qty"].sum()
        if not rows.empty
        else mobile_stock.pd.Series(dtype=float)
    )
    company_summary = " · ".join(
        f"{html.escape(str(company))} {int(qty):,}"
        for company, qty in company_totals.items()
        if int(qty or 0) > 0
    )
    safe_name = html.escape(str(name))
    meta_parts = []
    if company_summary:
        meta_parts.append(f"<span>{company_summary}</span>")
    meta_parts.append(f"<span class='mobile-result-total'>총 {total_qty:,}개</span>")

    st.markdown(
        f"""
        <div class="mobile-result-card">
            <div class="mobile-result-name">{safe_name}</div>
            <div class="mobile-result-meta">{''.join(meta_parts)}</div>
            <div class="mobile-result-arrow">›</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown('<div class="mobile-result-click">', unsafe_allow_html=True)
    clicked = st.button(
        f"{name} 상세 보기",
        key=f"mobile_result_{name}",
        use_container_width=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)
    return clicked


def _render_mobile_search_without_widget_state_conflict(username):
    """Render live mobile search without rewriting an instantiated widget key."""
    _inject_mobile_search_css()
    st.title("재고 검색")
    term = mobile_stock._live_search_input()

    candidates = mobile_stock.mobile_product_candidates(term, limit=20) if term.strip() else []
    selected_product = st.session_state.get("mobile_selected_product", "")

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
                    mobile_stock._select_product(name)
                    st.rerun()
        return

    if not candidates:
        st.caption("검색 결과가 없습니다.")
        return

    st.markdown('<div class="mobile-search-section">검색 결과</div>', unsafe_allow_html=True)
    for name in candidates:
        rows = mobile_stock.mobile_stock_rows(name)
        if _render_result_card(name, rows):
            mobile_stock._select_product(name)
            st.rerun()

    if selected_product and selected_product == term.strip():
        mobile_stock._render_product_detail(username, selected_product)


def page_mobile_stock_finder():
    """Run the mobile stock page with the fixed live-search renderer."""
    original_renderer = mobile_stock._render_mobile_search
    mobile_stock._render_mobile_search = _render_mobile_search_without_widget_state_conflict
    try:
        return mobile_stock.page_mobile_stock_finder()
    finally:
        mobile_stock._render_mobile_search = original_renderer
