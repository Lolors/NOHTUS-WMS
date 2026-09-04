"""Top-level page router for the 1.x application."""
from __future__ import annotations

from ui.navigation import render_sidebar
from ui.pages import (
    accounting_export_delete_ui,
    master_data,
    order_list_enhanced,
    order_write,
    orders,
    purchase_enhancements,
    purchases,
    statement_history_lot_ui,
    statement_register_lot_ui,
    integrated_correction,
)


def run(core_app, purchase_module) -> None:
    purchase_module.ensure_purchase_files()
    core_app.inject_css()
    core_app.init_state()

    # 대체입고 품목도 원발주품목 기준으로 입고상태를 계산합니다.
    orders._item_key = statement_register_lot_ui.item_key
    purchase_enhancements._item_key = statement_register_lot_ui.item_key

    vendors, products, aliases, drafts, draft_items, order_headers, order_items = core_app.load_data()
    data = {
        "vendors": vendors,
        "products": products,
        "aliases": aliases,
        "drafts": drafts,
        "draft_items": draft_items,
        "orders": order_headers,
        "order_items": order_items,
    }
    page = render_sidebar(core_app.st)

    routes = {
        "발주 작성": lambda: order_write.render(core_app, data),
        "임시저장 목록": lambda: orders.drafts(core_app, data),
        "발주서 목록": lambda: order_list_enhanced.render(core_app, data, purchase_module),
        "거래명세서 등록": lambda: statement_register_lot_ui.render(purchase_module, data),
        "거래명세서 내역": lambda: statement_history_lot_ui.render(purchase_module, data),
        "월별 매입 현황": lambda: accounting_export_delete_ui.render(purchase_module, data),
        "통합 수정": lambda: integrated_correction.render(core_app, data, purchase_module),
    }

    handler = routes.get(page)
    if master_data.handles(page):
        handler = lambda: master_data.render(page, core_app, data)
    if handler is None:
        core_app.page_placeholder(page)
        return

    if page == "발주 작성":
        handler()
        return

    core_app.st.markdown(
        """
<style>
.st-key-standard_page_content {
    width: 60vw;
    max-width: 60vw;
}
.st-key-standard_page_content > div {
    width: 100%;
}
@media (max-width: 1100px) {
    .st-key-standard_page_content {
        width: 100%;
        max-width: 100%;
    }
}
</style>
""",
        unsafe_allow_html=True,
    )
    with core_app.st.container(key="standard_page_content"):
        handler()
