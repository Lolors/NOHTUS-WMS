import streamlit as st


MENU_SECTIONS = [
    (None, ["로케이션 맵", "즐겨찾는 제품", "최근 조회"]),
    ("출고", ["출고지시", "저장된 출고지시", "마감"]),
    ("재고", ["입고 등록", "이동 등록", "이력 조회", "재고 실사"]),
    ("기초", ["제품 매칭 관리", "거래처 관리"]),
]

HIDDEN_PAGES = {
    "재고 찾기": "RC3.3: 모바일용 재고 찾기 메뉴는 임시 숨김. 기능 함수는 유지한다.",
}

DEFAULT_PAGE = "로케이션 맵"


def apply_query_page_redirects():
    try:
        if st.query_params.get("map_search_product", ""):
            st.session_state["page"] = "로케이션 맵"
        elif st.query_params.get("inbound_loc", ""):
            st.session_state["page"] = "입고 등록"
    except Exception:
        pass


def render_sidebar(app_title, version, allowed_pages=None):
    st.sidebar.markdown(f"# {app_title}")
    st.sidebar.caption(version)

    if "page" not in st.session_state:
        st.session_state["page"] = DEFAULT_PAGE

    apply_query_page_redirects()

    def is_allowed(label):
        return allowed_pages is None or label in allowed_pages

    if not is_allowed(st.session_state.get("page", DEFAULT_PAGE)):
        st.session_state["page"] = DEFAULT_PAGE

    def nav_button(label):
        active = st.session_state.get("page") == label
        if st.sidebar.button(label, use_container_width=True, type="primary" if active else "secondary"):
            st.session_state["page"] = label
            if label == "로케이션 맵":
                st.session_state["_scroll_map_top"] = True
            st.rerun()

    for section, labels in MENU_SECTIONS:
        visible_labels = [label for label in labels if label not in HIDDEN_PAGES and is_allowed(label)]
        if not visible_labels:
            continue
        if section:
            st.sidebar.markdown(f"### {section}")
        for label in visible_labels:
            nav_button(label)

    return st.session_state["page"]
