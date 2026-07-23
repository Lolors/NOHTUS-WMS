from datetime import datetime

import pandas as pd
import streamlit as st

try:
    from st_keyup import st_keyup
except ImportError:
    st_keyup = None

from nohtus.config_runtime import COMPANIES
from nohtus.db import connect, q
from nohtus.dates import display_date_only, expiry_status


RECENT_SEARCH_LIMIT = 6


def mobile_favorite_users():
    """모바일 재고찾기 즐겨찾기 사용자 목록."""
    try:
        df = q("SELECT DISTINCT username FROM mobile_favorites ORDER BY username")
        users = [str(x).strip() for x in df["username"].dropna().tolist() if str(x).strip()]
    except Exception:
        users = []
    return users


def mobile_favorites_for_user(username):
    username = (username or "").strip() or "기본"
    try:
        return q(
            """
            SELECT product_name, COALESCE(sort_order, 0) AS sort_order
            FROM mobile_favorites
            WHERE username=?
            ORDER BY sort_order, product_name
            """,
            (username,),
        )
    except Exception:
        return pd.DataFrame(columns=["product_name", "sort_order"])


def mobile_is_favorite(username, product_name):
    username = (username or "").strip() or "기본"
    product_name = (product_name or "").strip()
    if not product_name:
        return False
    try:
        df = q(
            "SELECT 1 FROM mobile_favorites WHERE username=? AND product_name=? LIMIT 1",
            (username, product_name),
        )
        return not df.empty
    except Exception:
        return False


def mobile_add_favorite(username, product_name):
    username = (username or "").strip() or "기본"
    product_name = (product_name or "").strip()
    if not product_name:
        return
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with connect() as con:
        cur = con.cursor()
        row = cur.execute(
            "SELECT COALESCE(MAX(sort_order), -1) FROM mobile_favorites WHERE username=?",
            (username,),
        ).fetchone()
        next_order = int((row[0] if row else -1) or -1) + 1
        cur.execute(
            """
            INSERT OR IGNORE INTO mobile_favorites(username, product_name, sort_order, created_at)
            VALUES(?,?,?,?)
            """,
            (username, product_name, next_order, now),
        )
        con.commit()


def mobile_remove_favorite(username, product_name):
    username = (username or "").strip() or "기본"
    product_name = (product_name or "").strip()
    with connect() as con:
        con.execute(
            "DELETE FROM mobile_favorites WHERE username=? AND product_name=?",
            (username, product_name),
        )
        con.commit()
    mobile_reindex_favorites(username)


def mobile_reindex_favorites(username):
    username = (username or "").strip() or "기본"
    df = mobile_favorites_for_user(username)
    with connect() as con:
        cur = con.cursor()
        for i, row in enumerate(df.itertuples(index=False)):
            cur.execute(
                "UPDATE mobile_favorites SET sort_order=? WHERE username=? AND product_name=?",
                (i, username, getattr(row, "product_name")),
            )
        con.commit()


def mobile_move_favorite(username, product_name, direction):
    username = (username or "").strip() or "기본"
    product_name = (product_name or "").strip()
    df = mobile_favorites_for_user(username)
    names = df["product_name"].astype(str).tolist() if not df.empty else []
    if product_name not in names:
        return
    idx = names.index(product_name)
    new_idx = idx - 1 if direction == "up" else idx + 1
    if new_idx < 0 or new_idx >= len(names):
        return
    names[idx], names[new_idx] = names[new_idx], names[idx]
    with connect() as con:
        cur = con.cursor()
        for i, name in enumerate(names):
            cur.execute(
                "UPDATE mobile_favorites SET sort_order=? WHERE username=? AND product_name=?",
                (i, username, name),
            )
        con.commit()


def mobile_product_candidates(term="", limit=30):
    """제품명과 별칭만 검색하고 표준제품명을 반환한다."""
    term = (term or "").strip().lower()
    if not term:
        return []
    df = q(
        """
        SELECT standard_name, aliases
        FROM products
        WHERE COALESCE(standard_name, '') <> ''
        ORDER BY standard_name, id
        """
    )
    if df.empty:
        return []

    def matches(row):
        standard_name = str(row.get("standard_name", "") or "").lower()
        aliases = str(row.get("aliases", "") or "").lower()
        return term in standard_name or term in aliases

    df = df[df.apply(matches, axis=1)].copy()
    if df.empty:
        return []
    df["_starts"] = df["standard_name"].astype(str).str.lower().str.startswith(term)
    df = df.sort_values(["_starts", "standard_name"], ascending=[False, True])
    return df["standard_name"].dropna().astype(str).drop_duplicates().head(limit).tolist()


def mobile_stock_rows(product_name, company_filter="전체", expiry_filter="전체"):
    product_name = (product_name or "").strip()
    if not product_name:
        return pd.DataFrame()
    conditions = ["product_name=?", "qty>0"]
    params = [product_name]
    if company_filter and company_filter != "전체":
        conditions.append("company=?")
        params.append(company_filter)
    where = " AND ".join(conditions)
    df = q(
        f"""
        SELECT company, location, lot, exp_date, qty
        FROM inventory
        WHERE {where}
        ORDER BY company, exp_date, location, lot
        """,
        tuple(params),
    )
    if df.empty:
        return df
    df["상태"] = df["exp_date"].apply(expiry_status)
    if expiry_filter and expiry_filter != "전체":
        df = df[df["상태"] == expiry_filter]
    return df


def _remember_recent_search(product_name):
    name = (product_name or "").strip()
    if not name:
        return
    recent = [x for x in st.session_state.get("mobile_recent_searches", []) if x != name]
    st.session_state["mobile_recent_searches"] = [name] + recent[: RECENT_SEARCH_LIMIT - 1]


def _select_product(product_name):
    name = (product_name or "").strip()
    if not name:
        return
    st.session_state["mobile_selected_product"] = name
    st.session_state["mobile_product_term"] = name
    _remember_recent_search(name)


def _expiry_inventory(days_limit=365):
    df = q(
        """
        SELECT product_name, company, location, lot, exp_date, qty
        FROM inventory
        WHERE qty > 0 AND COALESCE(product_name, '') <> ''
        ORDER BY exp_date, product_name, location, lot
        """
    )
    if df.empty:
        return df
    today = pd.Timestamp.today().normalize()
    df["_expiry"] = pd.to_datetime(df["exp_date"], errors="coerce").dt.normalize()
    df = df[df["_expiry"].notna()].copy()
    df["남은일수"] = (df["_expiry"] - today).dt.days
    return df[df["남은일수"] <= days_limit].copy()


def _mobile_css():
    st.markdown(
        """
        <style>
        @media (max-width: 768px) {
            header[data-testid="stHeader"] { height: 0 !important; }
            div[data-testid="stAppViewContainer"] .main .block-container {
                padding: .55rem .75rem 2rem !important;
                max-width: 760px !important;
            }
            h1 { font-size: 1.15rem !important; margin: .15rem 0 .7rem !important; }
            h2, h3 { margin-top: .5rem !important; }
            p, label, div[data-testid="stMarkdownContainer"] { font-size: 13px; }
            div[data-testid="stTextInput"] input { font-size: 14px !important; height: 44px; }
            div[data-testid="stSelectbox"] { margin-top: -.72rem; }
            div[data-testid="stSelectbox"] > div > div { font-size: 13px !important; }
            div[data-testid="stButton"] button {
                min-height: 40px;
                font-size: 13px !important;
                border-radius: 10px;
            }
            div[data-testid="stExpander"] details {
                border-left: 0 !important;
                border-right: 0 !important;
                border-radius: 0 !important;
            }
            div[data-testid="stExpander"] summary p { font-size: 13px !important; }
            [data-testid="stDataFrame"] { font-size: 12px !important; }
            .mobile-summary {
                padding: 10px 12px;
                background: #f5f8ff;
                border-radius: 10px;
                margin: 6px 0 10px;
                font-size: 12px;
                line-height: 1.6;
            }
            .mobile-stock-title { font-size: 15px; font-weight: 700; margin-bottom: 2px; }
            .mobile-muted { color: #6b7280; font-size: 12px; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _live_search_input():
    if st_keyup is not None:
        return st_keyup(
            "제품 검색",
            value=st.session_state.get("mobile_product_term", ""),
            key="mobile_product_term_live",
            placeholder="제품명 또는 별칭 검색",
            debounce=120,
            label_visibility="collapsed",
        ) or ""
    return st.text_input(
        "제품 검색",
        placeholder="제품명 또는 별칭 검색",
        key="mobile_product_term",
        label_visibility="collapsed",
    )


def _render_mobile_search(username):
    st.title("재고 검색")
    term = _live_search_input()
    st.session_state["mobile_product_term"] = term

    candidates = mobile_product_candidates(term, limit=20) if term.strip() else []
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
            _select_product(picked)
            st.rerun()
    elif term.strip():
        st.caption("검색 결과가 없습니다.")

    if not term.strip():
        recent = st.session_state.get("mobile_recent_searches", [])
        if recent:
            st.markdown("**최근 검색어**")
            for name in recent:
                if st.button(f"◷  {name}", key=f"recent_{name}", use_container_width=True):
                    _select_product(name)
                    st.rerun()
        return

    if candidates:
        st.markdown("**검색 결과**")
        for name in candidates:
            rows = mobile_stock_rows(name)
            total_qty = int(rows["qty"].sum()) if not rows.empty else 0
            company_totals = rows.groupby("company")["qty"].sum() if not rows.empty else pd.Series(dtype=float)
            summary = " · ".join(
                f"{company} {int(qty):,}"
                for company, qty in company_totals.items()
                if int(qty or 0) > 0
            )
            button_text = f"{name}    총 {total_qty:,}개"
            if st.button(button_text, key=f"mobile_result_{name}", use_container_width=True):
                _select_product(name)
                st.rerun()
            if summary:
                st.markdown(f"<div class='mobile-muted'>{summary}</div>", unsafe_allow_html=True)

    if selected_product and selected_product == term.strip():
        _render_product_detail(username, selected_product)


def _render_product_detail(username, selected_product):
    rows = mobile_stock_rows(selected_product)
    total_qty = int(rows["qty"].sum()) if not rows.empty else 0
    st.markdown("---")
    title_col, fav_col = st.columns([4, 2])
    with title_col:
        st.markdown(f"<div class='mobile-stock-title'>{selected_product}</div>", unsafe_allow_html=True)
        st.markdown(f"### 총 {total_qty:,}개")
    with fav_col:
        fav = mobile_is_favorite(username, selected_product)
        if fav:
            if st.button("★ 해제", key=f"mobile_unfav_{selected_product}", use_container_width=True):
                mobile_remove_favorite(username, selected_product)
                st.rerun()
        elif st.button("☆ 즐겨찾기", key=f"mobile_addfav_{selected_product}", use_container_width=True):
            mobile_add_favorite(username, selected_product)
            st.rerun()

    if rows.empty or total_qty <= 0:
        st.warning("현재 재고가 없습니다.")
        return

    company_totals = rows.groupby("company")["qty"].sum().sort_index()
    summary = " · ".join(
        f"{company} {int(qty):,}개" for company, qty in company_totals.items() if int(qty or 0) > 0
    )
    st.markdown(f"<div class='mobile-summary'>{summary}</div>", unsafe_allow_html=True)

    detail = rows.copy()
    detail["유통기한"] = detail["exp_date"].apply(display_date_only)
    detail = detail.rename(columns={"location": "로케이션", "qty": "수량", "lot": "LOT/제조번호"})
    st.dataframe(
        detail[["로케이션", "유통기한", "수량", "LOT/제조번호"]],
        use_container_width=True,
        hide_index=True,
    )


def _render_expiry_inventory():
    st.title("임박재고")
    filter_label = st.radio(
        "기간",
        ["전체", "3개월 이내", "6개월 이내", "1년 이내", "만료"],
        horizontal=True,
        label_visibility="collapsed",
        key="mobile_expiry_period",
    )
    exclude_bidata = st.checkbox(
        "비자료 제외",
        value=True,
        key="mobile_expiry_exclude_bidata",
    )
    limits = {"3개월 이내": 90, "6개월 이내": 180, "1년 이내": 365}
    df = _expiry_inventory(days_limit=365)
    if exclude_bidata and not df.empty:
        df = df[df["company"].astype(str).str.strip() != "비자료"]
    if filter_label == "만료":
        df = df[df["남은일수"] < 0]
    elif filter_label in limits:
        df = df[(df["남은일수"] >= 0) & (df["남은일수"] <= limits[filter_label])]

    search_term = st.text_input(
        "임박재고 검색",
        placeholder="제품명 검색",
        key="mobile_expiry_search",
        label_visibility="collapsed",
    ).strip().lower()
    if search_term and not df.empty:
        df = df[df["product_name"].astype(str).str.lower().str.contains(search_term, na=False)]

    if df.empty:
        st.info("조건에 맞는 임박재고가 없습니다.")
        return

    total_qty = int(df["qty"].sum())
    nearest = df["_expiry"].min().strftime("%Y.%m.%d")
    st.markdown(
        f"<div class='mobile-summary'><b>임박재고 {len(df):,}건 · 총 {total_qty:,}개</b><br>"
        f"가장 가까운 유통기한: {nearest}</div>",
        unsafe_allow_html=True,
    )

    product_summary = (
        df.groupby("product_name", as_index=False)
        .agg(총수량=("qty", "sum"), 건수=("qty", "size"), 최근유통기한=("_expiry", "min"))
        .sort_values(["최근유통기한", "product_name"])
    )

    for row in product_summary.itertuples(index=False):
        name = str(row.product_name)
        total = int(row.총수량)
        count = int(row.건수)
        nearest_date = row.최근유통기한.strftime("%Y.%m.%d")
        with st.expander(f"{name}  ·  총 {total:,}개  ·  {count}건  ·  최근 {nearest_date}"):
            detail = df[df["product_name"] == name].copy()
            detail = detail.sort_values(["_expiry", "location", "lot"])
            detail["유통기한"] = detail["_expiry"].dt.strftime("%Y.%m.%d")
            detail["남은 일수"] = detail["남은일수"].apply(
                lambda days: f"만료 {abs(int(days))}일" if days < 0 else f"{int(days)}일"
            )
            detail = detail.rename(columns={"location": "로케이션", "qty": "수량"})
            st.dataframe(
                detail[["로케이션", "유통기한", "수량", "남은 일수"]],
                use_container_width=True,
                hide_index=True,
            )


def page_mobile_stock_finder():
    _mobile_css()
    username = "기본"
    st.session_state["mobile_stock_user"] = username

    mode = st.radio(
        "모바일 메뉴",
        ["재고 검색", "임박재고"],
        horizontal=True,
        label_visibility="collapsed",
        key="mobile_stock_mode",
    )
    if mode == "임박재고":
        _render_expiry_inventory()
    else:
        _render_mobile_search(username)
