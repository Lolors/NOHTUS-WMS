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
OUTBOUND_TYPES = {"출고지시", "출고지시수정", "출고", "출고확정"}
MOVE_TYPES = {"사업장이동", "사업장+위치이동", "비자료전환", "이동"}


def _today_text():
    return date.today().strftime("%Y-%m-%d")


def _company_current_stock(company: str) -> pd.DataFrame:
    placeholders = ",".join(["?"] * len(OWN_PRODUCTS))
    return q(
        f"""
        SELECT product_name, COALESCE(SUM(qty),0) AS qty
        FROM inventory
        WHERE company=? AND product_name IN ({placeholders})
        GROUP BY product_name
        """,
        tuple([company] + OWN_PRODUCTS),
    )


def _today_transactions() -> pd.DataFrame:
    product_placeholders = ",".join(["?"] * len(OWN_PRODUCTS))
    tx_types = sorted(INBOUND_TYPES | OUTBOUND_TYPES | MOVE_TYPES)
    tx_placeholders = ",".join(["?"] * len(tx_types))
    return q(
        f"""
        SELECT tx_type, product_name, from_company, to_company, qty
        FROM transactions
        WHERE substr(created_at,1,10)=?
          AND product_name IN ({product_placeholders})
          AND tx_type IN ({tx_placeholders})
        """,
        tuple([_today_text()] + OWN_PRODUCTS + tx_types),
    )


def _today_delta_map() -> dict[tuple[str, str], int]:
    deltas = {(company, product): 0 for company in COMPANIES for product in OWN_PRODUCTS}
    tx_df = _today_transactions()
    if tx_df.empty:
        return deltas
    for _, row in tx_df.iterrows():
        product = str(row.get("product_name") or "").strip()
        tx_type = str(row.get("tx_type") or "").strip()
        from_company = str(row.get("from_company") or "").strip()
        to_company = str(row.get("to_company") or "").strip()
        qty = int(row.get("qty") or 0)
        if tx_type in INBOUND_TYPES and to_company in COMPANIES:
            deltas[(to_company, product)] += qty
        elif tx_type in OUTBOUND_TYPES and from_company in COMPANIES:
            deltas[(from_company, product)] -= qty
        elif tx_type in MOVE_TYPES and from_company != to_company:
            if from_company in COMPANIES:
                deltas[(from_company, product)] -= qty
            if to_company in COMPANIES:
                deltas[(to_company, product)] += qty
    return deltas


def _fmt_qty(value) -> str:
    value = int(value or 0)
    return "-" if value == 0 else f"{value:,}"


def _fmt_delta(value) -> str:
    value = int(value or 0)
    if value > 0:
        return f"+{value:,}"
    if value < 0:
        return f"{value:,}"
    return "-"


def _company_table(company: str, delta_map: dict[tuple[str, str], int]) -> pd.DataFrame:
    base = pd.DataFrame({"표준제품명": OWN_PRODUCTS})
    current = _company_current_stock(company)
    if not current.empty:
        current = current.rename(columns={"product_name": "표준제품명", "qty": "현재수량"})
    else:
        current = pd.DataFrame(columns=["표준제품명", "현재수량"])
    out = base.merge(current, on="표준제품명", how="left")
    out["현재수량"] = out["현재수량"].fillna(0).astype(int)
    out["증감"] = out["표준제품명"].map(lambda p: int(delta_map.get((company, p), 0) or 0))
    out["전일수량"] = out["현재수량"] - out["증감"]
    out = out[["표준제품명", "전일수량", "증감", "현재수량"]]
    out["전일수량"] = out["전일수량"].map(_fmt_qty)
    out["증감"] = out["증감"].map(_fmt_delta)
    out["현재수량"] = out["현재수량"].map(_fmt_qty)
    return out


def _table_html(df: pd.DataFrame) -> str:
    head = "".join(f"<th>{escape(str(c))}</th>" for c in df.columns)
    rows = []
    for _, row in df.iterrows():
        cells = []
        for col in df.columns:
            cls = "name" if col == "표준제품명" else "num"
            cells.append(f"<td class='{cls}'>{escape(str(row[col]))}</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return """
    <table tabindex='-1'>
      <colgroup><col class='col-name'><col class='col-num'><col class='col-num'><col class='col-num'></colgroup>
      <thead><tr>{head}</tr></thead>
      <tbody>{body}</tbody>
    </table>
    """.format(head=head, body="".join(rows))


def _report_html(delta_map: dict[tuple[str, str], int]) -> str:
    cards = []
    for company in COMPANIES:
        cards.append(f"<section><h2>{escape(company)}</h2>{_table_html(_company_table(company, delta_map))}</section>")
    return f"""
    <!doctype html><html lang='ko'><head><meta charset='utf-8'>
    <style>
      html,body,*{{caret-color:transparent!important;}}
      body{{margin:0;padding:0;background:transparent;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#0f172a;cursor:default;user-select:none;overflow:hidden;}}
      .grid{{display:flex;flex-direction:column;gap:26px;align-items:flex-start;justify-content:flex-start;width:100%;}}
      section{{width:38vw;min-width:520px;box-sizing:border-box;overflow-x:auto;}}
      h2{{text-align:center;font-size:32px;font-weight:600;margin:0 0 10px 0;line-height:1.2;}}
      table{{border-collapse:collapse;table-layout:fixed;width:100%;background:white;font-size:13px;outline:0;}}
      .col-name{{width:150px;}}
      .col-num{{width:72px;}}
      th,td{{border:1px solid #e5e7eb;padding:6px 6px;line-height:1.25;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
      th{{background:#f8fafc;color:#334155;font-weight:800;text-align:center;}}
      td.name{{text-align:center;}}
      td.num{{text-align:center;}}
      @media(max-width:768px){{.grid{{display:block;width:100%;}}section{{width:100%;min-width:0;margin-bottom:28px;}}body{{overflow:auto;}}}}
    </style></head><body tabindex='-1'><div class='grid'>{''.join(cards)}</div></body></html>
    """


def page_own_product_status():
    st.title("자사제품 조회")
    st.caption(f"기준일자: {_today_text()} · 전일수량 = 현재수량 - 금일 입고/출고/사업장 이동 증감")
    components.html(_report_html(_today_delta_map()), height=900, scrolling=False)
