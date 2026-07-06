import streamlit as st

from nohtus.auth import current_username
from nohtus.services.favorites import list_favorites, list_recent_views, remove_favorite


def _open_product_on_map(product_name):
    st.session_state["_map_forced_search_term"] = product_name
    st.session_state["map_view_mode"] = "search"
    st.session_state["page"] = "로케이션 맵"
    st.rerun()


def _render_product_buttons(products, *, removable=False, prefix="shortcut"):
    if not products:
        st.info("표시할 제품이 없습니다.")
        return
    for idx, product_name in enumerate(products):
        c1, c2 = st.columns([8, 2], gap="small")
        with c1:
            if st.button(product_name, key=f"{prefix}_open_{idx}_{product_name}", use_container_width=True):
                _open_product_on_map(product_name)
        with c2:
            if removable:
                if st.button("해제", key=f"{prefix}_remove_{idx}_{product_name}", use_container_width=True):
                    remove_favorite(current_username(), product_name)
                    st.rerun()


def page_favorite_products():
    st.title("즐겨찾는 제품")
    st.caption("제품명을 누르면 로케이션맵에서 바로 검색됩니다.")
    _render_product_buttons(list_favorites(current_username()), removable=True, prefix="fav_page")


def page_recent_products():
    st.title("최근 조회")
    st.caption("최근 로케이션맵에서 조회한 제품입니다. 제품명을 누르면 다시 검색됩니다.")
    _render_product_buttons(list_recent_views(current_username(), limit=10), removable=False, prefix="recent_page")
