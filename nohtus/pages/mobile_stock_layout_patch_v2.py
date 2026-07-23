import html
from datetime import date

import pandas as pd
import streamlit as st

import nohtus.pages.mobile_stock as mobile_stock
import nohtus.pages.mobile_stock_layout_patch as base


_ORIGINAL_INJECT_CSS = base._inject_mobile_search_css


def _inject_mobile_search_css():
    _ORIGINAL_INJECT_CSS()
    st.markdown(
        """
        <style>
        @media (max-width: 768px) {
            /* 카드 테두리와 내부 콘텐츠 사이 상하 여백을 2px 수준으로 줄인다. */
            div[class*="st-key-mobile_result_row_"] div[data-testid="stVerticalBlockBorderWrapper"] {
                margin-bottom: 3px !important;
                border-radius: 9px !important;
            }
            div[class*="st-key-mobile_result_row_"] div[data-testid="stHorizontalBlock"] {
                min-height: 100px !important;
                padding: 2px 3px !important;
                column-gap: 4px !important;
                grid-template-columns: 98px minmax(0, 1fr) 78px 54px !important;
            }
            div[class*="st-key-mobile_result_row_"] div[data-testid="column"],
            div[class*="st-key-mobile_result_row_"] div[data-testid="stElementContainer"] {
                margin: 0 !important;
                padding-top: 0 !important;
                padding-bottom: 0 !important;
            }

            .mobile-result-name {
                font-size: 14px !important;
                line-height: 1.3 !important;
                margin-bottom: 4px !important;
            }
            .mobile-result-company {
                font-size: 11.5px !important;
                line-height: 1.35 !important;
            }

            /* 수량과 열기 칸 전체를 똑같은 높이와 중심선으로 강제한다. */
            div[class*="st-key-mobile_result_row_"] div[data-testid="column"]:nth-child(3),
            div[class*="st-key-mobile_result_row_"] div[data-testid="column"]:nth-child(4) {
                height: 36px !important;
                min-height: 36px !important;
                display: flex !important;
                align-items: center !important;
                justify-content: center !important;
                align-self: center !important;
            }
            div[class*="st-key-mobile_result_row_"] div[data-testid="column"]:nth-child(3) > div,
            div[class*="st-key-mobile_result_row_"] div[data-testid="column"]:nth-child(4) > div,
            div[class*="st-key-mobile_result_row_"] div[data-testid="column"]:nth-child(4) div[data-testid="stButton"] {
                width: 100% !important;
                height: 36px !important;
                min-height: 36px !important;
                margin: 0 !important;
                padding: 0 !important;
                display: flex !important;
                align-items: center !important;
                justify-content: center !important;
            }
            .mobile-result-qty {
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
            div[class*="st-key-mobile_result_row_"] div[data-testid="stButton"] button {
                width: 54px !important;
                height: 36px !important;
                min-height: 36px !important;
                margin: 0 !important;
                padding: 0 !important;
                display: flex !important;
                align-items: center !important;
                justify-content: center !important;
                line-height: 1 !important;
                white-space: nowrap !important;
                writing-mode: horizontal-tb !important;
            }
            div[class*="st-key-mobile_result_row_"] div[data-testid="stButton"] button p {
                margin: 0 !important;
                line-height: 1 !important;
                white-space: nowrap !important;
                writing-mode: horizontal-tb !important;
            }

            .mobile-expiry-date-row {
                display: flex;
                align-items: center;
                gap: 6px;
                margin-top: 5px;
                font-size: 11.5px;
                line-height: 1.2;
                color: #586174;
                white-space: nowrap;
            }
            .mobile-expiry-badge {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                padding: 2px 6px;
                border-radius: 999px;
                font-size: 10.5px;
                font-weight: 750;
                line-height: 1.2;
            }
            .mobile-expiry-badge.red { background: #fee2e2; color: #b91c1c; }
            .mobile-expiry-badge.yellow { background: #fef3c7; color: #a16207; }
            .mobile-expiry-badge.blue { background: #dbeafe; color: #1d4ed8; }

            div[class*="st-key-mobile_expiry_filter_row"] {
                margin-top: 4px !important;
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


def _remember_result_state(key_prefix):
    if key_prefix.startswith("mobile_expiry"):
        term = str(st.session_state.get("mobile_expiry_search_live", "") or "")
        st.session_state["mobile_expiry_search_value"] = term
        st.session_state["mobile_expiry_return_term"] = term
    else:
        term = str(st.session_state.get("mobile_product_term_live", "") or "")
        st.session_state["mobile_product_term"] = term
        st.session_state["mobile_stock_return_term"] = term


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
        f'<div class="mobile-expiry-date-row">'
        f'<span>유통기한 {html.escape(date_text)}</span>'
        f'<span class="mobile-expiry-badge {badge_class}">{badge_text}</span>'
        f'</div>'
    )


def _render_result_list(candidates, meta_getter, state_key, key_prefix):
    for index, name in enumerate(candidates):
        rows, total_qty, summary = meta_getter(name)
        row_key = f"mobile_result_row_{key_prefix}_{index}_{base._safe_key(name)}"
        with st.container(border=True, key=row_key):
            photo_col, info_col, qty_col, open_col = st.columns(
                [1.2, 3.25, 1.05, 0.82],
                gap="small",
                vertical_alignment="center",
            )
            with photo_col:
                thumbnail_uri = base.base._product_thumbnail_uri(name)
                if thumbnail_uri:
                    st.image(thumbnail_uri, width=96)
                else:
                    st.markdown('<div class="mobile-empty-thumb"></div>', unsafe_allow_html=True)
            with info_col:
                expiry_html = _expiry_badge(rows) if key_prefix.startswith("mobile_expiry") else ""
                st.markdown(
                    f'<div class="mobile-result-name">{html.escape(str(name))}</div>'
                    f'<div class="mobile-result-company">{summary or "재고 없음"}</div>'
                    f'{expiry_html}',
                    unsafe_allow_html=True,
                )
            with qty_col:
                st.markdown(
                    f'<div class="mobile-result-qty">{total_qty:,}개</div>',
                    unsafe_allow_html=True,
                )
            with open_col:
                if st.button("열기", key=f"{key_prefix}_{index}_{name}", use_container_width=True):
                    _remember_result_state(key_prefix)
                    st.session_state[state_key] = name
                    mobile_stock._remember_recent_search(name)
                    st.rerun()


def _render_stock_detail_view(product_name):
    st.markdown('<div class="mobile-back-button">', unsafe_allow_html=True)
    go_back = st.button("‹ 검색 결과", key="mobile_search_back")
    st.markdown("</div>", unsafe_allow_html=True)
    if go_back:
        st.session_state.pop(base.base.DETAIL_STATE_KEY, None)
        saved_term = str(st.session_state.get("mobile_stock_return_term", "") or "")
        st.session_state["mobile_product_term"] = saved_term
        st.rerun()
    base._render_stock_detail(product_name)


def _render_expiry_detail(product_name, source_df):
    st.markdown('<div class="mobile-back-button">', unsafe_allow_html=True)
    go_back = st.button("‹ 검색 결과", key="mobile_expiry_back")
    st.markdown("</div>", unsafe_allow_html=True)
    if go_back:
        st.session_state.pop(base.base.EXPIRY_DETAIL_STATE_KEY, None)
        saved_term = str(st.session_state.get("mobile_expiry_return_term", "") or "")
        st.session_state["mobile_expiry_search_value"] = saved_term
        st.rerun()

    rows = source_df[source_df["product_name"].astype(str) == str(product_name)].copy()
    base._detail_header(product_name, rows)
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
    detail_product = str(st.session_state.get(base.base.EXPIRY_DETAIL_STATE_KEY, "") or "").strip()

    term = base.base._live_input(
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

    df = base.base._filtered_expiry_df(period, exclude_bidata)
    if detail_product:
        _render_expiry_detail(detail_product, df)
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
        lambda name: base.base._expiry_meta(name, df),
        base.base.EXPIRY_DETAIL_STATE_KEY,
        "mobile_expiry_result",
    )


def page_mobile_stock_finder():
    original_inject = base._inject_mobile_search_css
    original_result = base._render_result_list
    original_stock_detail = base._render_stock_detail_view
    original_expiry_detail = base._render_expiry_detail
    original_expiry = base._render_expiry_tab
    base._inject_mobile_search_css = _inject_mobile_search_css
    base._render_result_list = _render_result_list
    base._render_stock_detail_view = _render_stock_detail_view
    base._render_expiry_detail = _render_expiry_detail
    base._render_expiry_tab = _render_expiry_tab
    try:
        return base.page_mobile_stock_finder()
    finally:
        base._inject_mobile_search_css = original_inject
        base._render_result_list = original_result
        base._render_stock_detail_view = original_stock_detail
        base._render_expiry_detail = original_expiry_detail
        base._render_expiry_tab = original_expiry
