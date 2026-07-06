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


def _build_query(companies, product_term, erp_term, limit):
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
    sql = f"""
        SELECT company AS 사업장,
               location AS 로케이션,
               product_name AS 표준제품명,
               COALESCE(warehouse_name, '-') AS ERP명,
               COALESCE(lot, '-') AS 제조번호,
               COALESCE(exp_date, '-') AS 유통기한,
               qty AS 수량
        FROM inventory
        WHERE {' AND '.join(where)}
        ORDER BY company, location, product_name, warehouse_name, lot, exp_date, id
        LIMIT ?
    """
    params.append(int(limit))
    return q(sql, tuple(params))


def _render_inventory_table(df):
    if df.empty:
        st.info("조회되는 재고가 없습니다.")
        return
    work = df.copy()
    work["유통기한"] = work["유통기한"].apply(display_date_only)
    work["수량"] = pd.to_numeric(work["수량"], errors="coerce").fillna(0).astype(int)

    html = [
        "<style>",
        ".all-inv-wrap{width:100%;overflow:visible;margin-top:12px;}",
        ".all-inv-table{width:100%;border-collapse:collapse;background:white;border:1px solid #e5e7eb;font-size:13px;}",
        ".all-inv-table th{position:sticky;top:0;background:#f1f5f9;color:#111827;font-weight:800;border:1px solid #e5e7eb;padding:7px;text-align:center;z-index:1;}",
        ".all-inv-table td{border:1px solid #e5e7eb;padding:7px;color:#111827;vertical-align:middle;}",
        ".all-inv-table td.num{text-align:right;font-weight:700;color:#2563eb;}",
        "</style>",
        "<div class='all-inv-wrap'><table class='all-inv-table'>",
        "<thead><tr><th>사업장</th><th>로케이션</th><th>표준제품명</th><th>ERP명</th><th>제조번호</th><th>유통기한</th><th>수량</th></tr></thead><tbody>",
    ]
    for r in work.itertuples(index=False):
        html.append("<tr>")
        html.append(f"<td>{escape(str(getattr(r, '사업장', '') or '-'))}</td>")
        html.append(f"<td>{escape(str(getattr(r, '로케이션', '') or '-'))}</td>")
        html.append(f"<td>{escape(str(getattr(r, '표준제품명', '') or '-'))}</td>")
        html.append(f"<td>{escape(str(getattr(r, 'ERP명', '') or '-'))}</td>")
        html.append(f"<td>{escape(str(getattr(r, '제조번호', '') or '-'))}</td>")
        html.append(f"<td>{escape(str(getattr(r, '유통기한', '') or '-'))}</td>")
        html.append(f"<td class='num'>{int(getattr(r, '수량', 0) or 0):,}</td>")
        html.append("</tr>")
    html.append("</tbody></table></div>")
    st.markdown("".join(html), unsafe_allow_html=True)


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

    limit = int(st.session_state.get("all_inv_limit", PAGE_SIZE) or PAGE_SIZE)
    df = _build_query(companies, product_term, erp_term, limit + 1)
    has_more = len(df) > limit
    shown = df.iloc[:limit].copy() if has_more else df.copy()

    st.caption(f"표시 중: {len(shown):,}건" + (" · 아래로 내려가 더 보기를 누르면 계속 불러옵니다." if has_more else ""))
    _render_inventory_table(shown)

    if has_more:
        _left, mid, _right = st.columns([3, 2, 3])
        with mid:
            if st.button(f"더 보기 (+{PAGE_SIZE}건)", use_container_width=True):
                st.session_state["all_inv_limit"] = limit + PAGE_SIZE
                st.rerun()
