import html
from datetime import date

import pandas as pd
import streamlit as st

import nohtus.pages.mobile_stock as mobile_stock
import nohtus.pages.mobile_stock_layout_patch_v2 as base


_ORIGINAL_INJECT_CSS = base._inject_mobile_search_css
_ORIGINAL_RENDER_RESULT = base._render_result_list
_ORIGINAL_STOCK_DETAIL = base._render_stock_detail_view
_ORIGINAL_EXPIRY_DETAIL = base._render_expiry_detail
_ORIGINAL_EXPIRY_TAB = base._render_expiry_tab


def _inject_mobile_search_css():
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
            div[class*="st-key-mobile_result_row_"] div[data-testid="stHorizontalBlock"] {
                display: grid !important;
                grid-template-columns: 96px minmax(0, 1fr) 150px !important;
                column-gap: 8px !important;
                align-items: center !important;
                min-height: 112px !important;
                padding: 8px !important;
                box-sizing: border-box !important;
            }
            div[class*="st-key-mobile_result_row_"] div[data-testid="column"],
            div[class*="st-key-mobile_result_row_"] div[data-testid="stElementContainer"],
            div[class*="st-key-mobile_result_row_"] div[data-testid="stButton"] {
                margin: 0 !important;
                padding: 0 !important;
                min-width: 0 !important;
                transform: none !important;
            }

            .mobile-thumb-frame {
                width: 96px !important;
                height: 96px !important;
                box-sizing: border-box !important;
                border-radius: 10px !important;
                overflow: hidden !important;
                background: #fafbfc !important;
            }
            .mobile-thumb-frame.has-image {
                border: 1px solid #e1e6ee !important;
            }
            .mobile-thumb-frame.empty {
                border: 1.5px dashed #b8c0cc !important;
            }
            .mobile-thumb-frame img {
                display: block !important;
                width: 100% !important;
                height: 100% !important;
                object-fit: cover !important;
                object-position: center !important;
            }

            .mobile-result-info {
                display: flex !important;
                flex-direction: column !important;
                justify-content: center !important;
                min-height: 48px !important;
            }
            .mobile-result-name {
                margin: 0 0 4px !important;
                font-size: 14px !important;
                line-height: 1.3 !important;
            }
            .mobile-result-company {
                margin: 0 !important;
                font-size: 11.5px !important;
                line-height: 1.35 !important;
            }

            div[class*="st-key-mobile_result_action_"] {
                width: 100% !important;
                padding-right: 8px !important;
            }
            div[class*="st-key-mobile_result_action_"] div[data-testid="stHorizontalBlock"] {
                display: grid !important;
                grid-template-columns: minmax(74px, 1fr) 58px !important;
                gap: 6px !important;
                align-items: center !important;
                min-height: 36px !important;
                height: 36px !important;
                padding: 0 !important;
            }
            div[class*="st-key-mobile_result_action_"] div[data-testid="column"],
            div[class*="st-key-mobile_result_action_"] div[data-testid="stElementContainer"],
            div[class*="st-key-mobile_result_action_"] div[data-testid="stButton"] {
                height: 36px !important;
                min-height: 36px !important;
                display: flex !important;
                align-items: center !important;
                justify-content: center !important;
                transform: none !important;
            }
            .mobile-result-qty {
                width: 100% !important;
                height: 36px !important;
                min-height: 36px !important;
                display: flex !important;
                align-items: center !important;
                justify-content: center !important;
                margin: 0 !important;
                padding: 0 4px 0 0 !important;
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
                transform: none !important;
                white-space: nowrap !important;
                writing-mode: horizontal-tb !important;
                line-height: 1 !important;
            }
            div[class*="st-key-mobile_result_action_"] button p {
                margin: 0 !important;
                line-height: 1 !important;
                white-space: nowrap !important;
            }

            .mobile-expiry-date-row {
                display: flex;
                align-items: center;
                gap: 6px;
                margin-top: 4px;
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
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _safe_key(value):
    return base.base._safe_key(value)


def _thumbnail_html(name):
    thumbnail_uri = base.base.base._product_thumbnail_uri(name)
    if not thumbnail_uri:
        return '<div class="mobile-thumb-frame empty"></div>'
    safe_uri = html.escape(str(thumbnail_uri), quote=True)
    safe_name = html.escape(str(name), quote=True)
    return (
        '<div class="mobile-thumb-frame has-image">'
        f'<img src="{safe_uri}" alt="{safe_name}">'
        '</div>'
    )


def _expiry_badge(rows):
    if rows is None or rows.empty or "_expiry" not in rows.columns:
        return ""
    nearest = rows["_expiry"].min()
    if pd.isna(nearest):
        return ""
    days = int((nearest.date() - date.today()).days)
    if days <= 90:
        badge_text, badge_class = "3개월 이내", "red"
    elif days <= 180:
        badge_text, badge_class = "6개월 이내", "yellow"
    else:
        badge_text, badge_class = "1년 이내", "blue"
    return (
        '<div class="mobile-expiry-date-row">'
        f'<span>{nearest.strftime("%Y.%m.%d")}</span>'
        f'<span class="mobile-expiry-badge {badge_class}">{badge_text}</span>'
        '</div>'
    )


def _remember_result_state(key_prefix, anchor_id):
    if key_prefix.startswith("mobile_expiry"):
        term = str(st.session_state.get("mobile_expiry_search_live", "") or "")
        st.session_state["mobile_expiry_search_value"] = term
        st.session_state["mobile_expiry_return_term"] = term
        st.session_state["mobile_expiry_return_anchor"] = anchor_id
    else:
        term = str(st.session_state.get("mobile_product_term_live", "") or "")
        st.session_state["mobile_product_term"] = term
        st.session_state["mobile_stock_return_term"] = term
        st.session_state["mobile_stock_return_anchor"] = anchor_id


def _restore_anchor(state_key):
    anchor_id = str(st.session_state.pop(state_key, "") or "").strip()
    if not anchor_id:
        return
    st.markdown(
        f"""
        <script>
        const target = window.parent.document.getElementById({anchor_id!r});
        if (target) {{
            setTimeout(() => target.scrollIntoView({{block: 'center', behavior: 'auto'}}), 80);
        }}
        </script>
        """,
        unsafe_allow_html=True,
    )


def _render_result_list(candidates, meta_getter, state_key, key_prefix):
    for index, name in enumerate(candidates):
        rows, total_qty, summary = meta_getter(name)
        anchor_id = f"result-anchor-{key_prefix}-{index}-{_safe_key(name)}"
        st.markdown(f'<div id="{anchor_id}"></div>', unsafe_allow_html=True)
        row_key = f"mobile_result_row_{key_prefix}_{index}_{_safe_key(name)}"
        with st.container(border=True, key=row_key):
            photo_col, info_col, action_col = st.columns(
                [1.2, 3.25, 1.8],
                gap="small",
                vertical_alignment="center",
            )
            with photo_col:
                st.markdown(_thumbnail_html(name), unsafe_allow_html=True)
            with info_col:
                expiry_html = _expiry_badge(rows) if key_prefix.startswith("mobile_expiry") else ""
                st.markdown(
                    '<div class="mobile-result-info">'
                    f'<div class="mobile-result-name">{html.escape(str(name))}</div>'
                    f'<div class="mobile-result-company">{summary or "재고 없음"}</div>'
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
                            _remember_result_state(key_prefix, anchor_id)
                            st.session_state[state_key] = name
                            mobile_stock._remember_recent_search(name)
                            st.rerun()


def _render_stock_detail_view(product_name):
    st.markdown('<div class="mobile-back-button">', unsafe_allow_html=True)
    go_back = st.button("‹ 검색 결과", key="mobile_search_back")
    st.markdown("</div>", unsafe_allow_html=True)
    if go_back:
        st.session_state.pop(base.base.base.DETAIL_STATE_KEY, None)
        saved_term = str(st.session_state.get("mobile_stock_return_term", "") or "")
        st.session_state["mobile_product_term"] = saved_term
        st.rerun()
    base._render_stock_detail(product_name)


def _render_expiry_detail(product_name, source_df):
    st.markdown('<div class="mobile-back-button">', unsafe_allow_html=True)
    go_back = st.button("‹ 검색 결과", key="mobile_expiry_back")
    st.markdown("</div>", unsafe_allow_html=True)
    if go_back:
        st.session_state.pop(base.base.base.EXPIRY_DETAIL_STATE_KEY, None)
        saved_term = str(st.session_state.get("mobile_expiry_return_term", "") or "")
        st.session_state["mobile_expiry_search_value"] = saved_term
        st.rerun()
    base._render_expiry_detail(product_name, source_df)


def _render_expiry_tab():
    detail_product = str(st.session_state.get(base.base.base.EXPIRY_DETAIL_STATE_KEY, "") or "").strip()
    if detail_product:
        period = st.session_state.get("mobile_expiry_period", "1년 이내")
        exclude_bidata = bool(st.session_state.get("mobile_expiry_exclude_bidata", True))
        df = base.base.base._filtered_expiry_df(period, exclude_bidata)
        _render_expiry_detail(detail_product, df)
        return

    term = base.base.base._live_input(
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
    _restore_anchor("mobile_expiry_return_anchor")


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
        result = base.page_mobile_stock_finder()
        _restore_anchor("mobile_stock_return_anchor")
        return result
    finally:
        base._inject_mobile_search_css = original_inject
        base._render_result_list = original_result
        base._render_stock_detail_view = original_stock_detail
        base._render_expiry_detail = original_expiry_detail
        base._render_expiry_tab = original_expiry
