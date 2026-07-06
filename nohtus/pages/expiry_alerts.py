from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from nohtus.db import q
from nohtus.dates import display_date_only

COMPANY_OPTIONS = ["노투스팜", "NOH", "노투스", "비자료"]


def _expiry_alert_rows(companies: list[str]) -> pd.DataFrame:
    today = date.today().strftime("%Y-%m-%d")
    until = (date.today() + timedelta(days=365)).strftime("%Y-%m-%d")
    params: list[str] = [today, until]
    company_sql = ""
    if companies:
        placeholders = ",".join(["?"] * len(companies))
        company_sql = f" AND company IN ({placeholders})"
        params.extend(companies)

    df = q(
        f"""
        SELECT company AS 사업장,
               location AS 로케이션,
               product_name AS 표준제품명,
               exp_date AS 유통기한,
               qty AS 수량
        FROM inventory
        WHERE qty > 0
          AND exp_date IS NOT NULL
          AND exp_date <> '-'
          AND date(exp_date) BETWEEN date(?) AND date(?)
          {company_sql}
        ORDER BY date(exp_date), company, location, product_name
        """,
        tuple(params),
    )
    if df.empty:
        return df
    df = df.copy()
    df["유통기한"] = df["유통기한"].apply(display_date_only)
    df["수량"] = pd.to_numeric(df["수량"], errors="coerce").fillna(0).astype(int)
    return df


def page_expiry_alerts():
    st.title("유통기한 임박")
    selected_companies = st.multiselect(
        "사업장",
        COMPANY_OPTIONS,
        default=COMPANY_OPTIONS,
        key="expiry_alert_company_filter",
    )
    rows = _expiry_alert_rows(selected_companies)
    if rows.empty:
        st.info("선택한 조건에 해당하는 유통기한 1년 이하 재고가 없습니다.")
        return
    st.dataframe(
        rows[["사업장", "로케이션", "표준제품명", "유통기한", "수량"]],
        use_container_width=True,
        hide_index=True,
    )
