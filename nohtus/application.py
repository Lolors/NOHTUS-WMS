import streamlit as st

from styles import apply_style
from nohtus.auth import allowed_pages_for_current_user, can_access_page, render_user_box, require_login
from nohtus.config import APP_TITLE, VERSION
from nohtus.db_init import init_db
from nohtus.device import is_mobile, sync_mobile_flag
from nohtus.navigation import render_sidebar
from nohtus.pages.closing import page_closing
from nohtus.pages.history import page_history
from nohtus.pages.inbound import page_inbound as page_inbound_refactored
from nohtus.pages.location_map import page_map
from nohtus.pages.customer_master_business import page_customer_master
from nohtus.pages.mobile_stock import page_mobile_stock_finder
from nohtus.pages.move import page_move
from nohtus.pages.outbound_business import page_outbound
from nohtus.pages.product_matching_business import page_product_matching
from nohtus.pages.product_shortcuts import page_favorite_products, page_recent_products
from nohtus.pages.saved_outbound_business_v2 import page_saved_outbound as page_saved_outbound_refactored
from nohtus.pages.stocktake_business import page_stocktake


# RC3.0 STABLE BASE 개발 원칙
# [CORE FREEZE / 절대 수정 금지]
# - 입고도면 클릭 및 입고 위치 연동
# - 로케이션맵 상세보기
# - 로케이션맵 제품명 클릭 -> 제품검색 자동 실행
# - 도면 SVG / 클릭 JS / query parameter 연동
#
# RC2.82는 위 기능이 정상 작동하던 안정 기준입니다.
# 이후 기능 추가는 이 코어를 직접 수정하지 않고,
# CSS/UI/서비스 함수 레이어에서만 확장하는 방식으로 진행합니다.


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
    elif menu == "즐겨찾는 제품":
        page_favorite_products()
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
    elif menu == "제품 매칭 관리":
        page_product_matching()
    elif menu == "거래처 관리":
        page_customer_master()
    elif menu == "이력 조회":
        page_history()
