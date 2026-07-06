import streamlit as st

import nohtus.pages.location_map as location_map_page
from nohtus.auth import current_username
from nohtus.services.favorites import is_favorite, record_recent_view, toggle_favorite
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


def _render_favorite_toggle_for_current_search():
    username = current_username()
    term = st.session_state.get("_last_map_product_search", "")
    product_name = _favorite_target_from_search_term(term)
    if not username or not product_name:
        return
    record_recent_view(username, product_name)
    added = is_favorite(username, product_name)
    label = "⭐즐겨찾기 추가됨" if added else "⭐즐겨찾기"
    c1, c2 = st.columns([8, 2])
    with c2:
        if st.button(label, key=f"toggle_fav_{username}_{product_name}", use_container_width=True):
            toggle_favorite(username, product_name)
            st.rerun()


def page_map():
    location_map_page.page_map()
    _render_favorite_toggle_for_current_search()
