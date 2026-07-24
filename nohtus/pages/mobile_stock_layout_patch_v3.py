import html
from datetime import date

import pandas as pd
import streamlit as st

import nohtus.pages.mobile_stock as mobile_stock
import nohtus.pages.mobile_stock_layout_patch_v2 as base


_ORIGINAL_INJECT_CSS = base._inject_mobile_search_css


def _inject_mobile_search_css():
    _ORIGINAL_INJECT_CSS()
    st.markdown(
        """
        <style>
        @media (max-width: 768px) {
            div[class*="st-key-mobile_result_row_"] div[data-testid="stVerticalBlockBorderWrapper"] {
                margin-bottom: 4px !important;
                padding: 0 !important;
                border-radius: 12px !important;
                overflow: hidden !important;
            }
            div[class*="st-key-mobile_result_row_"] > div,
            div[class*="st-key-mobile_result_row_"] div[data-testid="stVerticalBlock"],
            div[class*="st-key-mobile_result_row_"] div[data-testid="stElementContainer"] {
                margin: 0 !important;
                padding-top: 0 !important;
                padding-bottom: 0 !important;
            }
            div[class*="st-key-mobile_result_row_"] > div div[data-testid="stHorizontalBlock"]:first-of-type {
                display: grid !important;
                grid-template-columns: minmax(0, 1fr) 150px !important;
                column-gap: 8px !important;
                align-items: center !important;
                min-height: 68px !important;
                padding: 6px 8px !important;
                box-sizing: border-box !important;
            }
            div[class*="st-key-mobile_result_row_"] div[data-testid="column"] {
                min-width: 0 !important;
                margin: 0 !important;
                padding: 0 !important;
            }
            .mobile-result-info {
                display: flex !important;
                flex-direction: column !important;
                justify-content: center !important;
                margin: 0 !important;
                padding: 0 !important;
            }
            .mobile-result-name {
                font-size: 14px !important;
                line-height: 1.3 !important;
                margin: 0 0 4px !important;
                white-space: normal !important;
                overflow: visible !important;
                text-overflow: clip !important;
                word-break: keep-all !important;
            }
            .mobile-result-company {
                font-size: 11.5px !important;
                line-height: 1.35 !important;
                margin: 0 !important;
                white-space: normal !important;
                overflow: visible !important;
                text-overflow: clip !important;
            }
            div[class*="st-key-mobile_result_action_"] {
                width: 100% !important;
                margin: 0 !important;
                padding: 0 !important;
                align-self: center !important;
            }
            div[class*="st-key-mobile_result_action_"] div[data-testid="stHorizontalBlock"] {
                display: grid !important;
                grid-template-columns: minmax(72px, 1fr) 58px !important;
                gap: 6px !important;
                align-items: center !important;
                width: 100% !important;
                min-height: 36px !important;
                height: 36px !important;
                margin: 0 !important;
                padding: 0 !important;
            }
            div[class*="st-key-mobile_result_action_"] div[data-testid="column"],
            div[class*="st-key-mobile_result_action_"] div[data-testid="stElementContainer"],
            div[class*="st-key-mobile_result_action_"] div[data-testid="stButton"] {
                height: 36px !important;
                min-height: 36px !important;
                margin: 0 !important;
                padding: 0 !important;
                display: flex !important;
                align-items: center !important;
                justify-content: center !important;
            }
            div[class*="st-key-mobile_result_action_"] .mobile-result-qty {
                width: 100% !important;
                height: 36px !important;
                min-height: 36px !important;
                margin: 0 !important;
                padding: 0 !important;
                display: flex !important;
                align-items: center !important;
                justify-content: center !important;
                line-height: 1 !important;
                white-space: nowrap !important;
            }
            div[class*="st-key-mobile_result_action_"] button {
                width: 58px !important;
                height: 36px !important;
                min-height: 36px !important;
                margin: 0 !important;
                padding: 0 6px !important;
                display: flex !important;
                align-items: center !important;
                justify-content: center !important;
                white-space: nowrap !important;
                writing-mode: horizontal-tb !important;
                line-height: 1 !important;
            }
            div[class*="st-key-mobile_result_action_"] button p {
                margin: 0 !important;
                line-height: 1 !important;
                white-space: nowrap !important;
                writing-mode: horizontal-tb !important;
            }
            .mobile-detail-photo:empty {
                box-sizing: border-box !important;
                border: 1.5px dashed #b8c0cc !important;
                border-radius: 12px !important;
                background: #fafbfc !important;
            }
            .mobile-detail-photo img { object-fit: cover !important; }
            .mobile-expiry-date-row { margin-top: 4px !important; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _live_input(key, value_key, placeholder):
    """iOS 한글 조합 입력이 끝날 시간을 확보한 실시간 검색 입력."""
    if mobile_stock.st_keyup is not None:
        return mobile_stock.st_keyup(
            "검색",
            value=st.session_state.get(value_key, ""),
            key=key,
            placeholder=placeholder,
            debounce=350,
            label_visibility="collapsed",
        ) or ""
    return st.text_input(
        "검색",
        value=st.session_state.get(value_key, ""),
        key=key,
        placeholder=placeholder,
        label_visibility="collapsed",
    ) or ""


def _remember_result_state(key_prefix, name, index):
    if key_prefix.startswith("mobile_expiry"):
        term = str(st.session_state.get("mobile_expiry_search_live", "") or "")
        st.session_state["mobile_expiry_search_value"] = term
        st.session_state["mobile_expiry_return_term"] = term
        st.session_state["mobile_expiry_return_product"] = str(name)
        st.session_state["mobile_expiry_return_index"] = int(index)
    else:
        term = str(st.session_state.get("mobile_product_term_live", "") or "")
        st.session_state["mobile_product_term"] = term
        st.session_state["mobile_stock_return_term"] = term
        st.session_state["mobile_stock_return_product"] = str(name)
        st.session_state["mobile_stock_return_index"] = int(index)


def _restore_result_position(state_key, key_prefix):
    index = st.session_state.pop(state_key, None)
    if index is None:
        return
    try:
        index = int(index)
    except (TypeError, ValueError):
        return

    safe_prefix = html.escape(str(key_prefix), quote=True)
    st.components.v1.html(
        f"""
        <script>
        (() => {{
            const selector = 'div[class*="st-key-mobile_result_row_{safe_prefix}_"]';
            const targetIndex = {index};
            const restore = () => {{
                const doc = window.parent && window.parent.document ? window.parent.document : document;
                const cards = Array.from(doc.querySelectorAll(selector));
                const target = cards[targetIndex];
                if (!target) return false;
                target.scrollIntoView({{block: "center", behavior: "auto"}});
                return true;
            }};
            [0, 100, 250, 500, 900].forEach(delay => setTimeout(restore, delay));
        }})();
        </script>
        """,
        height=0,
        width=0,
    )


def _expiry_badge(rows):
    if rows is None or rows.empty or "_expiry" not in rows.columns:
        return ""
    nearest = rows["_expiry"].min()
    if pd.isna(nearest):
        return ""
    days = int((nearest.date() - date.today()).days)
    date_text = nearest.strftime("%Y.%m.%d")
    if days <= 90:
        badge_text, badge_class = "3개월 이내", "red"
    elif days <= 180:
        badge_text, badge_class = "6개월 이내", "yellow"
    else:
        badge_text, badge_class = "1년 이내", "blue"
    return (
        '<div class="mobile-expiry-date-row">'
        f'<span>{html.escape(date_text)}</span>'
        f'<span class="mobile-expiry-badge {badge_class}">{badge_text}</span>'
        '</div>'
    )


def _render_result_list(candidates, meta_getter, state_key, key_prefix):
    for index, name in enumerate(candidates):
        rows, total_qty, summary = meta_getter(name)
        row_key = f"mobile_result_row_{key_prefix}_{index}_{base.base._safe_key(name)}"
        with st.container(border=True, key=row_key):
            info_col, action_col = st.columns(
                [4.2, 1.8],
                gap="small",
                vertical_alignment="center",
            )
            with info_col:
                expiry_html = _expiry_badge(rows) if key_prefix.startswith("mobile_expiry") else ""
                st.markdown(
                    '<div class="mobile-result-info">'
                    f'<div class="mobile-result-name">{html.escape(str(name))}</div>'
                    f'<div class="mobile-result-company">{html.escape(str(summary or "재고 없음"))}</div>'
                    f'{expiry_html}'
                    '</div>',
                    unsafe_allow_html=True,
                )
            with action_col:
                with st.container(key=f"mobile_result_action_{key_prefix}_{index}"):
                    qty_col, open_col = st.columns([1.25, 0.9], gap="small", vertical_alignment="center")
                    with qty_col:
                        st.markdown(
                            f'<div class="mobile-result-qty">{total_qty:,}개</div>',
                            unsafe_allow_html=True,
                        )
                    with open_col:
                        if st.button("열기", key=f"{key_prefix}_{index}_{name}", use_container_width=True):
                            _remember_result_state(key_prefix, name, index)
                            st.session_state[state_key] = name
                            mobile_stock._remember_recent_search(name)
                            st.rerun()


def _render_stock_detail_view(product_name):
    st.markdown('<div class="mobile-back-button">', unsafe_allow_html=True)
    go_back = st.button("‹ 검색 결과", key="mobile_search_back_v3")
    st.markdown("</div>", unsafe_allow_html=True)
    if go_back:
        st.session_state.pop(base.base.base.DETAIL_STATE_KEY, None)
        saved_term = str(st.session_state.get("mobile_stock_return_term", "") or "")
        st.session_state["mobile_product_term"] = saved_term
        st.rerun()
    base.base._render_stock_detail(product_name)


def _render_expiry_detail(product_name, source_df):
    st.markdown('<div class="mobile-back-button">', unsafe_allow_html=True)
    go_back = st.button("‹ 검색 결과", key="mobile_expiry_back_v3")
    st.markdown("</div>", unsafe_allow_html=True)
    if go_back:
        st.session_state.pop(base.base.base.EXPIRY_DETAIL_STATE_KEY, None)
        saved_term = str(st.session_state.get("mobile_expiry_return_term", "") or "")
        st.session_state["mobile_expiry_search_value"] = saved_term
        st.rerun()

    rows = source_df[source_df["product_name"].astype(str) == str(product_name)].copy()
    base.base._detail_header(product_name, rows)
    if rows.empty:
        st.info("조건에 맞는 임박재고가 없습니다.")
        return
    rows = rows.sort_values(["_expiry", "company", "location", "lot"])
    rows["유통기한"] = rows["_expiry"].dt.strftime("%Y.%m.%d")
    rows = rows.rename(
        columns={"company": "사업장", "location": "로케이션", "lot": "제조번호", "qty": "수량"}
    )
    st.markdown('<div class="mobile-detail-table-gap"></div>', unsafe_allow_html=True)
    st.dataframe(
        rows[["사업장", "로케이션", "제조번호", "유통기한", "수량"]],
        use_container_width=True,
        hide_index=True,
    )


def _render_expiry_tab():
    detail_product = str(st.session_state.get(base.base.base.EXPIRY_DETAIL_STATE_KEY, "") or "").strip()

    if detail_product:
        period = st.session_state.get("mobile_expiry_period", "1년 이내")
        exclude_bidata = bool(st.session_state.get("mobile_expiry_exclude_bidata", True))
        df = base.base.base._filtered_expiry_df(period, exclude_bidata)
        _render_expiry_detail(detail_product, df)
        return

    term = _live_input(
        "mobile_expiry_search_live",
        "mobile_expiry_search_value",
        "제품명 또는 별칭 검색",
    )

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

    df = base.base.base._filtered_expiry_df(period, exclude_bidata)
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
        lambda name: base.base.base._expiry_meta(name, df),
        base.base.base.EXPIRY_DETAIL_STATE_KEY,
        "mobile_expiry_result",
    )
    _restore_result_position("mobile_expiry_return_index", "mobile_expiry_result")


def page_mobile_stock_finder():
    original_inject = base._inject_mobile_search_css
    original_result = base._render_result_list
    original_stock_detail = base._render_stock_detail_view
    original_expiry_detail = base._render_expiry_detail
    original_expiry = base._render_expiry_tab
    original_live_input = base.base.base._live_input
    base._inject_mobile_search_css = _inject_mobile_search_css
    base._render_result_list = _render_result_list
    base._render_stock_detail_view = _render_stock_detail_view
    base._render_expiry_detail = _render_expiry_detail
    base._render_expiry_tab = _render_expiry_tab
    base.base.base._live_input = _live_input
    try:
        result = base.page_mobile_stock_finder()
        _restore_result_position("mobile_stock_return_index", "mobile_stock_result")
        return result
    finally:
        base._inject_mobile_search_css = original_inject
        base._render_result_list = original_result
        base._render_stock_detail_view = original_stock_detail
        base._render_expiry_detail = original_expiry_detail
        base._render_expiry_tab = original_expiry
        base.base.base._live_input = original_live_input
