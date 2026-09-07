"""발주서 미리보기 표 레이아웃."""
from __future__ import annotations

from datetime import datetime


def render_order_html(core_app, vendor, order_items, request_note, order_id=None, order_date=None):
    template = (
        core_app.TEMPLATE_FILE.read_text(encoding="utf-8")
        if core_app.TEMPLATE_FILE.exists()
        else core_app.DEFAULT_TEMPLATE
    )
    logo_b64 = core_app.get_logo_base64()
    order_id = order_id or f"PO-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    order_date = order_date or datetime.now().strftime("%Y-%m-%d")

    rows_html = ""
    for idx, item in enumerate(order_items, 1):
        packaging_unit = item.get("포장단위", item.get("단위", ""))
        rows_html += f"""
        <tr>
            <td>{idx}</td>
            <td class="left">{item.get("정식제품명", item.get("제품명", ""))}</td>
            <td>{item.get("규격", "")}</td>
            <td>{core_app.fmt_int(item.get("수량", 0))}</td>
            <td>{packaging_unit}</td>
        </tr>
        """

    if not rows_html:
        rows_html = '<tr><td colspan="5" class="empty">발주 품목이 없습니다.</td></tr>'

    total_count, total_qty = core_app.calc_totals(order_items)

    if logo_b64:
        template = (
            template.replace("{% if_logo %}", "")
            .replace("{% else_logo %}", "<!--")
            .replace("{% endif_logo %}", "-->")
        )
    else:
        template = (
            template.replace("{% if_logo %}", "<!--")
            .replace("{% else_logo %}", "-->")
            .replace("{% endif_logo %}", "")
        )

    header_patterns = [
        "<th>No.</th>\n                <th>제품코드</th>\n                <th>제품명</th>\n                <th>규격</th>\n                <th>단위</th>\n                <th>수량</th>",
        "<th>No.</th>\n                <th>제품코드</th>\n                <th>제품명</th>\n                <th>규격</th>\n                <th>수량</th>\n                <th>단위</th>",
        "<th>No.</th>\n                <th>제품명</th>\n                <th>규격</th>\n                <th>수량</th>\n                <th>단위</th>",
        "<th>No.</th>\n                <th>제품명</th>\n                <th>규격</th>\n                <th>수량</th>\n                <th>포장단위</th>",
    ]
    desired_header = (
        "<th>No.</th>\n"
        "                <th>제품명</th>\n"
        "                <th>규격</th>\n"
        "                <th>수량</th>\n"
        "                <th>포장단위</th>"
    )
    for pattern in header_patterns:
        template = template.replace(pattern, desired_header)

    # 요청 비율 0.7 : 5 : 2 : 1 : 1.3을 백분율로 환산합니다.
    ratio_css = """
<style>
.item-table { table-layout: fixed !important; width: 100% !important; }
.item-table th:nth-child(1), .item-table td:nth-child(1) { width: 7% !important; }
.item-table th:nth-child(2), .item-table td:nth-child(2) { width: 50% !important; }
.item-table th:nth-child(3), .item-table td:nth-child(3) { width: 20% !important; }
.item-table th:nth-child(4), .item-table td:nth-child(4) { width: 10% !important; }
.item-table th:nth-child(5), .item-table td:nth-child(5) { width: 13% !important; }
</style>
"""
    template = template.replace("</head>", ratio_css + "</head>")

    html = (
        template.replace("{{LOGO_BASE64}}", logo_b64)
        .replace("{{ORDER_ID}}", order_id)
        .replace("{{ORDER_DATE}}", order_date)
        .replace("{{COMPANY_NAME}}", core_app.COMPANY["상호"])
        .replace("{{COMPANY_OWNER}}", core_app.COMPANY["대표"])
        .replace("{{COMPANY_ADDRESS}}", core_app.COMPANY["주소"])
        .replace("{{COMPANY_PHONE}}", core_app.COMPANY["연락처"])
        .replace("{{COMPANY_FAX}}", core_app.COMPANY["팩스"])
        .replace("{{COMPANY_REGNO}}", core_app.COMPANY["등록번호"])
        .replace("{{VENDOR_NAME}}", str(vendor.get("거래처명", "")))
        .replace("{{VENDOR_ADDRESS}}", str(vendor.get("배송지", "")))
        .replace("{{VENDOR_PHONE}}", str(vendor.get("연락처", "")))
        .replace("{{ITEM_ROWS}}", rows_html)
        .replace("{{TOTAL_COUNT}}", core_app.fmt_int(total_count))
        .replace("{{TOTAL_QTY}}", core_app.fmt_int(total_qty))
        .replace("{{REQUEST_NOTE}}", request_note or "")
    )

    if not str(request_note or "").strip():
        import re

        html = re.sub(
            r'\s*<div class="request">\s*<b>요청사항</b><br>\s*-\s*</div>\s*',
            "\n",
            html,
            flags=re.DOTALL,
        )
    return html
