from datetime import date
from html import escape
from io import BytesIO

import pandas as pd
import streamlit as st

from nohtus.db import q
from nohtus.dates import display_date_only
from nohtus.services.closing import (
    _infer_customer_from_title,
    _extract_inbound_source_from_memo,
)
from nohtus.services.outbound import _find_korean_font


def _today_outbound_final_stock_map(items):
    if items.empty:
        return {}
    keys = items[["사업장", "표준제품명", "제조번호", "유통기한"]].drop_duplicates()
    result = {}
    for r in keys.itertuples(index=False):
        company = str(getattr(r, "사업장") or "")
        product = str(getattr(r, "표준제품명") or "")
        lot = str(getattr(r, "제조번호") or "-")
        exp = str(getattr(r, "유통기한") or "-")
        df = q(
            """
            SELECT COALESCE(SUM(qty), 0) AS qty
            FROM inventory
            WHERE company=?
              AND product_name=?
              AND COALESCE(lot, '-')=?
              AND COALESCE(exp_date, '-')=?
            """,
            (company, product, lot, exp),
        )
        result[(company, product, lot, exp)] = int(df.iloc[0]["qty"] or 0) if not df.empty else 0
    return result


def _today_outbound_display_df(items):
    group_cols = ["사업장", "로케이션", "표준제품명", "제조번호", "유통기한"]
    final_map = _today_outbound_final_stock_map(items)
    rows = []
    for key, grp in items.groupby(group_cols, sort=False, dropna=False):
        company, location, product, lot, exp = key
        total_qty = int(grp["출고수량"].sum())
        final_qty = final_map.get((company, product, lot, exp), 0)
        for i, rr in enumerate(grp.itertuples(index=False)):
            rows.append({
                "사업장": company if i == 0 else "",
                "로케이션": location if i == 0 else "",
                "제품명": product if i == 0 else "",
                "유통기한": exp if i == 0 else "",
                "매출처": getattr(rr, "매출처", ""),
                "수량": int(getattr(rr, "출고수량", 0) or 0),
                "총 출고수량": total_qty if i == 0 else "",
                "최종재고": final_qty if i == 0 else "",
            })
    return pd.DataFrame(rows, columns=["사업장", "로케이션", "제품명", "유통기한", "매출처", "수량", "총 출고수량", "최종재고"])


def _today_outbound_html(items, *, include_style=True):
    # 제조번호는 화면에 표시하지 않지만, LOT이 다른 재고가 섞이지 않도록 내부 그룹 기준에는 유지한다.
    group_cols = ["사업장", "로케이션", "표준제품명", "제조번호", "유통기한"]
    final_map = _today_outbound_final_stock_map(items)
    html = []
    if include_style:
        html.extend([
            "<style>",
            ".today-out-table{width:100%;border-collapse:collapse;background:white;border:1px solid #e5e7eb;font-size:14px;}",
            ".today-out-table th{background:#f1f5f9;color:#111827;font-weight:800;border:1px solid #e5e7eb;padding:8px;text-align:center;}",
            ".today-out-table td{border:1px solid #e5e7eb;padding:8px;vertical-align:middle;color:#111827;}",
            ".today-out-table td.num{text-align:right;font-weight:700;}",
            "</style>",
        ])
    html.extend([
        "<table class='today-out-table'>",
        "<thead><tr><th>사업장</th><th>로케이션</th><th>제품명</th><th>유통기한</th><th>매출처</th><th>수량</th><th>총 출고수량</th><th>최종재고</th></tr></thead><tbody>",
    ])
    for key, grp in items.groupby(group_cols, sort=False, dropna=False):
        company, location, product, lot, exp = key
        total_qty = int(grp["출고수량"].sum())
        final_qty = final_map.get((company, product, lot, exp), 0)
        rowspan = len(grp)
        for i, rr in enumerate(grp.itertuples(index=False)):
            html.append("<tr>")
            if i == 0:
                html.append(f"<td rowspan='{rowspan}'>{escape(str(company))}</td>")
                html.append(f"<td rowspan='{rowspan}'>{escape(str(location))}</td>")
                html.append(f"<td rowspan='{rowspan}'>{escape(str(product))}</td>")
                html.append(f"<td rowspan='{rowspan}'>{escape(str(exp))}</td>")
            html.append(f"<td>{escape(str(getattr(rr, '매출처', '') or '-'))}</td>")
            html.append(f"<td class='num'>{int(getattr(rr, '출고수량', 0) or 0):,}</td>")
            if i == 0:
                html.append(f"<td class='num' rowspan='{rowspan}'>{total_qty:,}</td>")
                html.append(f"<td class='num' rowspan='{rowspan}'>{final_qty:,}</td>")
            html.append("</tr>")
    html.append("</tbody></table>")
    return "".join(html)


def _render_today_outbound_html(items):
    st.markdown(_today_outbound_html(items), unsafe_allow_html=True)


def _today_outbound_pdf_bytes(items, ds):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    bio = BytesIO()
    font_name = "Helvetica"
    font_path = _find_korean_font()
    if font_path:
        try:
            pdfmetrics.registerFont(TTFont("NOHTUS_KR_CLOSING", font_path))
            font_name = "NOHTUS_KR_CLOSING"
        except Exception:
            font_name = "Helvetica"

    styles = getSampleStyleSheet()
    styles["Title"].fontName = font_name
    styles["Normal"].fontName = font_name
    doc = SimpleDocTemplate(bio, pagesize=landscape(A4), leftMargin=20, rightMargin=20, topMargin=24, bottomMargin=24)
    story = [Paragraph(f"마감 체크리스트 · {ds}", styles["Title"]), Spacer(1, 12)]

    headers = ["사업장", "로케이션", "제품명", "유통기한", "매출처", "수량", "총 출고수량", "최종재고"]
    data = [headers]
    spans = []
    group_cols = ["사업장", "로케이션", "표준제품명", "제조번호", "유통기한"]
    final_map = _today_outbound_final_stock_map(items)
    row_idx = 1
    for key, grp in items.groupby(group_cols, sort=False, dropna=False):
        company, location, product, lot, exp = key
        total_qty = int(grp["출고수량"].sum())
        final_qty = final_map.get((company, product, lot, exp), 0)
        start = row_idx
        for i, rr in enumerate(grp.itertuples(index=False)):
            data.append([
                str(company) if i == 0 else "",
                str(location) if i == 0 else "",
                str(product) if i == 0 else "",
                str(exp) if i == 0 else "",
                str(getattr(rr, "매출처", "") or "-"),
                f"{int(getattr(rr, '출고수량', 0) or 0):,}",
                f"{total_qty:,}" if i == 0 else "",
                f"{final_qty:,}" if i == 0 else "",
            ])
            row_idx += 1
        end = row_idx - 1
        if end > start:
            for col in [0, 1, 2, 3, 6, 7]:
                spans.append(("SPAN", (col, start), (col, end)))

    table = Table(data, colWidths=[62, 72, 178, 82, 130, 48, 72, 62], repeatRows=1)
    style_cmds = [
        ("FONTNAME", (0, 0), (-1, -1), font_name),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F5F9")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#111827")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D1D5DB")),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("ALIGN", (5, 1), (7, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
    ]
    style_cmds.extend(spans)
    table.setStyle(TableStyle(style_cmds))
    story.append(table)
    doc.build(story)
    bio.seek(0)
    return bio.getvalue()


def page_closing():
    st.title("마감")
    st.caption("출고의 마지막 단계입니다. 오늘 출고 체크와 업무일지 작성 기능을 한 화면에서 전환합니다.")
    tab = st.radio("마감", ["오늘 출고 체크", "업무일지 작성"], horizontal=True, key="closing_sub")

    target_date = st.date_input("기준일", value=date.today(), key="closing_date")
    ds = str(target_date)

    if tab == "오늘 출고 체크":
        items = q("""SELECT COALESCE(o.title, '') AS 출고지시서제목,
                            o.id AS 출고지시서ID,
                            i.inventory_id AS 재고ID,
                            i.company AS 사업장,
                            i.location AS 로케이션,
                            i.product_name AS 표준제품명,
                            COALESCE(i.lot, '-') AS 제조번호,
                            COALESCE(i.exp_date, '-') AS 유통기한,
                            i.qty AS 출고수량
                     FROM outbound_orders o
                     JOIN outbound_order_items i ON o.id=i.order_id
                     WHERE o.order_date=?
                       AND IFNULL(o.status,'')<>'취소됨'
                       AND EXISTS (
                           SELECT 1
                           FROM transactions t
                           WHERE substr(t.created_at,1,10)=o.order_date
                             AND t.tx_type IN ('출고지시','출고지시수정','출고')
                             AND COALESCE(t.from_company,'')=COALESCE(i.company,'')
                             AND t.product_name=i.product_name
                             AND COALESCE(t.lot,'-')=COALESCE(i.lot,'-')
                             AND COALESCE(t.exp_date,'-')=COALESCE(i.exp_date,'-')
                             AND COALESCE(t.from_location,'')=COALESCE(i.location,'')
                             AND CAST(t.qty AS INTEGER)=CAST(i.qty AS INTEGER)
                             AND COALESCE(t.memo,'') LIKE '%' || '출고지시서 #' || CAST(o.id AS TEXT) || '%'
                       )
                     ORDER BY i.company, i.location, i.product_name, i.lot, i.exp_date, o.id, i.id""", (ds,))
        if items.empty:
            st.info("해당 날짜의 출고지시가 없습니다.")
        else:
            items["로케이션"] = items["로케이션"].astype(str).replace("", "-")
            items["유통기한"] = items["유통기한"].apply(display_date_only)
            items["출고수량"] = pd.to_numeric(items["출고수량"], errors="coerce").fillna(0).astype(int)
            try:
                customers_for_close = q("SELECT customer_name, manager FROM customers ORDER BY LENGTH(customer_name) DESC")
                items["매출처"] = items["출고지시서제목"].apply(lambda x: _infer_customer_from_title(x, customers_for_close)[0])
            except Exception:
                items["매출처"] = ""
            _render_today_outbound_html(items)
            btn_left, btn_mid, btn_right = st.columns([3, 2, 3])
            with btn_mid:
                st.download_button(
                    "마감 체크리스트 PDF 다운로드",
                    data=_today_outbound_pdf_bytes(items, ds),
                    file_name=f"NOHTUS_마감체크_{ds}.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                )
        return

    st.subheader("업무일지 작성")
    history = q("""
        SELECT created_at, tx_type, product_name, lot, exp_date,
               from_company, from_location, to_company, to_location, qty, memo
        FROM transactions
        WHERE substr(created_at, 1, 10)=?
        ORDER BY created_at, id
    """, (ds,))
    if history.empty:
        st.info("해당 날짜의 재고 이력이 없습니다.")
        return

    rows = []
    for r in history.itertuples(index=False):
        tx_type = str(getattr(r, "tx_type", "") or "")
        memo = str(getattr(r, "memo", "") or "")
        rows.append({
            "시간": str(getattr(r, "created_at", "") or "")[11:16],
            "업무구분": tx_type,
            "제품명": str(getattr(r, "product_name", "") or ""),
            "제조번호": str(getattr(r, "lot", "-") or "-"),
            "유통기한": display_date_only(getattr(r, "exp_date", "-") or "-"),
            "출발": " / ".join(v for v in [str(getattr(r, "from_company", "") or ""), str(getattr(r, "from_location", "") or "")] if v),
            "도착": " / ".join(v for v in [str(getattr(r, "to_company", "") or ""), str(getattr(r, "to_location", "") or "")] if v),
            "수량": int(getattr(r, "qty", 0) or 0),
            "입고처": _extract_inbound_source_from_memo(memo),
            "메모": memo,
        })
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
