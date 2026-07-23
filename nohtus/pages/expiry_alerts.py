from __future__ import annotations

from datetime import date, datetime, timedelta
from html import escape

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
    return df[["사업장", "로케이션", "표준제품명", "유통기한", "수량"]]


def _expiry_badge(exp_date_text: str) -> tuple[str, str]:
    text = str(exp_date_text or "").strip()
    if not text:
        return "", ""

    parsed = None
    for fmt in ("%Y.%m.%d", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            parsed = datetime.strptime(text, fmt).date()
            break
        except ValueError:
            continue

    if parsed is None:
        return "", ""

    days = (parsed - date.today()).days
    if days <= 90:
        return "3개월 이내", "red"
    if days <= 180:
        return "4개월~6개월 이내", "yellow"
    return "7개월~1년 이내", "blue"


def _render_html_table(rows: pd.DataFrame):
    body = []
    for r in rows.itertuples(index=False):
        company = escape(str(getattr(r, "사업장") or ""))
        location = escape(str(getattr(r, "로케이션") or ""))
        product_name = escape(str(getattr(r, "표준제품명") or ""))
        exp_date_raw = str(getattr(r, "유통기한") or "")
        exp_date = escape(exp_date_raw)
        badge_text, badge_class = _expiry_badge(exp_date_raw)
        badge_html = (
            f"<span class='expiry-badge {badge_class}'>{escape(badge_text)}</span>"
            if badge_text
            else ""
        )
        qty = int(getattr(r, "수량") or 0)
        body.append(
            "<tr>"
            f"<td>{company}</td>"
            f"<td>{location}</td>"
            f"<td>{product_name}</td>"
            f"<td><div class='expiry-date-cell'><span>{exp_date}</span>{badge_html}</div></td>"
            f"<td class='qty'>{qty:,}</td>"
            "</tr>"
        )

    st.markdown(
        """
        <style>
        .expiry-alert-table-wrap{
            width:40vw;
            max-width:100%;
            height:auto!important;
            max-height:none!important;
            overflow:visible!important;
            margin-top:14px;
        }
        .expiry-alert-table{
            width:100%;
            border-collapse:collapse;
            table-layout:auto;
            font-size:14px;
            background:white;
        }
        .expiry-alert-table th{
            background:#f8fafc;
            color:#334155;
            font-weight:800;
            border-bottom:1px solid #dbe3ee;
            padding:10px 12px;
            text-align:left;
            white-space:nowrap;
        }
        .expiry-alert-table td{
            border-bottom:1px solid #edf2f7;
            color:#111827;
            padding:9px 12px;
            vertical-align:middle;
        }
        .expiry-alert-table td:nth-child(1),
        .expiry-alert-table td:nth-child(2),
        .expiry-alert-table td:nth-child(4),
        .expiry-alert-table td:nth-child(5){
            white-space:nowrap;
        }
        .expiry-alert-table td.qty{
            text-align:right;
            color:#4f6fff;
            font-weight:700;
        }
        .expiry-date-cell{
            display:flex;
            align-items:center;
            gap:7px;
            white-space:nowrap;
        }
        .expiry-badge{
            display:inline-flex;
            align-items:center;
            justify-content:center;
            padding:3px 7px;
            border-radius:999px;
            font-size:11px;
            font-weight:750;
            line-height:1.2;
            white-space:nowrap;
        }
        .expiry-badge.red{background:#fee2e2;color:#b91c1c;}
        .expiry-badge.yellow{background:#fef3c7;color:#a16207;}
        .expiry-badge.blue{background:#dbeafe;color:#1d4ed8;}
        @media (max-width: 768px){
            .expiry-alert-table-wrap{width:100%;}
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div class='expiry-alert-table-wrap'>"
        "<table class='expiry-alert-table'>"
        "<thead><tr><th>사업장</th><th>로케이션</th><th>표준제품명</th><th>유통기한</th><th>수량</th></tr></thead>"
        f"<tbody>{''.join(body)}</tbody>"
        "</table></div>",
        unsafe_allow_html=True,
    )


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
    _render_html_table(rows)
