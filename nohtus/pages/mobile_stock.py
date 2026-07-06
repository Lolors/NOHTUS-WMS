from datetime import datetime

import pandas as pd
import streamlit as st

from nohtus.config_runtime import COMPANIES
from nohtus.db import connect, q
from nohtus.dates import display_date_only, expiry_status
from nohtus.services.products import product_options


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
        return q("""
            SELECT product_name, COALESCE(sort_order, 0) AS sort_order
            FROM mobile_favorites
            WHERE username=?
            ORDER BY sort_order, product_name
        """, (username,))
    except Exception:
        return pd.DataFrame(columns=["product_name", "sort_order"])


def mobile_is_favorite(username, product_name):
    username = (username or "").strip() or "기본"
    product_name = (product_name or "").strip()
    if not product_name:
        return False
    try:
        df = q("SELECT 1 FROM mobile_favorites WHERE username=? AND product_name=? LIMIT 1", (username, product_name))
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
        row = cur.execute("SELECT COALESCE(MAX(sort_order), -1) FROM mobile_favorites WHERE username=?", (username,)).fetchone()
        next_order = int((row[0] if row else -1) or -1) + 1
        cur.execute("""
            INSERT OR IGNORE INTO mobile_favorites(username, product_name, sort_order, created_at)
            VALUES(?,?,?,?)
        """, (username, product_name, next_order, now))
        con.commit()


def mobile_remove_favorite(username, product_name):
    username = (username or "").strip() or "기본"
    product_name = (product_name or "").strip()
    with connect() as con:
        con.execute("DELETE FROM mobile_favorites WHERE username=? AND product_name=?", (username, product_name))
        con.commit()
    mobile_reindex_favorites(username)


def mobile_reindex_favorites(username):
    username = (username or "").strip() or "기본"
    df = mobile_favorites_for_user(username)
    with connect() as con:
        cur = con.cursor()
        for i, r in enumerate(df.itertuples(index=False)):
            cur.execute("UPDATE mobile_favorites SET sort_order=? WHERE username=? AND product_name=?", (i, username, getattr(r, "product_name")))
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
            cur.execute("UPDATE mobile_favorites SET sort_order=? WHERE username=? AND product_name=?", (i, username, name))
        con.commit()


def mobile_product_candidates(term="", limit=30):
    """표준제품명/ERP명/비자료명/별칭으로 검색하되 표시값은 표준제품명만 반환."""
    df = product_options(term)
    if df.empty:
        return []
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
    df = q(f"""
        SELECT company, location, lot, exp_date, qty
        FROM inventory
        WHERE {where}
        ORDER BY company, exp_date, location, lot
    """, tuple(params))
    if df.empty:
        return df
    df["상태"] = df["exp_date"].apply(expiry_status)
    if expiry_filter and expiry_filter != "전체":
        df = df[df["상태"] == expiry_filter]
    return df


def page_mobile_stock_finder():
    st.markdown("""
    <style>
    @media (max-width: 768px) {
        div[data-testid="stAppViewContainer"] .main .block-container {
            padding-top: 0.65rem !important;
        }
        header[data-testid="stHeader"] {
            height: 0 !important;
        }
    }
    </style>
    """, unsafe_allow_html=True)

    st.title("재고 찾기")
    st.caption("모바일 조회 전용 화면입니다. 표준제품명, ERP명, 비자료명, 별칭으로 제품을 찾아 현재 재고 위치를 확인합니다.")

    username = "기본"
    st.session_state["mobile_stock_user"] = username

    fav_df = mobile_favorites_for_user(username)
    with st.expander("즐겨찾기", expanded=not fav_df.empty):
        if fav_df.empty:
            st.caption("아직 즐겨찾기가 없습니다. 제품 검색 후 즐겨찾기에 추가하세요.")
        else:
            for i, r in enumerate(fav_df.itertuples(index=False)):
                fav_name = str(getattr(r, "product_name") or "")
                c1, c2, c3, c4 = st.columns([5, 1, 1, 1])
                with c1:
                    if st.button(fav_name, key=f"mobile_fav_pick_{username}_{fav_name}", use_container_width=True):
                        st.session_state["mobile_selected_product"] = fav_name
                        st.session_state["mobile_product_term"] = fav_name
                        st.rerun()
                with c2:
                    if st.button("▲", key=f"mobile_fav_up_{username}_{fav_name}", disabled=(i == 0), use_container_width=True):
                        mobile_move_favorite(username, fav_name, "up")
                        st.rerun()
                with c3:
                    if st.button("▼", key=f"mobile_fav_down_{username}_{fav_name}", disabled=(i == len(fav_df)-1), use_container_width=True):
                        mobile_move_favorite(username, fav_name, "down")
                        st.rerun()
                with c4:
                    if st.button("삭제", key=f"mobile_fav_del_{username}_{fav_name}", use_container_width=True):
                        mobile_remove_favorite(username, fav_name)
                        st.rerun()

    term = st.text_input("제품 검색", placeholder="표준제품명 또는 ERP명 입력", key="mobile_product_term")
    filter_c1, filter_c2 = st.columns(2)
    with filter_c1:
        company_filter = st.selectbox("사업장", ["전체"] + COMPANIES, key="mobile_company_filter")
    with filter_c2:
        expiry_filter = st.selectbox("유통기한", ["전체", "정상", "임박(1년)", "만료"], key="mobile_expiry_filter")

    candidates = mobile_product_candidates(term, limit=30) if term.strip() else []
    selected_product = st.session_state.get("mobile_selected_product", "")
    if candidates:
        if selected_product not in candidates:
            selected_product = candidates[0]
        selected_product = st.selectbox(
            "제품 선택",
            candidates,
            index=candidates.index(selected_product) if selected_product in candidates else 0,
            key="mobile_product_select",
        )
        st.session_state["mobile_selected_product"] = selected_product
    elif term.strip():
        st.info("검색 결과가 없습니다. ERP명이나 표준제품명을 다시 확인해주세요.")
        return
    elif not selected_product:
        st.info("제품명을 검색하거나 즐겨찾기를 선택하세요.")
        return

    if not selected_product:
        return

    rows = mobile_stock_rows(selected_product, company_filter=company_filter, expiry_filter=expiry_filter)
    total_qty = int(rows["qty"].sum()) if not rows.empty else 0

    st.markdown("---")
    fav = mobile_is_favorite(username, selected_product)
    title_col, fav_col = st.columns([4, 2])
    with title_col:
        st.subheader(selected_product)
        st.markdown(f"### 총재고 {total_qty:,}EA")
    with fav_col:
        if fav:
            if st.button("★ 즐겨찾기 해제", use_container_width=True, key=f"mobile_unfav_{username}_{selected_product}"):
                mobile_remove_favorite(username, selected_product)
                st.rerun()
        else:
            if st.button("☆ 즐겨찾기 추가", use_container_width=True, key=f"mobile_addfav_{username}_{selected_product}"):
                mobile_add_favorite(username, selected_product)
                st.rerun()

    if rows.empty or total_qty <= 0:
        st.warning("조건에 맞는 현재 재고가 없습니다.")
        return

    if expiry_filter == "임박(1년)":
        near_df = rows.copy()
        near_df["표준제품명"] = selected_product
        near_df["유통기한"] = near_df["exp_date"].apply(display_date_only)
        near_df = near_df.rename(columns={"location": "로케이션", "qty": "수량"})
        st.dataframe(
            near_df[["로케이션", "표준제품명", "유통기한", "수량"]],
            use_container_width=True,
            hide_index=True,
        )
        return

    company_totals = rows.groupby("company")["qty"].sum().sort_index()
    summary = " · ".join([f"{company} {int(qty):,}EA" for company, qty in company_totals.items() if int(qty or 0) > 0])
    if summary:
        st.caption(summary)

    for company, cdf in rows.groupby("company", sort=True):
        ctotal = int(cdf["qty"].sum())
        if ctotal <= 0:
            continue
        with st.expander(f"{company} ({ctotal:,}EA)", expanded=True):
            cdf = cdf.copy()
            cdf["_exp_sort"] = pd.to_datetime(cdf["exp_date"], errors="coerce")
            cdf["_exp_sort"] = cdf["_exp_sort"].fillna(pd.Timestamp.max)
            cdf = cdf.sort_values(["_exp_sort", "location", "qty"])
            for r in cdf.itertuples(index=False):
                loc = str(getattr(r, "location") or "-")
                exp = display_date_only(getattr(r, "exp_date") or "-")
                qty = int(getattr(r, "qty") or 0)
                status = expiry_status(getattr(r, "exp_date") or "-")
                badge = "🟢" if status == "정상" else ("🟡" if status.startswith("임박") else "🔴")
                st.markdown(f"{badge} **{loc}** &nbsp;&nbsp; {exp} &nbsp;&nbsp; **{qty:,}EA**", unsafe_allow_html=True)
