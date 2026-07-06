from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from nohtus.auth import current_username
from nohtus.db import connect, q
from nohtus.dates import display_date_only


def add_recent_product_view(product_name: str, username: str | None = None):
    username = (username or current_username() or "기본").strip() or "기본"
    product_name = str(product_name or "").strip()
    if not product_name:
        return
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with connect() as con:
        con.execute(
            """
            INSERT INTO recent_product_views(username, product_name, viewed_at)
            VALUES(?,?,?)
            ON CONFLICT(username, product_name) DO UPDATE SET viewed_at=excluded.viewed_at
            """,
            (username, product_name, now),
        )
        con.commit()


def is_favorite_product(product_name: str, username: str | None = None) -> bool:
    username = (username or current_username() or "기본").strip() or "기본"
    product_name = str(product_name or "").strip()
    if not product_name:
        return False
    df = q("SELECT 1 FROM favorite_products WHERE username=? AND product_name=? LIMIT 1", (username, product_name))
    return not df.empty


def toggle_favorite_product(product_name: str, username: str | None = None):
    username = (username or current_username() or "기본").strip() or "기본"
    product_name = str(product_name or "").strip()
    if not product_name:
        return
    with connect() as con:
        if is_favorite_product(product_name, username):
            con.execute("DELETE FROM favorite_products WHERE username=? AND product_name=?", (username, product_name))
        else:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            con.execute(
                "INSERT OR IGNORE INTO favorite_products(username, product_name, created_at) VALUES(?,?,?)",
                (username, product_name, now),
            )
        con.commit()


def _stock_summary(product_name: str) -> pd.DataFrame:
    return q(
        """
        SELECT company AS 사업장,
               location AS 로케이션,
               product_name AS 표준제품명,
               warehouse_name AS ERP명,
               lot AS 제조번호,
               exp_date AS 유통기한,
               qty AS 수량
        FROM inventory
        WHERE product_name=? AND qty>0
        ORDER BY company, location, exp_date, lot
        """,
        (product_name,),
    )


def render_product_stock_summary(product_name: str):
    product_name = str(product_name or "").strip()
    if not product_name:
        return
    add_recent_product_view(product_name)
    df = _stock_summary(product_name)
    st.subheader(product_name)
    if df.empty:
        st.info("현재 재고가 없습니다.")
        return
    df = df.copy()
    df["유통기한"] = df["유통기한"].apply(display_date_only)
    total_qty = int(df["수량"].sum())
    st.markdown(f"### 총재고 {total_qty:,}EA")
    company_totals = df.groupby("사업장")["수량"].sum().reset_index()
    st.dataframe(company_totals, use_container_width=True, hide_index=True)
    st.dataframe(df, use_container_width=True, hide_index=True)


def _product_button_list(df: pd.DataFrame, key_prefix: str):
    if df.empty:
        st.info("표시할 제품이 없습니다.")
        return
    for r in df.itertuples(index=False):
        product_name = str(getattr(r, "product_name") or "")
        if st.button(product_name, key=f"{key_prefix}_{product_name}", use_container_width=True):
            st.session_state["shortcut_selected_product"] = product_name
            st.rerun()


def page_favorite_products():
    st.title("즐겨찾는 제품")
    username = current_username() or "기본"
    fav_df = q(
        """
        SELECT product_name
        FROM favorite_products
        WHERE username=?
        ORDER BY created_at DESC, product_name
        """,
        (username,),
    )
    left, right = st.columns([3, 7], gap="large")
    with left:
        _product_button_list(fav_df, "favorite_product")
    with right:
        render_product_stock_summary(st.session_state.get("shortcut_selected_product", ""))


def page_recent_products():
    st.title("최근 조회")
    username = current_username() or "기본"
    recent_df = q(
        """
        SELECT product_name
        FROM recent_product_views
        WHERE username=?
        ORDER BY viewed_at DESC
        LIMIT 50
        """,
        (username,),
    )
    left, right = st.columns([3, 7], gap="large")
    with left:
        _product_button_list(recent_df, "recent_product")
    with right:
        render_product_stock_summary(st.session_state.get("shortcut_selected_product", ""))
