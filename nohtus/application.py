import streamlit as st

from styles import apply_style
from nohtus.auth import allowed_pages_for_current_user, can_access_page, is_admin, render_user_box, require_login
from nohtus.config import APP_TITLE, VERSION
from nohtus.db_init import init_db
from nohtus.device import is_mobile, sync_mobile_flag
from nohtus.navigation import render_sidebar
from nohtus.pages.all_inventory import page_all_inventory
from nohtus.pages.closing_date_fix import page_closing
from nohtus.pages.expiry_alerts import page_expiry_alerts
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
from nohtus.pages.purchase_history import page_purchase_history
from nohtus.pages.saved_outbound_date_fix import page_saved_outbound as page_saved_outbound_refactored
from nohtus.pages.shippable_inventory import page_shippable_inventory
from nohtus.pages.stocktake_business import page_stocktake


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

    if menu == "로케이션 맵":
        page_map()
    elif menu == "유통기한 임박":
        page_expiry_alerts()
    elif menu == "자사제품 조회":
        page_own_product_status()
    elif menu == "전체 조회":
        page_all_inventory()
    elif menu == "최근 조회":
        page_recent_products()
    elif menu == "출고지시":
        page_outbound()
    elif menu == "저장된 출고지시":
        page_saved_outbound_refactored()
    elif menu == "마감":
        page_closing()
    elif menu == "재고 찾기":
        page_mobile_stock_finder()
    elif menu == "입고 등록":
        page_inbound_refactored()
    elif menu == "이동 등록":
        page_move()
    elif menu == "재고 실사":
        page_stocktake()
    elif menu == "출고가능 관리":
        if not is_admin():
            st.warning("admin 계정만 접근할 수 있습니다.")
            return
        page_shippable_inventory()
    elif menu == "제품 매칭 관리":
        page_product_matching()
    elif menu == "거래처 관리":
        page_customer_master()
    elif menu == "매입가 조회":
        page_purchase_history()
    elif menu == "이력 조회":
        page_history()
