import streamlit as st

import nohtus.pages.location_map as location_map_page
from nohtus.auth import current_username
from nohtus.services.favorites import is_favorite, list_favorites, toggle_favorite
from nohtus.services.products import product_options


def _favorite_target_from_search_term(term):
    term = str(term or "").strip()
    if not term:
        return ""
    opts = product_options(term)
    if opts.empty:
        return ""
    names = opts["standard_name"].dropna().astype(str).drop_duplicates().tolist()
    if len(names) == 1:
        return names[0]
    exact = [name for name in names if name.strip().lower() == term.lower()]
    return exact[0] if len(exact) == 1 else ""


def _render_favorite_panel():
    username = current_username()
    with st.expander("즐겨찾는 제품", expanded=False):
        favorites = list_favorites(username)
        if not favorites:
            st.caption("아직 즐겨찾는 제품이 없습니다. 제품 검색 결과에서 ⭐즐겨찾기를 눌러 추가하세요.")
            return
        for product_name in favorites:
            if st.button(product_name, key=f"fav_search_{username}_{product_name}", use_container_width=True):
                st.session_state["_map_forced_search_term"] = product_name
                st.session_state["map_view_mode"] = "search"
                st.rerun()


def _render_favorite_toggle_for_current_search():
    username = current_username()
    term = st.session_state.get("_last_map_product_search", "")
    product_name = _favorite_target_from_search_term(term)
    if not username or not product_name:
        return
    added = is_favorite(username, product_name)
    label = "⭐즐겨찾기 추가됨" if added else "⭐즐겨찾기"
    c1, c2 = st.columns([8, 2])
    with c2:
        if st.button(label, key=f"toggle_fav_{username}_{product_name}", use_container_width=True):
            toggle_favorite(username, product_name)
            st.rerun()


def page_map():
    _render_favorite_panel()
    location_map_page.page_map()
    _render_favorite_toggle_for_current_search()
