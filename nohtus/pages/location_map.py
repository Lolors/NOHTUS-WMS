"""Location map page for NOHTUS WMS.

Migrated from app.py. This module intentionally imports Streamlit because it
contains page rendering code.
"""

from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as components

from nohtus.config import AREA_COLOR, AREA_CONFIG, COMPANIES
from nohtus.db import q
from nohtus.dates import display_date_only
from nohtus.locations import location_picking_key, parse_location
from nohtus.services.products import product_options

# Some UI/map helper functions may still live in app.py until later steps.
# The migration script injects runtime imports inside the moved page as needed.


def page_map():
    from app import page_map_search_results, render_location_map
    from app import render_location_map
    if st.session_state.pop("_scroll_map_top", False):
        components.html("""<script>
        try { window.parent.scrollTo({top:0,left:0,behavior:'auto'}); } catch(e) {}
        try { window.parent.document.documentElement.scrollTop = 0; window.parent.document.body.scrollTop = 0; } catch(e) {}
        </script>""", height=0, scrolling=False)
    st.markdown("""
<style>
/* RC3.3: 로케이션맵 타이틀/도면/상세영역 전체를 살짝 위로 이동 */
div[data-testid="stVerticalBlock"]:has(#wms-top-anchor) {
    margin-top: -15px !important;
}
</style>
<div id='wms-top-anchor'></div>
""", unsafe_allow_html=True)
    forced_search_term = ""
    try:
        qprod = st.session_state.pop("_map_forced_search_term", "") or st.session_state.pop("_pending_map_search_product", "") or st.query_params.get("map_search_product", "")
        if isinstance(qprod, list):
            qprod = qprod[0] if qprod else ""
        forced_search_term = str(qprod or "").strip()
        if forced_search_term:
            st.session_state["map_view_mode"] = "search"
            st.session_state["_last_map_product_search"] = ""
            # 제품 상세에서 표준제품명을 눌러 들어온 검색은 결과만 표시하고 입력칸은 비운다.
            # 위젯 생성 전에만 session_state 값을 정리하므로 widget key 직접 수정 오류가 나지 않는다.
            for _k in ["map_product_search", "map_product_search_forced_blank"]:
                if _k in st.session_state:
                    st.session_state[_k] = ""
            try:
                del st.query_params["map_search_product"]
            except Exception:
                pass
    except Exception:
        forced_search_term = ""
    h1, h2 = st.columns([1.2, 1.8], gap="large")
    with h1:
        st.title("📍로케이션 맵")
    with h2:
        # form을 쓰면 같은 검색어가 남아 있는 상태에서도 Enter/검색 버튼으로 다시 검색결과 화면으로 돌아갈 수 있다.
        with st.form("map_product_search_form", clear_on_submit=False):
            search_col, btn_col = st.columns([8, 1], gap="small")
            with search_col:
                term = st.text_input(
                    "제품명 검색",
                    value="",
                    placeholder="제품명/ERP명/별칭 일부 입력",
                    key="map_product_search_forced_blank" if forced_search_term else "map_product_search",
                )
            with btn_col:
                st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
                search_submitted = st.form_submit_button("검색", use_container_width=True)

    if "map_view_mode" not in st.session_state:
        st.session_state["map_view_mode"] = "search"

    term_clean = forced_search_term or (term or "").strip()
    last_term = st.session_state.get("_last_map_product_search", "")

    # 로케이션 버튼에서 넘어온 경우에는 맵을 보여주되, 검색창 값은 유지한다.
    if st.session_state.get("selected_location_from_search"):
        st.session_state["selected_location"] = st.session_state.pop("selected_location_from_search")
        st.session_state["map_view_mode"] = "map"

    # 검색어가 비면 즉시 기본 로케이션맵으로 복귀한다.
    if not term_clean:
        st.session_state["map_view_mode"] = "search"
    # 검색 버튼/Enter 또는 검색어 변경이 있으면 검색결과 화면으로 돌아간다.
    elif search_submitted or term_clean != last_term:
        st.session_state["map_view_mode"] = "search"

    st.session_state["_last_map_product_search"] = term_clean

    if term_clean and st.session_state.get("map_view_mode") != "map":
        page_map_search_results(term_clean)
    else:
        render_location_map()
