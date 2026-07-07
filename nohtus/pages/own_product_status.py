from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from nohtus.db import q

COMPANIES = ["노투스팜", "NOH", "노투스"]


def _today_text():
    return date.today().strftime("%Y-%m-%d")


def _product_master_names():
    df = q(
        """
        SELECT DISTINCT TRIM(standard_name) AS product_name
        FROM products
        WHERE TRIM(COALESCE(standard_name,'')) <> ''
        ORDER BY product_name
        """
    )
    if df.empty:
        return []
    return [str(x or "").strip() for x in df["product_name"].tolist() if str(x or "").strip()]


def _company_current_stock(company: str, product_names: list[str]) -> pd.DataFrame:
    if not product_names:
        return pd.DataFrame(columns=["product_name", "qty"])
    placeholders = ",".join(["?"] * len(product_names))
    params = tuple([company] + product_names)
    return q(
        f"""
        SELECT product_name, COALESCE(SUM(qty),0) AS qty
        FROM inventory
        WHERE company=?
          AND product_name IN ({placeholders})
        GROUP BY product_name
        """,
        params,
    )


def _company_today_delta(company: str, product_names: list[str]) -> pd.DataFrame:
    if not product_names:
        return pd.DataFrame(columns=["product_name", "delta_qty"])
    today = _today_text()
    placeholders = ",".join(["?"] * len(product_names))
    params = tuple([today, company, company] + product_names)
    return q(
        f"""
        SELECT product_name,
               COALESCE(SUM(
                   CASE
                     WHEN tx_type IN ('입고','출고지시취소','재고조사불러오기','기준재고','전산재고')
                          AND COALESCE(to_company,'')=? THEN CAST(qty AS INTEGER)
                     WHEN tx_type IN ('출고지시','출고','출고지시수정','출고확정')
                          AND COALESCE(from_company,'')=? THEN -CAST(qty AS INTEGER)
                     WHEN tx_type IN ('사업장이동','사업장+위치이동','비자료전환','이동')
                          AND COALESCE(to_company,'')=? AND COALESCE(from_company,'')<>? THEN CAST(qty AS INTEGER)
                     WHEN tx_type IN ('사업장이동','사업장+위치이동','비자료전환','이동')
                          AND COALESCE(from_company,'')=? AND COALESCE(to_company,'')<>? THEN -CAST(qty AS INTEGER)
                     WHEN tx_type IN ('재고조정','재고실사','재고정보수정')
                          AND COALESCE(to_company, from_company, '')=? THEN CAST(qty AS INTEGER)
                     ELSE 0
                   END
               ),0) AS delta_qty
        FROM transactions
        WHERE substr(created_at,1,10)=?
          AND product_name IN ({placeholders})
          AND tx_type IN (
              '입고','출고지시취소','재고조사불러오기','기준재고','전산재고',
              '출고지시','출고','출고지시수정','출고확정',
              '사업장이동','사업장+위치이동','비자료전환','이동',
              '재고조정','재고실사','재고정보수정'
          )
        GROUP BY product_name
        """,
        tuple([company, company, company, company, company, company, company, today] + product_names),
    )


def _format_qty(value) -> str:
    try:
        value = int(value or 0)
    except Exception:
        value = 0
    return "-" if value == 0 else f"{value:,}"


def _format_delta(value) -> str:
    try:
        value = int(value or 0)
    except Exception:
        value = 0
    if value > 0:
        return f"+{value:,}"
    if value < 0:
        return f"{value:,}"
    return "-"


def _company_table(company: str, product_names: list[str]) -> pd.DataFrame:
    base = pd.DataFrame({"제품명": product_names})
    current = _company_current_stock(company, product_names)
    delta = _company_today_delta(company, product_names)

    if not current.empty:
        current = current.rename(columns={"product_name": "제품명", "qty": "현재수량"})
    else:
        current = pd.DataFrame(columns=["제품명", "현재수량"])
    if not delta.empty:
        delta = delta.rename(columns={"product_name": "제품명", "delta_qty": "증감"})
    else:
        delta = pd.DataFrame(columns=["제품명", "증감"])

    out = base.merge(current, on="제품명", how="left").merge(delta, on="제품명", how="left")
    out["현재수량"] = out["현재수량"].fillna(0).astype(int)
    out["증감"] = out["증감"].fillna(0).astype(int)
    out["전일수량"] = out["현재수량"] - out["증감"]
    out = out[["제품명", "전일수량", "증감", "현재수량"]]
    out = out[(out["전일수량"] != 0) | (out["증감"] != 0) | (out["현재수량"] != 0)]
    out["전일수량"] = out["전일수량"].map(_format_qty)
    out["증감"] = out["증감"].map(_format_delta)
    out["현재수량"] = out["현재수량"].map(_format_qty)
    return out.reset_index(drop=True)


def _render_table(company: str, df: pd.DataFrame):
    st.markdown(f"<h2 class='own-product-company'>{company}</h2>", unsafe_allow_html=True)
    if df.empty:
        st.info("표시할 자사제품 재고가 없습니다.")
        return
    st.dataframe(df, hide_index=True, use_container_width=True)


def page_own_product_status():
    st.title("자사제품 조회")
    st.caption(f"기준일자: {_today_text()} · 전일수량은 현재수량에서 금일 입고/출고/이동 변동값을 되돌린 수량입니다.")
    st.markdown(
        """
        <style>
        .own-product-company{
            text-align:center;
            font-size:2rem;
            font-weight:500;
            margin:1.8rem 0 .3rem 0;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    product_names = _product_master_names()
    if not product_names:
        st.warning("제품 매칭 관리에 등록된 표준제품명이 없습니다.")
        return
    for company in COMPANIES:
        _render_table(company, _company_table(company, product_names))
