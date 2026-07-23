import streamlit as st

from styles import apply_style
from nohtus.auth import allowed_pages_for_current_user, can_access_page, is_admin, render_user_box, require_login
from nohtus.config import APP_TITLE, VERSION
from nohtus.db_init import init_db
from nohtus.device import is_mobile, sync_mobile_flag
from nohtus.navigation import render_sidebar
from nohtus.pages.all_inventory import page_all_inventory
from nohtus.pages.closing_print import page_closing
from nohtus.pages.expiry_alerts import page_expiry_alerts
from nohtus.pages.export_waiting import page_export_waiting as _page_export_waiting
from nohtus.pages.saved_export_waiting import page_saved_export_waiting
from nohtus.pages.history_business import page_history
from nohtus.pages.inbound import page_inbound as page_inbound_refactored
from nohtus.pages.location_map_business import page_map
from nohtus.pages.customer_master_business import page_customer_master
from nohtus.pages.mobile_stock import page_mobile_stock_finder
from nohtus.pages.move import page_move
from nohtus.pages.outbound_date_fix import page_outbound
from nohtus.pages.own_product_status import page_own_product_status
from nohtus.pages.product_matching_business import page_product_matching
from nohtus.pages.product_shortcuts import page_recent_products
from nohtus.pages.purchase_history_single import page_purchase_history
from nohtus.pages.saved_outbound_date_fix import page_saved_outbound as page_saved_outbound_refactored
from nohtus.pages.shippable_inventory import page_shippable_inventory
from nohtus.pages.stocktake_business import page_stocktake


def page_export_waiting():
    """수출대기 화면에서 혼재된 출고 헬퍼 함수 시그니처와 누락 함수를 호환한다."""
    from datetime import date, datetime

    import nohtus.pages.outbound as outbound_page

    original_customer_payload = getattr(outbound_page, "_current_customer_payload", None)
    original_manual_pick_rows = getattr(outbound_page, "_manual_pick_rows", None)
    original_last_sale_text = getattr(outbound_page, "_last_sale_text", None)
    original_days_ago_label = getattr(outbound_page, "_days_ago_label", None)

    if original_customer_payload is not None:
        def compatible_current_customer_payload(selected_customer=None):
            return original_customer_payload(selected_customer)

        outbound_page._current_customer_payload = compatible_current_customer_payload

    if original_manual_pick_rows is not None:
        def compatible_manual_pick_rows(pick_df, editor_df=None):
            if editor_df is None:
                if pick_df is None or pick_df.empty:
                    return pick_df
                rows = pick_df.copy()
                rows = rows.rename(columns={
                    "company": "사업장",
                    "product_name": "제품명",
                    "lot": "LOT",
                    "exp_date": "유통기한",
                    "location": "로케이션",
                    "qty": "현재수량",
                })
                if "유통기한" in rows.columns:
                    rows["유통기한"] = rows["유통기한"].apply(outbound_page.display_date_only)
                rows.insert(0, "선택", False)
                rows["요청수량"] = 0
                columns = ["선택", "id", "사업장", "제품명", "LOT", "유통기한", "로케이션", "현재수량", "요청수량"]
                return rows[[c for c in columns if c in rows.columns]]
            return original_manual_pick_rows(pick_df, editor_df)

        outbound_page._manual_pick_rows = compatible_manual_pick_rows

    def compatible_days_ago_label(date_text):
        try:
            target_date = datetime.strptime(str(date_text), "%Y-%m-%d").date()
        except Exception:
            return ""
        days = (date.today() - target_date).days
        if days < 0:
            return "예정"
        if days == 0:
            return "오늘"
        return f"{days}일 전"

    def compatible_last_sale_text(customer_name, company, exact_map, name_map):
        customer = str(customer_name or "").strip()
        company = str(company or "").strip()
        last_date = exact_map.get((customer, company)) or name_map.get(customer) or ""
        if not last_date:
            return "최근거래 없음"
        ago = compatible_days_ago_label(last_date)
        return f"최근거래 {last_date} ({ago})" if ago else f"최근거래 {last_date}"

    outbound_page._days_ago_label = compatible_days_ago_label
    outbound_page._last_sale_text = compatible_last_sale_text

    try:
        return _page_export_waiting()
    finally:
        if original_customer_payload is not None:
            outbound_page._current_customer_payload = original_customer_payload
        if original_manual_pick_rows is not None:
            outbound_page._manual_pick_rows = original_manual_pick_rows

        if original_last_sale_text is None:
            try:
                delattr(outbound_page, "_last_sale_text")
            except AttributeError:
                pass
        else:
            outbound_page._last_sale_text = original_last_sale_text

        if original_days_ago_label is None:
            try:
                delattr(outbound_page, "_days_ago_label")
            except AttributeError:
                pass
        else:
            outbound_page._days_ago_label = original_days_ago_label


def main():
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    init_db()
    apply_style()
    sync_mobile_flag()
    if not require_login():
        return
    if is_mobile():
        page_mobile_stock_finder()
        return

    allowed_pages = allowed_pages_for_current_user()
    menu = render_sidebar(APP_TITLE, VERSION, allowed_pages=allowed_pages)
    render_user_box()
    if not can_access_page(menu):
        st.warning("이 계정은 해당 메뉴에 접근할 수 없습니다.")
        return

    if menu == "로케이션 맵": page_map()
    elif menu == "유통기한 임박": page_expiry_alerts()
    elif menu == "자사제품 조회": page_own_product_status()
    elif menu == "전체 조회": page_all_inventory()
    elif menu == "최근 조회": page_recent_products()
    elif menu == "출고지시": page_outbound()
    elif menu == "저장된 출고지시": page_saved_outbound_refactored()
    elif menu == "수출대기 등록": page_export_waiting()
    elif menu == "저장된 수출대기": page_saved_export_waiting()
    elif menu == "마감": page_closing()
    elif menu == "재고 찾기": page_mobile_stock_finder()
    elif menu == "입고 등록": page_inbound_refactored()
    elif menu == "이동 등록": page_move()
    elif menu == "재고 실사": page_stocktake()
    elif menu == "출고가능 관리":
        if not is_admin():
            st.warning("admin 계정만 접근할 수 있습니다.")
            return
        page_shippable_inventory()
    elif menu == "제품 매칭 관리": page_product_matching()
    elif menu == "거래처 관리": page_customer_master()
    elif menu == "매입가 조회": page_purchase_history()
    elif menu == "이력 조회": page_history()
