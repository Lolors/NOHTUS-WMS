from __future__ import annotations

import html

import pandas as pd
import streamlit as st

import nohtus.pages.mobile_stock as mobile_stock
import nohtus.pages.mobile_stock_layout_patch_v3 as mobile_layout
from nohtus.pages.mobile_stock_layout_patch_v3 import page_mobile_stock_finder as _page_mobile_stock_finder


_MATERIAL_OR_PROMO_PREFIXES = ("G1", "G2")
_MATERIAL_OR_PROMO_KEYWORDS = ("부자재", "홍보물")


def _normalized_location(value):
    return str(value or "").strip().upper().replace(" ", "").replace("-", "").replace("_", "")


def _is_material_or_promo_location(value):
    location = _normalized_location(value)
    return (
        location.startswith(_MATERIAL_OR_PROMO_PREFIXES)
        or any(keyword in location for keyword in _MATERIAL_OR_PROMO_KEYWORDS)
    )


def _is_export_waiting_location(value):
    """P, P1, P2 등 수출대기 로케이션인지 확인한다."""
    return _normalized_location(value).startswith("P")


def _exclude_material_or_promo_rows(df):
    if not isinstance(df, pd.DataFrame) or df.empty or "location" not in df.columns:
        return df
    return df.loc[~df["location"].apply(_is_material_or_promo_location)].copy()


def _has_export_waiting_stock(rows):
    if not isinstance(rows, pd.DataFrame) or rows.empty or "location" not in rows.columns:
        return False
    return bool(rows["location"].apply(_is_export_waiting_location).any())


def _inject_export_waiting_badge_css():
    st.markdown(
        """
        <style>
        @media (max-width: 768px) {
            .mobile-export-waiting-row {
                margin-top: 5px !important;
                line-height: 1 !important;
            }
            .mobile-export-waiting-badge {
                display: inline-flex !important;
                align-items: center !important;
                width: fit-content !important;
                padding: 4px 8px !important;
                border: 1px solid #bae6fd !important;
                border-radius: 999px !important;
                background: #e0f2fe !important;
                color: #0369a1 !important;
                font-size: 10.5px !important;
                font-weight: 700 !important;
                line-height: 1 !important;
                white-space: nowrap !important;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_result_list_with_export_badge(candidates, meta_getter, state_key, key_prefix):
    """임박재고 카드의 사업장 재고 아래에 수출대기 배지를 표시한다."""
    for index, name in enumerate(candidates):
        rows, total_qty, summary = meta_getter(name)
        row_key = f"mobile_result_row_{key_prefix}_{index}_{mobile_layout.base.base._safe_key(name)}"
        with st.container(border=True, key=row_key):
            info_col, action_col = st.columns(
                [4.2, 1.8],
                gap="small",
                vertical_alignment="center",
            )
            with info_col:
                is_expiry_result = key_prefix.startswith("mobile_expiry")
                expiry_html = mobile_layout._expiry_badge(rows) if is_expiry_result else ""
                export_badge_html = ""
                if is_expiry_result and _has_export_waiting_stock(rows):
                    export_badge_html = (
                        '<div class="mobile-export-waiting-row">'
                        '<span class="mobile-export-waiting-badge">✈️수출대기중</span>'
                        '</div>'
                    )
                st.markdown(
                    '<div class="mobile-result-info">'
                    f'<div class="mobile-result-name">{html.escape(str(name))}</div>'
                    f'<div class="mobile-result-company">{html.escape(str(summary or "재고 없음"))}</div>'
                    f'{export_badge_html}'
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
                            mobile_layout._remember_result_state(key_prefix, name, index)
                            st.session_state[state_key] = name
                            mobile_stock._remember_recent_search(name)
                            st.rerun()


def page_mobile_stock_finder():
    """모바일 재고 화면에서는 부자재 및 홍보물 재고를 항상 제외한다."""
    original_stock_rows = mobile_stock.mobile_stock_rows
    original_candidates = mobile_stock.mobile_product_candidates
    original_expiry_inventory = mobile_stock._expiry_inventory
    original_favorites = mobile_stock.mobile_favorites_for_user
    original_render_result_list = mobile_layout._render_result_list

    def filtered_stock_rows(product_name, company_filter="전체", expiry_filter="전체"):
        rows = original_stock_rows(product_name, company_filter, expiry_filter)
        return _exclude_material_or_promo_rows(rows)

    def has_visible_stock(product_name):
        rows = original_stock_rows(product_name)
        rows = _exclude_material_or_promo_rows(rows)
        return isinstance(rows, pd.DataFrame) and not rows.empty

    def filtered_candidates(term="", limit=30):
        # 부자재/홍보물 위치에만 재고가 있는 제품은 검색 카드 자체를 만들지 않는다.
        candidates = original_candidates(term, limit=max(int(limit or 0) * 5, 100))
        visible = [name for name in candidates if has_visible_stock(name)]
        return visible[:limit]

    def filtered_expiry_inventory(days_limit=365):
        return _exclude_material_or_promo_rows(original_expiry_inventory(days_limit))

    def filtered_favorites(username):
        favorites = original_favorites(username)
        if not isinstance(favorites, pd.DataFrame) or favorites.empty or "product_name" not in favorites.columns:
            return favorites
        keep = favorites["product_name"].astype(str).apply(has_visible_stock)
        return favorites.loc[keep].copy()

    mobile_stock.mobile_stock_rows = filtered_stock_rows
    mobile_stock.mobile_product_candidates = filtered_candidates
    mobile_stock._expiry_inventory = filtered_expiry_inventory
    mobile_stock.mobile_favorites_for_user = filtered_favorites
    mobile_layout._render_result_list = _render_result_list_with_export_badge
    try:
        _inject_export_waiting_badge_css()
        recent = mobile_stock.st.session_state.get("mobile_recent_searches", [])
        if recent:
            mobile_stock.st.session_state["mobile_recent_searches"] = [
                name for name in recent if has_visible_stock(name)
            ]
        return _page_mobile_stock_finder()
    finally:
        mobile_stock.mobile_stock_rows = original_stock_rows
        mobile_stock.mobile_product_candidates = original_candidates
        mobile_stock._expiry_inventory = original_expiry_inventory
        mobile_stock.mobile_favorites_for_user = original_favorites
        mobile_layout._render_result_list = original_render_result_list
