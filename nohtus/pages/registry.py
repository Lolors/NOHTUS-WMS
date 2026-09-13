"""사이드바 메뉴 이름 → 페이지 렌더 함수 매핑.

nohtus.application.main()의 라우팅(원래는 21개의 개별 import + if/elif
32줄)을 여기 한곳에 모았다. 새 메뉴를 추가할 땐 이 파일에 함수를 import하고
PAGE_REGISTRY에 한 줄 추가하면 된다.
"""

from __future__ import annotations

import streamlit as st

from nohtus.auth import is_admin
from nohtus.pages.all_inventory import page_all_inventory
from nohtus.pages.closing_print import page_closing
from nohtus.pages.customer_master_business import page_customer_master
from nohtus.pages.expiry_alerts import page_expiry_alerts
from nohtus.pages.export_app_pages import (
    page_export_dashboard,
    page_export_domestic_delivery,
    page_export_my_folder,
    page_export_order_entry,
    page_export_order_search,
    page_export_packing,
    page_export_shared_documents,
    page_export_shipment_intake,
    page_export_sales_registration,
    page_export_statistics,
)
from nohtus.pages.history import page_history
from nohtus.pages.inbound import page_inbound as page_inbound_refactored
from nohtus.pages.location_map_business import page_map
from nohtus.pages.location_map_editor import page_location_map_editor
from nohtus.pages.material_management import page_material_management
from nohtus.pages.mobile_stock_business import page_mobile_stock_finder
from nohtus.pages.move import page_move
from nohtus.pages.outbound_entry import page_outbound
from nohtus.pages.own_product_status import page_own_product_status
from nohtus.pages.product_matching_business import page_product_matching
from nohtus.pages.product_shortcuts import page_recent_products
from nohtus.pages.purchase_history_single import page_purchase_history
from nohtus.pages.saved_outbound_date_fix import page_saved_outbound as page_saved_outbound_refactored
from nohtus.pages.stocktake_business import page_stocktake


def _page_location_map_editor_guarded():
    if not is_admin():
        st.warning("admin 계정만 접근할 수 있습니다.")
        return
    page_location_map_editor()


PAGE_REGISTRY = {
    "로케이션 맵": page_map,
    "유통기한 임박": page_expiry_alerts,
    "자사제품 조회": page_own_product_status,
    "전체 조회": page_all_inventory,
    "최근 조회": page_recent_products,
    "출고지시": page_outbound,
    "저장된 출고지시": page_saved_outbound_refactored,
    "마감": page_closing,
    "재고 찾기": page_mobile_stock_finder,
    "입고 등록": page_inbound_refactored,
    "이동 등록": page_move,
    "재고 실사": page_stocktake,
    "로케이션맵 편집": _page_location_map_editor_guarded,
    "제품 매칭 관리": page_product_matching,
    "부자재 관리": page_material_management,
    "거래처 관리": page_customer_master,
    "매입가 조회": page_purchase_history,
    "이력 조회": page_history,
    "수출 현황": page_export_dashboard,
    "주문 입력": page_export_order_entry,
    "주문 검색 및 수정": page_export_order_search,
    "수출대기 저장": page_export_shipment_intake,
    "수출확정 매출 등록": page_export_sales_registration,
    "박스 패킹": page_export_packing,
    "국내배송": page_export_domestic_delivery,
    "공유용 자료": page_export_shared_documents,
    "기간별 통계": page_export_statistics,
    "내 폴더": page_export_my_folder,
}
