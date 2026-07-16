from __future__ import annotations

import re
from html import escape
from io import BytesIO

import pandas as pd

import nohtus.pages.closing as closing_page
from nohtus.pages.erp_stock_compare_inventory import page_erp_stock_compare as page_erp_stock_compare_live
from nohtus.services.export_waiting import ensure_export_waiting_tables


_VALID_HISTORY_TYPES = (
    "'출고지시'",
    "'출고지시수정'",
    "'출고지시 재차감'",
    "'출고'",
    "'사업장이동'",
    "'사업장+위치이동'",
    "'사업장 이동'",
)


def _replace_transaction_history_gate(sql):
    """지정 출고일자를 유지하면서 관련 이력 유형을 폭넓게 인정한다."""
    if not isinstance(sql, str):
        return sql
    if "FROM outbound_orders o" not in sql or "WHERE o.order_date=?" not in sql:
        return sql

    valid_types = ",".join(_VALID_HISTORY_TYPES)
    replacement = f"""
                        AND EXISTS (
                            SELECT 1
                            FROM transactions t
                            WHERE t.tx_type IN ({valid_types})
                              AND COALESCE(t.memo,'') LIKE '%' || '출고지시서 #' || CAST(o.id AS TEXT) || '%'
                        )
 """
    return re.sub(
        r"\n\s+AND EXISTS \(.*?\n\s+\)\n(?=\s+ORDER BY)",
        replacement,
        sql,
        count=1,
        flags=re.DOTALL,
    )


def _is_today_outbound_query(sql):
    text = str(sql or "")
    return "FROM outbound_orders o" in text and "JOIN outbound_order_items i" in text and "WHERE o.order_date=?" in text


def _export_waiting_rows(original_q, ds):
    ensure_export_waiting_tables()
    return original_q(
        """
        SELECT o.title AS 출고지시서제목,
               -o.id AS 출고지시서ID,
               i.source_inventory_id AS 재고ID,
               i.company AS 사업장,
               i.source_location AS 로케이션,
               i.product_name AS 표준제품명,
               COALESCE(i.lot, '-') AS 제조번호,
               COALESCE(i.exp_date, '-') AS 유통기한,
               i.qty AS 출고수량
        FROM export_waiting_orders o
        JOIN export_waiting_items i ON o.id=i.order_id
        WHERE substr(COALESCE(i.moved_at, o.created_at), 1, 10)=?
          AND o.status IN ('waiting', 'confirmed')
        ORDER BY i.company, i.source_location, i.product_name, i.lot, i.exp_date, o.id, i.id
        """,
        (str(ds),),
    )


def _location_final_stock_map(items, query_func):
    """출고·수출대기 후 각 출발 로케이션에 실제로 남은 현재 수량을 계산한다."""
    if items is None or items.empty:
        return {}
    key_cols = ["사업장", "로케이션", "표준제품명", "제조번호", "유통기한"]
    result = {}
    for row in items[key_cols].drop_duplicates().itertuples(index=False):
        company, location, product, lot, exp = [str(value or "-") for value in row]
        stock = query_func(
            """
            SELECT COALESCE(SUM(qty), 0) AS qty
            FROM inventory
            WHERE company=?
              AND location=?
              AND product_name=?
              AND COALESCE(lot, '-')=?
              AND COALESCE(exp_date, '-')=?
            """,
            (company, location, product, lot, exp),
        )
        result[(company, location, product, lot, exp)] = int(stock.iloc[0]["qty"] or 0) if not stock.empty else 0
    return result


def _location_aware_html(items, *, include_style=True):
    group_cols = ["사업장", "로케이션", "표준제품명", "제조번호", "유통기한"]
    final_map = _location_final_stock_map(items, closing_page.q)
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
    for key, group in items.groupby(group_cols, sort=False, dropna=False):
        company, location, product, lot, exp = key
        total_qty = int(group["출고수량"].sum())
        final_qty = final_map.get(tuple(str(value or "-") for value in key), 0)
        rowspan = len(group)
        for index, row in enumerate(group.itertuples(index=False)):
            html.append("<tr>")
            if index == 0:
                html.append(f"<td rowspan='{rowspan}'>{escape(str(company))}</td>")
                html.append(f"<td rowspan='{rowspan}'>{escape(str(location))}</td>")
                html.append(f"<td rowspan='{rowspan}'>{escape(str(product))}</td>")
                html.append(f"<td rowspan='{rowspan}'>{escape(str(exp))}</td>")
            html.append(f"<td>{escape(str(getattr(row, '매출처', '') or '-'))}</td>")
            html.append(f"<td class='num'>{int(getattr(row, '출고수량', 0) or 0):,}</td>")
            if index == 0:
                html.append(f"<td class='num' rowspan='{rowspan}'>{total_qty:,}</td>")
                html.append(f"<td class='num' rowspan='{rowspan}'>{final_qty:,}</td>")
            html.append("</tr>")
    html.append("</tbody></table>")
    return "".join(html)


def _location_aware_pdf(items, ds):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    bio = BytesIO()
    font_name = "Helvetica"
    font_path = closing_page._find_korean_font()
    if font_path:
        try:
            pdfmetrics.registerFont(TTFont("NOHTUS_KR_CLOSING", font_path))
            font_name = "NOHTUS_KR_CLOSING"
        except Exception:
            pass

    styles = getSampleStyleSheet()
    styles["Title"].fontName = font_name
    styles["Normal"].fontName = font_name
    document = SimpleDocTemplate(bio, pagesize=landscape(A4), leftMargin=20, rightMargin=20, topMargin=24, bottomMargin=24)
    story = [Paragraph(f"마감 체크리스트 · {ds}", styles["Title"]), Spacer(1, 12)]
    data = [["사업장", "로케이션", "제품명", "유통기한", "매출처", "수량", "총 출고수량", "최종재고"]]
    spans = []
    row_index = 1
    group_cols = ["사업장", "로케이션", "표준제품명", "제조번호", "유통기한"]
    final_map = _location_final_stock_map(items, closing_page.q)

    for key, group in items.groupby(group_cols, sort=False, dropna=False):
        company, location, product, lot, exp = key
        total_qty = int(group["출고수량"].sum())
        final_qty = final_map.get(tuple(str(value or "-") for value in key), 0)
        start = row_index
        for index, row in enumerate(group.itertuples(index=False)):
            data.append([
                str(company) if index == 0 else "",
                str(location) if index == 0 else "",
                str(product) if index == 0 else "",
                str(exp) if index == 0 else "",
                str(getattr(row, "매출처", "") or "-"),
                f"{int(getattr(row, '출고수량', 0) or 0):,}",
                f"{total_qty:,}" if index == 0 else "",
                f"{final_qty:,}" if index == 0 else "",
            ])
            row_index += 1
        end = row_index - 1
        if end > start:
            for column in [0, 1, 2, 3, 6, 7]:
                spans.append(("SPAN", (column, start), (column, end)))

    table = Table(data, colWidths=[62, 72, 178, 82, 130, 48, 72, 62], repeatRows=1)
    commands = [
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
    commands.extend(spans)
    table.setStyle(TableStyle(commands))
    story.append(table)
    document.build(story)
    bio.seek(0)
    return bio.getvalue()


def page_closing():
    """출고일자 보정, 수출대기 원위치 체크, inventory 기준 ERP/WMS 비교를 적용한다."""
    original_q = closing_page.q
    original_erp_compare = closing_page.page_erp_stock_compare
    original_html = closing_page._today_outbound_html
    original_pdf = closing_page._today_outbound_pdf_bytes

    def patched_q(sql, params=()):
        result = original_q(_replace_transaction_history_gate(sql), params)
        if not _is_today_outbound_query(sql):
            return result
        ds = params[0] if params else ""
        export_rows = _export_waiting_rows(original_q, ds)
        if export_rows is None or export_rows.empty:
            return result
        if result is None or result.empty:
            return export_rows
        return pd.concat([result, export_rows], ignore_index=True)

    closing_page.q = patched_q
    closing_page.page_erp_stock_compare = page_erp_stock_compare_live
    closing_page._today_outbound_html = _location_aware_html
    closing_page._today_outbound_pdf_bytes = _location_aware_pdf
    try:
        return closing_page.page_closing()
    finally:
        closing_page.q = original_q
        closing_page.page_erp_stock_compare = original_erp_compare
        closing_page._today_outbound_html = original_html
        closing_page._today_outbound_pdf_bytes = original_pdf
