from __future__ import annotations

from html import escape

import pandas as pd
import streamlit as st

from nohtus.config import COMPANIES
from nohtus.db import q
from nohtus.dates import display_date_only


PAGE_SIZE = 100


def _filter_signature(companies, product_term, erp_term):
    return "|".join([
        ",".join(companies or []),
        str(product_term or "").strip(),
        str(erp_term or "").strip(),
    ])


def _build_where(companies, product_term, erp_term):
    where = ["qty>0"]
    params = []
    if companies:
        placeholders = ",".join(["?"] * len(companies))
        where.append(f"company IN ({placeholders})")
        params.extend(companies)
    product_term = str(product_term or "").strip()
    if product_term:
        where.append("product_name LIKE ?")
        params.append(f"%{product_term}%")
    erp_term = str(erp_term or "").strip()
    if erp_term:
        where.append("COALESCE(warehouse_name,'') LIKE ?")
        params.append(f"%{erp_term}%")
    return " AND ".join(where), params


def _build_query(companies, product_term, erp_term, limit):
    where_sql, params = _build_where(companies, product_term, erp_term)
    sql = f"""
        SELECT company AS 사업장,
               location AS 로케이션,
               product_name AS 표준제품명,
               COALESCE(warehouse_name, '-') AS ERP명,
               COALESCE(lot, '-') AS 제조번호,
               COALESCE(exp_date, '-') AS 유통기한,
               qty AS 수량
        FROM inventory
        WHERE {where_sql}
        ORDER BY company, location, product_name, warehouse_name, lot, exp_date, id
        LIMIT ?
    """
    params.append(int(limit))
    return q(sql, tuple(params))


def _summary_query(companies, product_term, erp_term):
    where_sql, params = _build_where(companies, product_term, erp_term)
    total_df = q(f"SELECT COUNT(*) AS row_count, COALESCE(SUM(qty), 0) AS total_qty FROM inventory WHERE {where_sql}", tuple(params))
    by_company = q(
        f"""
        SELECT company AS 사업장, COALESCE(SUM(qty), 0) AS 수량
        FROM inventory
        WHERE {where_sql}
        GROUP BY company
        ORDER BY company
        """,
        tuple(params),
    )
    row_count = int(total_df.iloc[0]["row_count"] or 0) if not total_df.empty else 0
    total_qty = int(total_df.iloc[0]["total_qty"] or 0) if not total_df.empty else 0
    return row_count, total_qty, by_company


def _prepare_display_df(df):
    if df.empty:
        return df
    work = df.copy()
    work["유통기한"] = work["유통기한"].apply(display_date_only)
    work["수량"] = pd.to_numeric(work["수량"], errors="coerce").fillna(0).astype(int)
    return work[["사업장", "로케이션", "표준제품명", "ERP명", "제조번호", "유통기한", "수량"]]


def _render_summary(row_count, total_qty, by_company):
    parts = []
    if by_company is not None and not by_company.empty:
        for r in by_company.itertuples(index=False):
            parts.append(
                f"<span class='all-inv-chip'><span>{escape(str(getattr(r, '사업장') or '-'))}</span>"
                f"<em>{int(getattr(r, '수량') or 0):,} EA</em></span>"
            )
    company_html = "".join(parts) or "<span class='all-inv-muted'>사업장별 합계 없음</span>"
    st.markdown(
        f"""
        <style>
        .all-inv-summary{{
            display:flex;align-items:center;gap:12px;flex-wrap:wrap;
            border:1px solid #e5e7eb;background:#ffffff;border-radius:14px;
            padding:9px 12px;margin:2px 0 12px;color:#334155;
            box-shadow:0 2px 8px rgba(15,23,42,.025);
        }}
        .all-inv-mini{{display:inline-flex;align-items:baseline;gap:6px;padding-right:10px;border-right:1px solid #e5e7eb;}}
        .all-inv-mini span{{font-size:12px;color:#64748b;font-weight:400;}}
        .all-inv-mini strong{{font-size:14px;color:#111827;font-weight:600;}}
        .all-inv-company{{display:flex;align-items:center;gap:7px;flex-wrap:wrap;}}
        .all-inv-company-label{{font-size:12px;color:#64748b;font-weight:400;margin-right:2px;}}
        .all-inv-chip{{display:inline-flex;align-items:center;gap:5px;border:1px solid #e5e7eb;background:#f8fafc;border-radius:999px;padding:4px 8px;font-size:12px;color:#475569;font-weight:400;}}
        .all-inv-chip em{{font-style:normal;color:#2563eb;font-weight:500;}}
        .all-inv-muted{{font-size:12px;color:#94a3b8;font-weight:400;}}
        </style>
        <div class='all-inv-summary'>
            <div class='all-inv-mini'><span>조회 행수</span><strong>{row_count:,}건</strong></div>
            <div class='all-inv-mini'><span>총 수량</span><strong>{total_qty:,} EA</strong></div>
            <div class='all-inv-company'><span class='all-inv-company-label'>사업장별</span>{company_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def page_all_inventory():
    st.title("전체 조회")
    st.caption("전체 재고를 사업장, 표준제품명, ERP명 기준으로 조회합니다.")

    f1, f2, f3 = st.columns([2.2, 3.4, 3.4], gap="small")
    with f1:
        companies = st.multiselect("사업장", COMPANIES, default=COMPANIES, key="all_inv_companies")
    with f2:
        product_term = st.text_input("표준제품명 검색", placeholder="표준제품명 일부 입력", key="all_inv_product_term")
    with f3:
        erp_term = st.text_input("ERP명 검색", placeholder="ERP명 일부 입력", key="all_inv_erp_term")

    sig = _filter_signature(companies, product_term, erp_term)
    if st.session_state.get("_all_inv_filter_sig") != sig:
        st.session_state["_all_inv_filter_sig"] = sig
        st.session_state["all_inv_limit"] = PAGE_SIZE

    row_count, total_qty, by_company = _summary_query(companies, product_term, erp_term)
    _render_summary(row_count, total_qty, by_company)

    limit = int(st.session_state.get("all_inv_limit", PAGE_SIZE) or PAGE_SIZE)
    df = _build_query(companies, product_term, erp_term, limit + 1)
    has_more = len(df) > limit
    shown = df.iloc[:limit].copy() if has_more else df.copy()
    display_df = _prepare_display_df(shown)

    st.caption(f"표시 중: {len(display_df):,} / {row_count:,}건" + (" · 아래로 내려가 더 보기를 누르면 계속 불러옵니다." if has_more else ""))
    if display_df.empty:
        st.info("조회되는 재고가 없습니다.")
    else:
        st.dataframe(
            display_df,
            hide_index=True,
            use_container_width=True,
            height=min(720, 38 + max(1, len(display_df)) * 35),
            column_config={
                "수량": st.column_config.NumberColumn("수량", format="%d"),
            },
        )

    if has_more:
        _left, mid, _right = st.columns([3, 2, 3])
        with mid:
            if st.button(f"더 보기 (+{PAGE_SIZE}건)", use_container_width=True):
                st.session_state["all_inv_limit"] = limit + PAGE_SIZE
                st.rerun()
