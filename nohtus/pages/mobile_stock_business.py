"""모바일 재고 화면(재고 검색 / 임박재고).

과거엔 mobile_stock.py -> mobile_stock_live_fix.py -> mobile_stock_layout_patch.py(v1)
-> _v2.py -> _v3.py -> 이 파일까지 5단계가 서로를 몽키패치로 감싸며 조금씩
기능을 얹은 구조였다. 각 레이어가 실제로 무엇을 최종적으로 그리는지 끝까지
추적해서(즐겨찾기, mobile_stock.py의 라디오 모드 분기, 각 레이어에서
다음 레이어에 덮어써진 자기 버전들은 전부 죽은 코드였음 — 이미 별도 정리에서
삭제됨) 그 최종 합성 동작만 몽키패치 없이 이 파일 하나로 옮겼다.

옮기면서 발견한 실제 불일치 하나를 통일했다: 예전엔 재고 검색 탭은 제품
사진을 한 장씩 조회하고 수출대기 배지가 없었는데, 임박재고 탭은 사진을
일괄 조회하고 수출대기 배지가 있었다 — 이제 두 탭 다 후자로 통일한다.
"""

from __future__ import annotations

import html
import re

import pandas as pd
import streamlit as st

import nohtus.pages.mobile_stock as mobile_stock
import nohtus.pages.mobile_theme as mobile_theme
from nohtus.services import expiry_rules
from nohtus.services.location_map import product_thumbnail_uris_for
from nohtus.services.stock_rules import (
    exclude_material_or_promo_rows,
    is_export_waiting_location,
)

DETAIL_STATE_KEY = "mobile_search_detail_product"
EXPIRY_DETAIL_STATE_KEY = "mobile_expiry_detail_product"


# ---------------------------------------------------------------------------
# 스타일
# ---------------------------------------------------------------------------

def _inject_mobile_search_css():
    st.markdown(
        """
        <style>
        header[data-testid="stHeader"] {
            height: 0 !important;
            min-height: 0 !important;
            display: none !important;
        }

        @media (max-width: 768px) {
            html, body, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
                margin-top: 0 !important;
                padding-top: 0 !important;
            }

            [data-testid="stMainBlockContainer"],
            section.main > div.block-container,
            div[data-testid="stAppViewContainer"] .main .block-container {
                padding: 0 .65rem 1.5rem !important;
                margin-top: 0 !important;
                transform: translateY(-62px) !important;
                margin-bottom: -62px !important;
            }

            div[data-testid="stTextInput"] input {
                height: 46px !important;
                border-radius: 13px !important;
                border: 1px solid #d9dee7 !important;
                background: #ffffff !important;
                box-shadow: none !important;
                padding: 0 15px !important;
                font-size: 15px !important;
            }
            div[data-testid="stTextInput"] input:focus {
                border-color: #8aa4d6 !important;
                box-shadow: 0 0 0 2px rgba(92, 124, 250, .08) !important;
            }

            div[data-testid="stTabs"] [data-baseweb="tab-list"] {
                gap: 0 !important;
                border-bottom: 1px solid #e5e7eb !important;
                margin: 0 0 10px !important;
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
            div[data-testid="stTabs"] [data-baseweb="tab-panel"] {
                padding-top: 0 !important;
            }

            .mobile-search-section {
                margin: 15px 0 7px;
                font-size: 14px;
                font-weight: 700;
                color: #202636;
            }

            .mobile-back-button div[data-testid="stButton"] button {
                min-height: 36px !important;
                margin-bottom: 2px !important;
                padding: 0 2px !important;
                border: 0 !important;
                background: transparent !important;
                color: #46546d !important;
                box-shadow: none !important;
                justify-content: flex-start !important;
                font-size: 13px !important;
                font-weight: 600 !important;
            }
            .mobile-recent-link div[data-testid="stButton"] {
                margin: 0 !important;
            }
            .mobile-recent-link div[data-testid="stButton"] button {
                min-height: 30px !important;
                height: auto !important;
                width: auto !important;
                padding: 2px 0 !important;
                border: 0 !important;
                border-radius: 0 !important;
                background: transparent !important;
                color: #334155 !important;
                box-shadow: none !important;
                justify-content: flex-start !important;
                font-size: 14px !important;
                font-weight: 500 !important;
                text-decoration: none !important;
            }
            .mobile-recent-link div[data-testid="stButton"] button:hover {
                color: #2563eb !important;
                text-decoration: underline !important;
            }

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
                grid-template-columns: 52px minmax(0, 1fr) 150px !important;
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
            .mobile-result-thumb {
                width: 48px;
                height: 48px;
                display: flex;
                align-items: center;
                justify-content: center;
                overflow: hidden;
                border-radius: 8px;
                background: #f8fafc;
                color: #a7afbd;
                font-size: 19px;
            }
            .mobile-result-thumb img {
                width: 100%;
                height: 100%;
                display: block;
                object-fit: contain;
                object-position: center;
                background: #ffffff;
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

            div[class*="st-key-recent_stock_"] div[data-testid="stButton"],
            div[class*="st-key-recent_expiry_"] div[data-testid="stButton"] {
                margin: -2px 0 !important;
            }
            div[class*="st-key-recent_stock_"] div[data-testid="stButton"] button,
            div[class*="st-key-recent_expiry_"] div[data-testid="stButton"] button {
                min-height: 30px !important;
                height: 30px !important;
                padding: 3px 9px !important;
                line-height: 1.15 !important;
                border-radius: 7px !important;
            }

            div[class*="st-key-mobile_expiry_search_live"] {
                margin-bottom: -8px !important;
            }
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

            .mobile-detail-header {
                display: grid;
                grid-template-columns: 104px minmax(0, 1fr) auto;
                gap: 12px;
                align-items: center;
                margin: 2px 0 10px;
            }
            .mobile-detail-photo {
                width: 96px;
                height: 96px;
                border-radius: 12px;
                overflow: hidden;
                background: #f8fafc;
                display: flex;
                align-items: center;
                justify-content: center;
            }
            .mobile-detail-photo:empty {
                box-sizing: border-box !important;
                border: 1.5px dashed #b8c0cc !important;
                border-radius: 12px !important;
                background: #fafbfc !important;
            }
            .mobile-detail-photo img {
                width: 100%;
                height: 100%;
                object-fit: cover;
                background: #fff;
            }
            .mobile-detail-name {
                font-size: 21px;
                line-height: 1.25;
                font-weight: 850;
                color: #172033;
                word-break: keep-all;
                margin-bottom: 8px;
            }
            .mobile-detail-company {
                font-size: 13px;
                line-height: 1.55;
                color: #687386;
            }
            .mobile-detail-total {
                font-size: 23px;
                line-height: 1;
                font-weight: 900;
                color: #172033;
                white-space: nowrap;
                text-align: right;
            }
            .mobile-detail-table-gap {
                height: 10px;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# 데이터 조회 (부자재/홍보물 위치 재고는 모바일 화면에서 항상 제외)
# ---------------------------------------------------------------------------

def _stock_rows(product_name, company_filter="전체", expiry_filter="전체"):
    rows = mobile_stock.mobile_stock_rows(product_name, company_filter, expiry_filter)
    return exclude_material_or_promo_rows(rows)


def _has_visible_stock(product_name):
    rows = exclude_material_or_promo_rows(mobile_stock.mobile_stock_rows(product_name))
    return isinstance(rows, pd.DataFrame) and not rows.empty


def _product_candidates(term="", limit=30):
    # 부자재/홍보물 위치에만 재고가 있는 제품은 검색 카드 자체를 만들지 않는다.
    candidates = mobile_stock.mobile_product_candidates(term, limit=max(int(limit or 0) * 5, 100))
    visible = [name for name in candidates if _has_visible_stock(name)]
    return visible[:limit]


def _filtered_expiry_df(period, exclude_bidata):
    df = exclude_material_or_promo_rows(mobile_stock._expiry_inventory(days_limit=365))
    if exclude_bidata and not df.empty:
        df = df[df["company"].astype(str).str.strip() != "비자료"]
    if period in expiry_rules.PERIOD_DAYS_KO and not df.empty:
        df = df[(df["남은일수"] >= 0) & (df["남은일수"] <= expiry_rules.PERIOD_DAYS_KO[period])]
    return df


def _stock_meta(name):
    rows = _stock_rows(name)
    total_qty = int(rows["qty"].sum()) if not rows.empty else 0
    company_totals = rows.groupby("company")["qty"].sum() if not rows.empty else pd.Series(dtype=float)
    summary = " · ".join(
        f"{html.escape(str(company))} {int(qty):,}"
        for company, qty in company_totals.items()
        if int(qty or 0) > 0
    )
    return rows, total_qty, summary


def _expiry_meta(name, source_df):
    rows = source_df[source_df["product_name"].astype(str) == str(name)].copy()
    total_qty = int(rows["qty"].sum()) if not rows.empty else 0
    company_totals = rows.groupby("company")["qty"].sum() if not rows.empty else pd.Series(dtype=float)
    summary = " · ".join(
        f"{html.escape(str(company))} {int(qty):,}"
        for company, qty in company_totals.items()
        if int(qty or 0) > 0
    )
    return rows, total_qty, summary


def _expiry_badge(rows):
    if rows is None or rows.empty or "_expiry" not in rows.columns:
        return ""
    badge = expiry_rules.expiry_badge_for(rows["_expiry"].min())
    if not badge:
        return ""
    return (
        '<div class="mobile-expiry-date-row">'
        f'<span>{html.escape(badge["date"])}</span>'
        f'<span class="mobile-expiry-badge {badge["level"]}">{badge["label"]}</span>'
        '</div>'
    )


def _has_export_waiting_stock(rows):
    if not isinstance(rows, pd.DataFrame) or rows.empty or "location" not in rows.columns:
        return False
    return bool(rows["location"].apply(is_export_waiting_location).any())


# ---------------------------------------------------------------------------
# 검색/스크롤 상태
# ---------------------------------------------------------------------------

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


def _safe_key(value):
    return re.sub(r"[^0-9A-Za-z가-힣_-]+", "_", str(value or ""))[:60]


# ---------------------------------------------------------------------------
# 렌더링
# ---------------------------------------------------------------------------

def _render_result_list(candidates, meta_getter, state_key, key_prefix):
    thumbnails = product_thumbnail_uris_for(candidates)
    for index, name in enumerate(candidates):
        rows, total_qty, summary = meta_getter(name)
        row_key = f"mobile_result_row_{key_prefix}_{index}_{_safe_key(name)}"
        with st.container(border=True, key=row_key):
            thumb_col, info_col, action_col = st.columns(
                [0.9, 3.3, 1.8],
                gap="small",
                vertical_alignment="center",
            )
            with thumb_col:
                thumbnail_uri = thumbnails.get(str(name).strip())
                thumbnail_html = f'<img src="{thumbnail_uri}" alt="">' if thumbnail_uri else "📷"
                st.markdown(
                    f'<div class="mobile-result-thumb">{thumbnail_html}</div>',
                    unsafe_allow_html=True,
                )
            with info_col:
                expiry_html = _expiry_badge(rows)
                export_badge_html = ""
                if _has_export_waiting_stock(rows):
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
                            _remember_result_state(key_prefix, name, index)
                            st.session_state[state_key] = name
                            mobile_stock._remember_recent_search(name)
                            st.rerun()


def _render_recent_links(names, state_key, key_prefix):
    st.markdown('<div class="mobile-search-section">최근 검색어</div>', unsafe_allow_html=True)
    for index, name in enumerate(names):
        st.markdown('<div class="mobile-recent-link">', unsafe_allow_html=True)
        clicked = st.button(str(name), key=f"{key_prefix}_{index}_{name}")
        st.markdown("</div>", unsafe_allow_html=True)
        if clicked:
            st.session_state[state_key] = name
            mobile_stock._remember_recent_search(name)
            st.rerun()


def _detail_header(product_name, rows):
    total_qty = int(rows["qty"].sum()) if not rows.empty else 0
    company_totals = rows.groupby("company")["qty"].sum().sort_index() if not rows.empty else []
    company_html = " · ".join(
        f"{html.escape(str(company))} {int(qty):,}개" for company, qty in getattr(company_totals, "items", lambda: [])()
    ) or "재고 없음"
    thumb = product_thumbnail_uris_for([product_name]).get(str(product_name).strip(), "")
    photo_html = f'<img src="{thumb}" alt="{html.escape(product_name)}">' if thumb else ""
    st.markdown(
        f"""
        <div class="mobile-detail-header">
            <div class="mobile-detail-photo">{photo_html}</div>
            <div>
                <div class="mobile-detail-name">{html.escape(product_name)}</div>
                <div class="mobile-detail-company">{company_html}</div>
            </div>
            <div class="mobile-detail-total">{total_qty:,}개</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_stock_detail(product_name):
    rows = _stock_rows(product_name)
    _detail_header(product_name, rows)
    if rows.empty:
        st.warning("현재 재고가 없습니다.")
        return
    detail = rows.copy()
    detail["유통기한"] = detail["exp_date"].apply(mobile_stock.display_date_only)
    detail = detail.rename(
        columns={"company": "사업장", "location": "로케이션", "lot": "제조번호", "qty": "수량"}
    )
    st.markdown('<div class="mobile-detail-table-gap"></div>', unsafe_allow_html=True)
    mobile_theme.render_location_cards(
        detail[["사업장", "로케이션", "제조번호", "유통기한", "수량"]],
        empty_message="현재 재고가 없습니다.",
    )


def _render_stock_detail_view(product_name):
    st.markdown('<div class="mobile-back-button">', unsafe_allow_html=True)
    go_back = st.button("‹ 검색 결과", key="mobile_search_back")
    st.markdown("</div>", unsafe_allow_html=True)
    if go_back:
        st.session_state.pop(DETAIL_STATE_KEY, None)
        saved_term = str(st.session_state.get("mobile_stock_return_term", "") or "")
        st.session_state["mobile_product_term"] = saved_term
        st.rerun()
    _render_stock_detail(product_name)


def _render_expiry_detail(product_name, source_df):
    st.markdown('<div class="mobile-back-button">', unsafe_allow_html=True)
    go_back = st.button("‹ 검색 결과", key="mobile_expiry_back")
    st.markdown("</div>", unsafe_allow_html=True)
    if go_back:
        st.session_state.pop(EXPIRY_DETAIL_STATE_KEY, None)
        saved_term = str(st.session_state.get("mobile_expiry_return_term", "") or "")
        st.session_state["mobile_expiry_search_value"] = saved_term
        st.rerun()

    rows = source_df[source_df["product_name"].astype(str) == str(product_name)].copy()
    _detail_header(product_name, rows)
    if rows.empty:
        st.info("조건에 맞는 임박재고가 없습니다.")
        return
    rows = rows.sort_values(["_expiry", "company", "location", "lot"])
    rows["유통기한"] = rows["_expiry"].dt.strftime("%Y.%m.%d")
    rows = rows.rename(
        columns={"company": "사업장", "location": "로케이션", "lot": "제조번호", "qty": "수량"}
    )
    st.markdown('<div class="mobile-detail-table-gap"></div>', unsafe_allow_html=True)
    mobile_theme.render_location_cards(
        rows[["사업장", "로케이션", "제조번호", "유통기한", "수량"]],
        empty_message="조건에 맞는 임박재고가 없습니다.",
    )


def _render_stock_tab():
    detail_product = str(st.session_state.get(DETAIL_STATE_KEY, "") or "").strip()
    if detail_product:
        _render_stock_detail_view(detail_product)
        return

    term = _live_input("mobile_product_term_live", "mobile_product_term", "제품명 또는 별칭 검색")
    if not term.strip():
        recent = st.session_state.get("mobile_recent_searches", [])
        if recent:
            _render_recent_links(recent, DETAIL_STATE_KEY, "recent_stock")
        return

    candidates = _product_candidates(term, limit=20)
    if not candidates:
        st.caption("검색 결과가 없습니다.")
        return
    st.markdown(f'<div class="mobile-search-section">검색 결과 {len(candidates)}건</div>', unsafe_allow_html=True)
    _render_result_list(candidates, _stock_meta, DETAIL_STATE_KEY, "mobile_stock_result")
    _restore_result_position("mobile_stock_return_index", "mobile_stock_result")


def _render_expiry_tab():
    detail_product = str(st.session_state.get(EXPIRY_DETAIL_STATE_KEY, "") or "").strip()

    if detail_product:
        period = st.session_state.get("mobile_expiry_period", "1년 이내")
        exclude_bidata = bool(st.session_state.get("mobile_expiry_exclude_bidata", True))
        df = _filtered_expiry_df(period, exclude_bidata)
        _render_expiry_detail(detail_product, df)
        return

    term = _live_input("mobile_expiry_search_live", "mobile_expiry_search_value", "제품명 또는 별칭 검색")

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

    df = _filtered_expiry_df(period, exclude_bidata)
    if df.empty:
        st.info("조건에 맞는 임박재고가 없습니다.")
        return

    available_names = df["product_name"].dropna().astype(str).drop_duplicates().tolist()
    if not term.strip():
        candidates = available_names
    else:
        matched = _product_candidates(term, limit=100)
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
    st.markdown(f'<div class="mobile-search-section">검색 결과 {len(candidates)}건</div>', unsafe_allow_html=True)
    _render_result_list(
        candidates,
        lambda name: _expiry_meta(name, df),
        EXPIRY_DETAIL_STATE_KEY,
        "mobile_expiry_result",
    )
    _restore_result_position("mobile_expiry_return_index", "mobile_expiry_result")


def page_mobile_stock_finder():
    """모바일 재고 화면에서는 부자재 및 홍보물 재고를 항상 제외한다."""
    recent = st.session_state.get("mobile_recent_searches", [])
    if recent:
        st.session_state["mobile_recent_searches"] = [name for name in recent if _has_visible_stock(name)]

    mobile_theme.render_app_bar()
    _inject_mobile_search_css()
    mobile_theme.inject_mobile_theme()
    stock_tab, expiry_tab = st.tabs(["🔍  재고 검색", "⏰  임박재고"])
    with stock_tab:
        _render_stock_tab()
    with expiry_tab:
        _render_expiry_tab()
