"""발주서 미리보기: 화면에 보이는 그대로 PDF/JPG로 저장한다."""
from __future__ import annotations

from datetime import datetime

from ui.preview_export import inject_export_toolbar


def render(core_app, vendor, order_items, request_note, order_date=None) -> None:
    st = core_app.st
    order_date = str(order_date or "") or datetime.now().strftime("%Y-%m-%d")
    vendor_name = str(vendor.get("거래처명", "") or "")

    html = core_app.render_order_html(
        vendor,
        order_items,
        request_note,
        order_date=order_date,
    )
    filename_base = f"발주서_{vendor_name}_{order_date}".strip("_")
    html = inject_export_toolbar(html, filename_base)
    core_app.components.html(html, height=830, scrolling=True)
