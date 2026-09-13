import pandas as pd
import streamlit as st

try:
    from st_keyup import st_keyup
except ImportError:
    st_keyup = None

from nohtus.db import q
from nohtus.dates import display_date_only, expiry_status


RECENT_SEARCH_LIMIT = 6


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

