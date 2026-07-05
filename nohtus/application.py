from pathlib import Path

import streamlit as st

from styles import apply_style
from nohtus.pages.history import page_history
from nohtus.pages.move import page_move
from nohtus.pages.stocktake import page_stocktake
from nohtus.pages.location_map import page_map
from nohtus.pages.product_matching_runtime import page_product_matching
from nohtus.pages.closing_runtime import page_closing
from nohtus.pages.master import page_customer_master
from nohtus.pages.outbound import page_outbound
from nohtus.pages.inbound import page_inbound as page_inbound_refactored
from nohtus.pages.saved_outbound import page_saved_outbound as page_saved_outbound_refactored
from nohtus.navigation import render_sidebar
from nohtus.db_init import init_db
from nohtus.pages.mobile_stock import page_mobile_stock_finder
from nohtus.locations import location_picking_key

PROJECT_ROOT = Path(__file__).resolve().parents[1]

_location_picking_key = location_picking_key

APP_TITLE = "NOHTUS WMS"

############################################################
# RC3.0 STABLE BASE 개발 원칙
#
# [CORE FREEZE / 절대 수정 금지]
# - 입고도면 클릭 및 입고 위치 연동
# - 로케이션맵 상세보기
# - 로케이션맵 제품명 클릭 -> 제품검색 자동 실행
# - 도면 SVG / 클릭 JS / query parameter 연동
#
# RC2.82는 위 기능이 정상 작동하던 안정 기준입니다.
# 이후 기능 추가는 이 코어를 직접 수정하지 않고,
# CSS/UI/서비스 함수 레이어에서만 확장하는 방식으로 진행합니다.
############################################################
VERSION = "v4.9 RC3.3 UI Stable"
DB_PATH = PROJECT_ROOT / "data" / "nohtus.db"
COMPANIES = ["노투스팜", "노투스", "NOH", "비자료"]
INBOUND_COMPANIES = COMPANIES + ["등록대기"]
SPECIAL_LOCATIONS = ["홍보물랙", "회색 카트", "오른쪽 창고", "사무실(4층)"]

AREA_CONFIG = {
    "A1": {"lines": ["01","02","03","04","05","06"], "levels": ["01","02","03"]},
    "A2": {"lines": ["01","02","03","04","05","06"], "levels": ["01","02","03"]},
    "B1": {"lines": ["01","02","03","04","05","06"], "levels": ["01","02","03"]},
    "B2": {"lines": ["01","02","03","04","05","06"], "levels": ["01","02","03"]},
    "C1": {"lines": ["01","02","03","04","05","06"], "levels": ["01","02","03"]},
    "C2": {"lines": ["01","02","03","04","05","06"], "levels": ["01","02","03"]},
    "D1": {"lines": ["01","02","03","04","05","06"], "levels": ["01","02","03"]},
    "E1": {"lines": ["01","02","03","04","05","06"], "levels": ["01","02","03"]},
    "F1": {"lines": ["01","02","03"], "levels": ["01","02","03"]},
    "G1": {"lines": ["01","02","03"], "levels": ["01","02","03"]},
    "G2": {"lines": [], "levels": []},
    "T1": {"lines": [], "levels": []},
    "T2": {"lines": [], "levels": []},
    "X1": {"lines": ["01","02","03"], "levels": ["01","02","03","04"]},
    "X2": {"lines": [], "levels": []},
    "REC": {"lines": [], "levels": []},
    "Q": {"lines": ["Q1","Q2"], "levels": []},
    "P": {"lines": [], "levels": []},
    "R1": {"lines": [], "levels": []},
    "R2": {"lines": [], "levels": []},
    "N": {"lines": SPECIAL_LOCATIONS, "levels": []},
}

AREA_COLOR = {
    "A1":"yellow", "A2":"yellow", "B1":"yellow", "B2":"yellow", "C1":"yellow",
    "C2":"blue", "D1":"blue",
    "E1":"pink", "Q":"pink",
    "F1":"bidata", "G1":"gray", "G2":"gray", "X1":"gray", "X2":"gray", "N":"gray",
    "REC":"white", "P":"white", "R1":"white", "R2":"white", "T1":"white", "T2":"white"
}

def main():
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    init_db()
    apply_style()
    menu = render_sidebar(APP_TITLE, VERSION)

    if menu == "로케이션 맵": page_map()
    elif menu == "출고지시": page_outbound()
    elif menu == "저장된 출고지시": page_saved_outbound_refactored()
    elif menu == "마감": page_closing()
    elif menu == "재고 찾기": page_mobile_stock_finder()
    elif menu == "입고 등록": page_inbound_refactored()
    elif menu == "이동 등록": page_move()
    elif menu == "재고 실사": page_stocktake()
    elif menu == "제품 매칭 관리": page_product_matching()
    elif menu == "거래처 관리": page_customer_master()
    elif menu == "이력 조회": page_history()
