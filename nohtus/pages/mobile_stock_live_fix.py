import streamlit as st

import nohtus.pages.mobile_stock as mobile_stock


def _render_mobile_search_without_widget_state_conflict(username):
    """Render live mobile search without rewriting an instantiated widget key."""
    st.title("재고 검색")
    term = mobile_stock._live_search_input()

    candidates = mobile_stock.mobile_product_candidates(term, limit=20) if term.strip() else []
    selected_product = st.session_state.get("mobile_selected_product", "")

    if term.strip() and candidates:
        options = ["선택하세요"] + candidates
        picked = st.selectbox(
            "검색 추천",
            options,
            index=0,
            key=f"mobile_autocomplete_{term}",
            label_visibility="collapsed",
        )
        if picked != "선택하세요":
            mobile_stock._select_product(picked)
            st.rerun()
    elif term.strip():
        st.caption("검색 결과가 없습니다.")

    if not term.strip():
        recent = st.session_state.get("mobile_recent_searches", [])
        if recent:
            st.markdown("**최근 검색어**")
            for name in recent:
                if st.button(f"◷  {name}", key=f"recent_{name}", use_container_width=True):
                    mobile_stock._select_product(name)
                    st.rerun()
        return

    if candidates:
        st.markdown("**검색 결과**")
        for name in candidates:
            rows = mobile_stock.mobile_stock_rows(name)
            total_qty = int(rows["qty"].sum()) if not rows.empty else 0
            company_totals = (
                rows.groupby("company")["qty"].sum()
                if not rows.empty
                else mobile_stock.pd.Series(dtype=float)
            )
            summary = " · ".join(
                f"{company} {int(qty):,}"
                for company, qty in company_totals.items()
                if int(qty or 0) > 0
            )
            button_text = f"{name}    총 {total_qty:,}개"
            if st.button(button_text, key=f"mobile_result_{name}", use_container_width=True):
                mobile_stock._select_product(name)
                st.rerun()
            if summary:
                st.markdown(f"<div class='mobile-muted'>{summary}</div>", unsafe_allow_html=True)

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
