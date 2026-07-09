import streamlit as st

from styles import apply_style
from nohtus.auth import allowed_pages_for_current_user, can_access_page, is_admin, render_user_box, require_login
from nohtus.config import APP_TITLE, VERSION
from nohtus.db_init import init_db
from nohtus.device import is_mobile, sync_mobile_flag
from nohtus.navigation import render_sidebar
from nohtus.pages.all_inventory import page_all_inventory
from nohtus.pages.closing_business import page_closing
from nohtus.pages.expiry_alerts import page_expiry_alerts
from nohtus.pages.history_business import page_history
from nohtus.pages.inbound import page_inbound as page_inbound_refactored
from nohtus.pages.location_map_business import page_map
from nohtus.pages.customer_master_business import page_customer_master
from nohtus.pages.mobile_stock import page_mobile_stock_finder
from nohtus.pages.move import page_move
from nohtus.pages.outbound_business import page_outbound
from nohtus.pages.own_product_status import page_own_product_status
from nohtus.pages.product_matching_business import page_product_matching
from nohtus.pages.product_shortcuts import page_recent_products
from nohtus.pages.saved_outbound_business_v4 import page_saved_outbound as page_saved_outbound_refactored
from nohtus.pages.shippable_inventory import page_shippable_inventory
from nohtus.pages.stocktake_business import page_stocktake
from nohtus.services.kakao_order_parser import parse_kakao_order


def _render_route_kakao_order_helper():
    st.markdown("### 카톡 주문 자동 출고지시")
    with st.container(border=True):
        st.caption("카카오톡 주문내용을 붙여넣고 해석하면 출고지시의 매출처/제품/수량 검색값을 자동으로 채웁니다.")
        raw_text = st.text_area(
            "카카오톡 주문내용",
            placeholder="한양재활\n콘쥬란 4통\n리쥬비넥스 10통\n\n부탁드려요",
            height=120,
            key="route_kakao_order_text",
        )
        if st.button("카톡 주문 해석", type="primary", use_container_width=True, key="route_kakao_order_parse_btn"):
            parsed = parse_kakao_order(raw_text)
            st.session_state["route_kakao_order_parsed"] = {
                "customer_keyword": parsed.customer_keyword,
                "items": [item.__dict__ for item in parsed.items],
                "note": parsed.note,
            }

        parsed_data = st.session_state.get("route_kakao_order_parsed") or {}
        if not parsed_data:
            return

        customer_keyword = str(parsed_data.get("customer_keyword") or "").strip()
        items = parsed_data.get("items") or []
        note = str(parsed_data.get("note") or "").strip()

        if customer_keyword:
            st.success(f"매출처 키워드: {customer_keyword}")
        else:
            st.warning("매출처 키워드를 찾지 못했습니다. 첫 줄에 매출처명을 넣으면 더 정확합니다.")

        if not items:
            st.warning("품목과 수량을 찾지 못했습니다. 예: 콘쥬란 4통")
        else:
            for idx, item in enumerate(items):
                product = str(item.get("product_keyword") or "").strip()
                qty = int(item.get("qty") or 1)
                unit = str(item.get("unit") or "").strip()
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.write(f"{idx + 1}. {product} / {qty}{unit}")
                with col2:
                    if st.button("불러오기", use_container_width=True, key=f"route_kakao_load_item_{idx}"):
                        if customer_keyword:
                            st.session_state["out_customer_term"] = customer_keyword
                            st.session_state["out_customer_direct"] = False
                            st.session_state.pop("_out_customer_label", None)
                        st.session_state["out_product_term"] = product
                        st.session_state["out_req_qty"] = qty
                        st.session_state.pop("out_rec_editor", None)
                        st.session_state.pop("out_manual_editor", None)
                        st.session_state["_outbound_last_success"] = "카톡 주문에서 추출한 매출처/제품/수량을 입력칸에 반영했습니다."
                        st.rerun()

        if note:
            st.caption(f"메모로 인식한 내용: {note}")


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
        _render_route_kakao_order_helper()
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
    elif menu == "이력 조회":
        page_history()
