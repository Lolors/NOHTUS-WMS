from __future__ import annotations

from html import escape

import pandas as pd
import streamlit as st

from nohtus.config import COMPANIES
from nohtus.db import q
from nohtus.dates import display_date_only


_NON_COUNTED_LOCATION = "N-홍보물랙"


def _normalized_location(value):
    return str(value or "").strip().upper().replace(" ", "")


def _is_non_counted_location(value):
    return _normalized_location(value) == _NON_COUNTED_LOCATION


def _build_where(companies, product_term, erp_term, exclude_p=False, exclude_materials=True):
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
    if exclude_p:
        where.append("REPLACE(UPPER(TRIM(COALESCE(location,''))), ' ', '') NOT LIKE 'P%'")
    if exclude_materials:
        normalized = "REPLACE(UPPER(TRIM(COALESCE(location,''))), ' ', '')"
        where.append(f"{normalized} NOT IN ('G1','G2','N-홍보물랙')")
        where.append(f"{normalized} NOT LIKE 'G1-%'")
        where.append(f"{normalized} NOT LIKE 'G2-%'")
    return " AND ".join(where), params


def _build_query(companies, product_term, erp_term, exclude_p=False, exclude_materials=True):
    where_sql, params = _build_where(companies, product_term, erp_term, exclude_p, exclude_materials)
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
        ORDER BY
            CASE WHEN REPLACE(UPPER(TRIM(COALESCE(location,''))), ' ', '')='N-홍보물랙' THEN 1 ELSE 0 END,
            company, location, product_name, warehouse_name, lot, exp_date, id
    """
    return q(sql, tuple(params))


def _summary_query(companies, product_term, erp_term, exclude_p=False, exclude_materials=True):
    where_sql, params = _build_where(companies, product_term, erp_term, exclude_p, exclude_materials)
    counted_condition = "REPLACE(UPPER(TRIM(COALESCE(location,''))), ' ', '')<>'N-홍보물랙'"
    total_df = q(
        f"""
        SELECT COUNT(*) AS row_count,
               COALESCE(SUM(CASE WHEN {counted_condition} THEN qty ELSE 0 END), 0) AS total_qty
        FROM inventory
        WHERE {where_sql}
        """,
        tuple(params),
    )
    by_company = q(
        f"""
        SELECT company AS 사업장,
               COALESCE(SUM(CASE WHEN {counted_condition} THEN qty ELSE 0 END), 0) AS 수량
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
    numeric_qty = pd.to_numeric(work["수량"], errors="coerce").fillna(0).astype(int)
    work["수량"] = [
        "측정 대상 아님" if _is_non_counted_location(location) else f"{qty:,}"
        for location, qty in zip(work["로케이션"], numeric_qty)
    ]
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
    st.caption("전체 재고를 사업장, 표준제품명, ERP명 기준으로 조회합니다. N - 홍보물랙은 수량 합계에서 제외됩니다.")

    f1, f2, f3, f4 = st.columns([3, 2, 2, 3], gap="small")
    with f1:
        companies = st.multiselect("사업장", COMPANIES, default=COMPANIES, key="all_inv_companies")
    with f2:
        product_term = st.text_input("표준제품명 검색", placeholder="표준제품명 일부 입력", key="all_inv_product_term")
    with f3:
        erp_term = st.text_input("ERP명 검색", placeholder="ERP명 일부 입력", key="all_inv_erp_term")
    with f4:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        c1, c2 = st.columns([1, 1], gap="small")
        with c1:
            exclude_p = st.checkbox(
                "수출대기(P) 제외",
                value=False,
                key="all_inv_exclude_p",
                help="P 로케이션 재고를 조회 결과와 합계에서 제외합니다.",
            )
        with c2:
            exclude_materials = st.checkbox(
                "부자재 및 홍보물 제외",
                value=True,
                key="all_inv_exclude_materials",
                help="G1, G2 및 그 하위 로케이션과 N - 홍보물랙 재고를 조회 결과와 합계에서 제외합니다.",
            )

    row_count, total_qty, by_company = _summary_query(
        companies, product_term, erp_term, exclude_p, exclude_materials
    )
    _render_summary(row_count, total_qty, by_company)

    df = _build_query(companies, product_term, erp_term, exclude_p, exclude_materials)
    display_df = _prepare_display_df(df)

    st.caption(f"표시 중: {len(display_df):,} / {row_count:,}건")
    if display_df.empty:
        st.info("조회되는 재고가 없습니다.")
    else:
        st.dataframe(
            display_df,
            hide_index=True,
            use_container_width=True,
            height=min(720, 38 + max(1, len(display_df)) * 35),
        )
