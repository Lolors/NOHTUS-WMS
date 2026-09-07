"""1.0.x 애플리케이션 조립과 기존 UI 호환 연결."""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

from repositories import purchase_repository
from services.master_data_service import MasterDataService
from services.order_service import OrderService
from services.purchase_service import PurchaseService
from services.correction_service import CorrectionService


@st.cache_resource(show_spinner=False)
def build_application(base_dir: Path):
    layer_dir = base_dir / "app_layers"
    if str(layer_dir) not in sys.path:
        sys.path.insert(0, str(layer_dir))

    from repositories.catalog_repository import CatalogRepository
    from repositories.draft_repository import DraftRepository
    from repositories.order_repository import OrderRepository
    from ui.pages.router import run as run_pages
    from ui.preview_layout import render_order_html
    from ui.purchase_preview import render as render_purchase_preview

    import core_app
    sys.modules["app"] = core_app

    import db_migration
    db_status = db_migration.initialize_database(core_app.DATA)

    import app_order_review as final_app
    purchase = final_app.purchase
    purchase.STATEMENT_ITEM_COLUMNS = purchase_repository.STATEMENT_ITEM_COLUMNS

    original_text_input = core_app.st.text_input

    def text_input_with_substitution_reason(label, *args, **kwargs):
        if str(label) != "대체사유":
            return original_text_input(label, *args, **kwargs)

        selectbox_kwargs = {
            key: kwargs[key]
            for key in ("key", "help", "disabled", "label_visibility", "on_change", "args", "kwargs")
            if key in kwargs
        }
        return core_app.st.selectbox(
            "대체사유",
            ["브랜드 대체", "발주 실수", "구매자 변심", "기타"],
            index=0,
            **selectbox_kwargs,
        )

    core_app.st.text_input = text_input_with_substitution_reason
    purchase.st.text_input = text_input_with_substitution_reason

    original_data_editor = core_app.st.data_editor

    def stable_receipt_editor(data, *args, **kwargs):
        widget_key = str(kwargs.get("key") or "")
        if not widget_key.startswith("statement_receipt_input_"):
            return original_data_editor(data, *args, **kwargs)
        if data is None or getattr(data, "empty", True):
            return data

        result = data.copy()
        widths = [0.72, 2.55, 0.95, 1.0, 1.15, 1.15, 1.2, 0.85]
        headers = core_app.st.columns(widths, gap="small")
        for column, title in zip(
            headers,
            ["복사/삭제", "제품명", "규격", "입고수량", "매입단가", "제조번호", "유통기한", "가격 적용"],
        ):
            column.markdown(
                f"<div style='font-size:13px;font-weight:700;color:#475569;padding:0 2px 6px;'>{title}</div>",
                unsafe_allow_html=True,
            )

        for index, row in result.iterrows():
            row_id = int(row.get("행번호", index))
            key_prefix = f"{widget_key}_row_{row_id}"
            columns = core_app.st.columns(widths, gap="small")

            result.at[index, "복사/삭제"] = columns[0].checkbox(
                "복사/삭제",
                value=bool(row.get("복사/삭제", False)),
                key=f"{key_prefix}_selected",
                label_visibility="collapsed",
            )
            columns[1].markdown(
                f"<div style='min-height:38px;display:flex;align-items:center;font-size:14px;padding:0 4px;'>"
                f"{str(row.get('제품명', '') or '')}</div>",
                unsafe_allow_html=True,
            )
            columns[2].markdown(
                f"<div style='min-height:38px;display:flex;align-items:center;font-size:13px;padding:0 4px;'>"
                f"{str(row.get('규격', '') or '')}</div>",
                unsafe_allow_html=True,
            )
            result.at[index, "입고수량"] = columns[3].number_input(
                "입고수량",
                min_value=0,
                value=max(0, int(float(row.get("입고수량", 0) or 0))),
                step=1,
                key=f"{key_prefix}_quantity",
                label_visibility="collapsed",
            )
            result.at[index, "매입단가"] = columns[4].text_input(
                "매입단가",
                value="" if str(row.get("매입단가", "") or "").strip() in {"", "0", "0.0"} else str(row.get("매입단가", "")),
                key=f"{key_prefix}_price_v2",
                placeholder="단가 입력",
                label_visibility="collapsed",
            )
            result.at[index, "제조번호"] = columns[5].text_input(
                "제조번호",
                value=str(row.get("제조번호", "") or ""),
                key=f"{key_prefix}_lot",
                label_visibility="collapsed",
            )
            result.at[index, "유통기한"] = columns[6].text_input(
                "유통기한",
                value=str(row.get("유통기한", "") or ""),
                key=f"{key_prefix}_expiry",
                label_visibility="collapsed",
            )
            result.at[index, "현재 가격 적용"] = columns[7].checkbox(
                "현재 가격 적용",
                value=bool(row.get("현재 가격 적용", True)),
                key=f"{key_prefix}_apply_price",
                label_visibility="collapsed",
            )

        return result

    core_app.st.data_editor = stable_receipt_editor
    purchase.st.data_editor = stable_receipt_editor

    core_app.render_order_html = lambda vendor, items, note, order_id=None, order_date=None: render_order_html(
        core_app, vendor, items, note, order_id=order_id, order_date=order_date
    )
    core_app.render_purchase_preview = lambda vendor, items, note, order_date=None: render_purchase_preview(
        core_app, vendor, items, note, order_date=order_date
    )

    if db_status.get("ok"):
        import app_product_schema as product_schema

        catalog_repo = CatalogRepository(core_app.DATA)
        draft_repo = DraftRepository(core_app.DATA)
        draft_repo.migrate_legacy_csv_once()
        order_repo = OrderRepository(core_app.DATA, core_app)
        master_data_service = MasterDataService(catalog_repo)
        order_service = OrderService(core_app, draft_repo, order_repo)
        purchase_service = PurchaseService(core_app.DATA)
        correction_service = CorrectionService(core_app.DATA)

        @core_app.st.cache_data(show_spinner=False)
        def load_data_from_repositories():
            vendors, products, aliases = master_data_service.load_all()
            drafts, draft_items, orders, order_items = order_service.load_all()
            return vendors, products, aliases, drafts, draft_items, orders, order_items

        @core_app.st.cache_data(show_spinner=False)
        def load_purchase_data_cached():
            return purchase_service.load_all()

        def clear_data_cache() -> None:
            load_data_from_repositories.clear()
            load_purchase_data_cached.clear()

        master_data_service.set_cache_invalidator(clear_data_cache)
        order_service.set_cache_invalidator(clear_data_cache)
        purchase_service.set_cache_invalidator(clear_data_cache)
        correction_service.set_cache_invalidator(clear_data_cache)

        def read_products_from_db():
            return master_data_service.read_products(product_schema)

        core_app.load_data = load_data_from_repositories
        product_schema.read_products_file = read_products_from_db
        product_schema.save_products_with_schema = master_data_service.save_products

        core_app.save_products = master_data_service.save_products
        core_app.save_aliases = master_data_service.save_aliases
        core_app.save_vendors = master_data_service.save_vendors
        core_app.save_order = order_service.save_order
        core_app.delete_order = order_service.delete_order
        core_app.save_draft = order_service.save_draft
        core_app.delete_draft = order_service.delete_draft

        purchase.load_purchase_data = load_purchase_data_cached

        purchase.save_table = purchase_service.save_table
        core_app.correction_service = correction_service

    return core_app, purchase, db_status, run_pages


def run(base_dir: Path) -> None:
    core_app, purchase, db_status, run_pages = build_application(base_dir)

    if not db_status.get("ok"):
        core_app.st.error(
            "SQLite DB 초기화에 실패했습니다. 기존 CSV 방식으로 앱을 계속 실행합니다.\n\n"
            f"오류: {db_status.get('error', '알 수 없는 오류')}"
        )
    elif db_status.get("migrated"):
        core_app.st.toast("기존 CSV 데이터를 SQLite DB로 안전하게 이전했습니다.", icon="✅")

    run_pages(core_app, purchase)
