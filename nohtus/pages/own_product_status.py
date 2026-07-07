from __future__ import annotations

from datetime import date
from html import escape

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from nohtus.db import q

COMPANIES = ["노투스팜", "NOH", "노투스"]
OWN_PRODUCTS = [
    "리쥬네르 골드라벨",
    "리쥬네르 블랙라벨",
    "델가다 (5EA)",
    "디센바 (5EA)",
    "디센바B (5EA)",
    "마이클리어 (10 EA)",
    "하이바이 (5EA)",
]
INBOUND_TYPES = {"입고", "출고지시취소"}
OUTBOUND_TYPES = {"출고지시", "출고", "출고지시수정", "출고확정"}
MOVE_TYPES = {"사업장이동", "사업장+위치이동", "비자료전환", "이동"}


def _today_text():
    return date.today().strftime("%Y-%m-%d")


def _own_product_names():
    return list(OWN_PRODUCTS)


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


def _today_transactions(product_names: list[str]) -> pd.DataFrame:
    if not product_names:
        return pd.DataFrame(columns=["tx_type", "product_name", "from_company", "to_company", "qty"])
    placeholders = ",".join(["?"] * len(product_names))
    tx_types = sorted(INBOUND_TYPES | OUTBOUND_TYPES | MOVE_TYPES)
    tx_type_placeholders = ",".join(["?"] * len(tx_types))
    return q(
        f"""
        SELECT tx_type, product_name, from_company, to_company, qty
        FROM transactions
        WHERE substr(created_at,1,10)=?
          AND product_name IN ({placeholders})
          AND tx_type IN ({tx_type_placeholders})
        """,
        tuple([_today_text()] + product_names + tx_types),
    )


def _today_delta_map(product_names: list[str]) -> dict[tuple[str, str], int]:
    deltas = {(company, product): 0 for company in COMPANIES for product in product_names}
    tx_df = _today_transactions(product_names)
    if tx_df.empty:
        return deltas

    for _, row in tx_df.iterrows():
        product = str(row.get("product_name") or "").strip()
        tx_type = str(row.get("tx_type") or "").strip()
        from_company = str(row.get("from_company") or "").strip()
        to_company = str(row.get("to_company") or "").strip()
        try:
            qty = int(row.get("qty") or 0)
        except Exception:
            qty = 0
        if not product or qty == 0:
            continue

        if tx_type in INBOUND_TYPES:
            if to_company in COMPANIES:
                deltas[(to_company, product)] = deltas.get((to_company, product), 0) + qty
        elif tx_type in OUTBOUND_TYPES:
            if from_company in COMPANIES:
                deltas[(from_company, product)] = deltas.get((from_company, product), 0) - qty
        elif tx_type in MOVE_TYPES and from_company != to_company:
            if from_company in COMPANIES:
                deltas[(from_company, product)] = deltas.get((from_company, product), 0) - qty
            if to_company in COMPANIES:
                deltas[(to_company, product)] = deltas.get((to_company, product), 0) + qty

    return deltas


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


def _company_table(company: str, product_names: list[str], delta_map: dict[tuple[str, str], int]) -> pd.DataFrame:
    base = pd.DataFrame({"표준제품명": product_names})
    current = _company_current_stock(company, product_names)

    if not current.empty:
        current = current.rename(columns={"product_name": "표준제품명", "qty": "현재수량"})
    else:
        current = pd.DataFrame(columns=["표준제품명", "현재수량"])

    out = base.merge(current, on="표준제품명", how="left")
    out["현재수량"] = out["현재수량"].fillna(0).astype(int)
    out["증감"] = out["표준제품명"].map(lambda product: int(delta_map.get((company, product), 0) or 0))
    out["전일수량"] = out["현재수량"] - out["증감"]
    out = out[["표준제품명", "전일수량", "증감", "현재수량"]]
    out["전일수량"] = out["전일수량"].map(_format_qty)
    out["증감"] = out["증감"].map(_format_delta)
    out["현재수량"] = out["현재수량"].map(_format_qty)
    return out.reset_index(drop=True)


def _table_html(df: pd.DataFrame) -> str:
    headers = "".join(f"<th>{escape(str(col))}</th>" for col in df.columns)
    body_rows = []
    for _, row in df.iterrows():
        cells = []
        for col in df.columns:
            align_class = " own-num" if col != "표준제품명" else " own-name"
            cells.append(f"<td class='{align_class.strip()}'>{escape(str(row.get(col, '')))}</td>")
        body_rows.append("<tr>" + "".join(cells) + "</tr>")
    return (
        "<table class='own-product-html-table'>"
        f"<thead><tr>{headers}</tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody>"
        "</table>"
    )


def _render_table(company: str, df: pd.DataFrame) -> str:
    return (
        "<section class='own-product-card'>"
        f"<h2 class='own-product-company'>{escape(company)}</h2>"
        f"<div class='own-product-table'>{_table_html(df)}</div>"
        "</section>"
    )


def _report_html(sections: list[str]) -> str:
    return f"""
<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8" />
<style>
html, body {{
    margin:0;
    padding:0;
    background:transparent;
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
    color:#0f172a;
}}
.own-product-grid {{
    width:100%;
    display:grid;
    grid-template-columns:30vw 30vw 30vw;
    justify-content:center;
    gap:1.5vw;
    align-items:start;
    box-sizing:border-box;
}}
.own-product-card {{
    width:30vw;
    max-width:30vw;
    min-width:0;
    box-sizing:border-box;
}}
.own-product-company {{
    text-align:center;
    font-size:32px;
    font-weight:600;
    margin:0 0 10px 0;
    line-height:1.2;
}}
.own-product-table {{
    width:30vw;
    max-width:30vw;
    min-width:0;
    overflow-x:auto;
}}
.own-product-html-table {{
    width:max-content;
    min-width:100%;
    border-collapse:collapse;
    table-layout:auto;
    font-size:13px;
    background:white;
}}
.own-product-html-table th,
.own-product-html-table td {{
    border:1px solid #e5e7eb;
    padding:6px 8px;
    line-height:1.25;
    white-space:nowrap;
}}
.own-product-html-table th {{
    background:#f8fafc;
    color:#334155;
    font-weight:800;
    text-align:center;
}}
.own-product-html-table .own-name {{
    text-align:left;
}}
.own-product-html-table .own-num {{
    text-align:right;
    width:1%;
}}
@media (max-width: 768px) {{
    .own-product-grid {{
        display:block;
        width:100%;
    }}
    .own-product-card,
    .own-product-table {{
        width:100%;
        max-width:100%;
        min-width:0;
        margin:0 0 28px 0;
    }}
    .own-product-company {{
        font-size:28px;
        margin:18px 0 8px 0;
    }}
}}
</style>
</head>
<body>
<div class="own-product-grid">{''.join(sections)}</div>
</body>
</html>
"""


def page_own_product_status():
    st.title("자사제품 조회")
    st.caption(f"기준일자: {_today_text()} · 전일수량 = 현재수량 - 금일 입고/출고/사업장 이동 증감")
    product_names = _own_product_names()
    delta_map = _today_delta_map(product_names)
    sections = []
    for company in COMPANIES:
        sections.append(_render_table(company, _company_table(company, product_names, delta_map)))
    components.html(_report_html(sections), height=420, scrolling=False)
