import base64
import html
import mimetypes
from pathlib import Path

import pandas as pd
import streamlit as st

import nohtus.pages.mobile_stock as mobile_stock
from nohtus.services.location_map import get_product_image_path


DETAIL_STATE_KEY = "mobile_search_detail_product"
EXPIRY_DETAIL_STATE_KEY = "mobile_expiry_detail_product"
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_THUMB_DIR = _PROJECT_ROOT / "data" / "product_images" / "thumbs"


def _inject_mobile_search_css():
    st.markdown(
        """
        <style>
        header[data-testid="stHeader"] { height: 0 !important; }
        div[data-testid="stAppViewContainer"] .main .block-container {
            padding-top: .35rem !important;
        }
        @media (max-width: 768px) {
            div[data-testid="stAppViewContainer"] .main .block-container {
                padding: .25rem .75rem 2rem !important;
                max-width: 760px !important;
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
            .mobile-search-section {
                margin: 15px 0 7px;
                font-size: 14px;
                font-weight: 700;
                color: #202636;
            }
            .mobile-result-list {
                overflow: hidden;
                border-top: 1px solid #e7eaf0;
                border-bottom: 1px solid #e7eaf0;
                background: #ffffff;
            }
            .mobile-result-row {
                position: relative;
                min-height: 72px;
                padding: 10px 90px 9px 70px;
                border-bottom: 1px solid #edf0f4;
                background: #ffffff;
            }
            .mobile-result-row.last-row { border-bottom: 0; }
            .mobile-result-thumb {
                position: absolute;
                left: 10px;
                top: 50%;
                width: 48px;
                height: 48px;
                transform: translateY(-50%);
                overflow: hidden;
                display: flex;
                align-items: center;
                justify-content: center;
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
                right: 33px;
                transform: translateY(-50%);
                font-size: 13px;
                font-weight: 700;
                color: #253148;
                white-space: nowrap;
            }
            .mobile-result-arrow {
                position: absolute;
                top: 50%;
                right: 13px;
                transform: translateY(-50%);
                font-size: 22px;
                font-weight: 300;
                color: #adb4c1;
            }
            .mobile-result-click div[data-testid="stButton"] {
                position: relative;
                z-index: 2;
                margin-top: -72px !important;
                margin-bottom: 0 !important;
            }
            .mobile-result-click div[data-testid="stButton"] button {
                height: 72px !important;
                min-height: 72px !important;
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
            .mobile-filter-row { margin-top: -4px; }
            [data-testid="stDataFrame"] { font-size: 12px !important; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _image_data_uri(path_value):
    path = Path(str(path_value or ""))
    if not path.is_file():
        return ""
    try:
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    except OSError:
        return ""
    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    return f"data:{mime};base64,{encoded}"


def _product_thumbnail_uri(product_name):
    original_path = get_product_image_path(product_name)
    if not original_path:
        return ""
    original = Path(original_path)
    thumb = _THUMB_DIR / f"{original.stem}.jpg"
    return _image_data_uri(thumb if thumb.is_file() else original)


def _live_input(key, value_key, placeholder):
    if mobile_stock.st_keyup is not None:
        return mobile_stock.st_keyup(
            "검색",
            value=st.session_state.get(value_key, ""),
            key=key,
            placeholder=placeholder,
            debounce=120,
            label_visibility="collapsed",
        ) or ""
    return st.text_input(
        "검색",
        key=key,
        placeholder=placeholder,
        label_visibility="collapsed",
    ) or ""


def _stock_meta(name):
    rows = mobile_stock.mobile_stock_rows(name)
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


def _render_result_list(candidates, meta_getter, state_key, key_prefix):
    st.markdown('<div class="mobile-result-list">', unsafe_allow_html=True)
    for index, name in enumerate(candidates):
        _, total_qty, summary = meta_getter(name)
        last_class = " last-row" if index == len(candidates) - 1 else ""
        thumbnail_uri = _product_thumbnail_uri(name)
        thumbnail_html = (
            f'<img src="{thumbnail_uri}" alt="{html.escape(str(name))}">' if thumbnail_uri else "📷"
        )
        st.markdown(
            f"""
            <div class="mobile-result-row{last_class}">
                <div class="mobile-result-thumb">{thumbnail_html}</div>
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
            key=f"{key_prefix}_{index}_{name}",
            use_container_width=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)
        if clicked:
            st.session_state[state_key] = name
            mobile_stock._remember_recent_search(name)
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)


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


def _render_stock_detail(_username, product_name):
    rows = mobile_stock.mobile_stock_rows(product_name)
    total_qty = int(rows["qty"].sum()) if not rows.empty else 0
    st.markdown(f"<div class='mobile-stock-title'>{html.escape(product_name)}</div>", unsafe_allow_html=True)
    st.markdown(f"### 총 {total_qty:,}개")
    if rows.empty:
        st.warning("현재 재고가 없습니다.")
        return

    company_totals = rows.groupby("company")["qty"].sum().sort_index()
    summary = " · ".join(f"{company} {int(qty):,}개" for company, qty in company_totals.items())
    st.markdown(f"<div class='mobile-summary'>{summary}</div>", unsafe_allow_html=True)

    detail = rows.copy()
    detail["유통기한"] = detail["exp_date"].apply(mobile_stock.display_date_only)
    detail = detail.rename(
        columns={"company": "사업장", "location": "로케이션", "lot": "제조번호", "qty": "수량"}
    )
    st.dataframe(
        detail[["사업장", "로케이션", "제조번호", "유통기한", "수량"]],
        use_container_width=True,
        hide_index=True,
    )


def _render_detail_view(username, product_name):
    st.markdown('<div class="mobile-back-button">', unsafe_allow_html=True)
    go_back = st.button("‹ 검색 결과", key="mobile_search_back")
    st.markdown("</div>", unsafe_allow_html=True)
    if go_back:
        st.session_state.pop(DETAIL_STATE_KEY, None)
        st.rerun()
    _render_stock_detail(username, product_name)


def _render_mobile_search(username):
    detail_product = str(st.session_state.get(DETAIL_STATE_KEY, "") or "").strip()
    if detail_product:
        _render_detail_view(username, detail_product)
        return

    st.title("재고 검색")
    term = _live_input("mobile_product_term_live", "mobile_product_term", "제품명 또는 별칭 검색")
    if not term.strip():
        recent = st.session_state.get("mobile_recent_searches", [])
        if recent:
            _render_recent_links(recent, DETAIL_STATE_KEY, "recent_stock")
        return

    candidates = mobile_stock.mobile_product_candidates(term, limit=20)
    if not candidates:
        st.caption("검색 결과가 없습니다.")
        return
    st.markdown(f'<div class="mobile-search-section">검색 결과 {len(candidates)}건</div>', unsafe_allow_html=True)
    _render_result_list(candidates, _stock_meta, DETAIL_STATE_KEY, "mobile_stock_result")


def _filtered_expiry_df(period, exclude_bidata):
    limits = {"3개월 이내": 90, "6개월 이내": 180, "1년 이내": 365}
    df = mobile_stock._expiry_inventory(days_limit=365)
    if exclude_bidata and not df.empty:
        df = df[df["company"].astype(str).str.strip() != "비자료"]
    if period in limits and not df.empty:
        df = df[(df["남은일수"] >= 0) & (df["남은일수"] <= limits[period])]
    return df


def _render_expiry_detail(product_name, source_df):
    st.markdown('<div class="mobile-back-button">', unsafe_allow_html=True)
    go_back = st.button("‹ 검색 결과", key="mobile_expiry_back")
    st.markdown("</div>", unsafe_allow_html=True)
    if go_back:
        st.session_state.pop(EXPIRY_DETAIL_STATE_KEY, None)
        st.rerun()

    rows = source_df[source_df["product_name"].astype(str) == str(product_name)].copy()
    total_qty = int(rows["qty"].sum()) if not rows.empty else 0
    st.markdown(f"<div class='mobile-stock-title'>{html.escape(product_name)}</div>", unsafe_allow_html=True)
    st.markdown(f"### 총 {total_qty:,}개")
    if rows.empty:
        st.info("조건에 맞는 임박재고가 없습니다.")
        return
    rows = rows.sort_values(["_expiry", "company", "location", "lot"])
    rows["유통기한"] = rows["_expiry"].dt.strftime("%Y.%m.%d")
    rows = rows.rename(
        columns={"company": "사업장", "location": "로케이션", "lot": "제조번호", "qty": "수량"}
    )
    st.dataframe(
        rows[["사업장", "로케이션", "제조번호", "유통기한", "수량"]],
        use_container_width=True,
        hide_index=True,
    )


def _render_expiry_inventory():
    st.title("임박재고")
    period_col, exclude_col = st.columns([4.3, 1.7], gap="small")
    with period_col:
        period = st.radio(
            "기간",
            ["전체", "3개월 이내", "6개월 이내", "1년 이내"],
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
    detail_product = str(st.session_state.get(EXPIRY_DETAIL_STATE_KEY, "") or "").strip()
    if detail_product:
        _render_expiry_detail(detail_product, df)
        return

    term = _live_input("mobile_expiry_search_live", "mobile_expiry_search_value", "제품명 또는 별칭 검색")
    if df.empty:
        st.info("조건에 맞는 임박재고가 없습니다.")
        return

    available_names = df["product_name"].dropna().astype(str).drop_duplicates().tolist()
    if not term.strip():
        st.caption(f"임박재고 제품 {len(available_names):,}종")
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
    st.markdown(f'<div class="mobile-search-section">검색 결과 {len(candidates)}건</div>', unsafe_allow_html=True)
    _render_result_list(
        candidates,
        lambda name: _expiry_meta(name, df),
        EXPIRY_DETAIL_STATE_KEY,
        "mobile_expiry_result",
    )


def page_mobile_stock_finder():
    """모바일 재고검색과 임박재고를 앱형 검색 UX로 렌더링한다."""
    _inject_mobile_search_css()
    original_search = mobile_stock._render_mobile_search
    original_detail = mobile_stock._render_product_detail
    original_expiry = mobile_stock._render_expiry_inventory
    mobile_stock._render_mobile_search = _render_mobile_search
    mobile_stock._render_product_detail = _render_stock_detail
    mobile_stock._render_expiry_inventory = _render_expiry_inventory
    try:
        return mobile_stock.page_mobile_stock_finder()
    finally:
        mobile_stock._render_mobile_search = original_search
        mobile_stock._render_product_detail = original_detail
        mobile_stock._render_expiry_inventory = original_expiry
