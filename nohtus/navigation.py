import streamlit as st

from nohtus.auth import is_admin


MENU_SECTIONS = [
    (None, ["로케이션 맵", "유통기한 임박", "매입가 조회", "자사제품 조회", "전체 조회", "수출 현황"]),
    ("출고", ["출고지시", "저장된 출고지시", "마감"]),
    ("재고", ["입고 등록", "이동 등록", "이력 조회", "재고 실사"]),
    ("수출", [
        "주문 입력",
        "주문 검색 및 수정",
        "수출대기 저장",
        "박스 패킹",
        "수출확정 매출 등록",
        "국내배송",
        "공유용 자료",
        "기간별 통계",
        "내 폴더",
    ]),
    ("기초", ["제품 매칭 관리", "부자재 관리", "거래처 관리", "로케이션맵 편집"]),
]

# The export section is collapsed by default and rendered only when explicitly
# expanded.  Keeping this in Python state avoids brittle CSS selectors that can
# change between Streamlit releases.
_COLLAPSIBLE_SECTION = "수출"
_EXPORT_SUBMENU_EXPANDED_KEY = "export_submenu_expanded"

HIDDEN_PAGES = {
    "재고 찾기": "RC3.3: 모바일용 재고 찾기 메뉴는 임시 숨김. 기능 함수는 유지한다.",
}

ADMIN_ONLY_PAGES = {"로케이션맵 편집"}
DEFAULT_PAGE = "로케이션 맵"
_OUTBOUND_WORK_PAGES = {"출고지시"}
_OUTBOUND_STATE_KEYS = [
    "outbound_cart", "outbound_order_date", "out_customer_term", "out_customer_select",
    "_out_customer_label", "out_selected_customer", "out_customer_direct",
    "out_customer_manual_name", "out_product_term", "out_req_qty", "out_rec_editor",
    "out_manual_editor", "out_ignore_company", "out_manual_pick", "out_all_company_manual_pick",
    "out_expiry_short_first", "pending_outbound_save", "pending_outbound_expiry_warnings",
    "pending_outbound_add_rows", "pending_outbound_add_warnings", "editing_order_id",
    "editing_order_title",
]


def _is_admin_only_allowed(label):
    return label not in ADMIN_ONLY_PAGES or is_admin()


def _reset_outbound_work_state():
    for key in _OUTBOUND_STATE_KEYS:
        st.session_state.pop(key, None)
    st.session_state["outbound_cart"] = []
    st.session_state["out_cart_editor_token"] = int(st.session_state.get("out_cart_editor_token", 0) or 0) + 1
    st.session_state["_outbound_reset_inputs_pending"] = True


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
        role_allowed = allowed_pages is None or label in allowed_pages or (is_admin() and label in ADMIN_ONLY_PAGES)
        return role_allowed and _is_admin_only_allowed(label)

    if not is_allowed(st.session_state.get("page", DEFAULT_PAGE)):
        st.session_state["page"] = DEFAULT_PAGE

    def _go_to(label):
        current_page = st.session_state.get("page")
        if label in _OUTBOUND_WORK_PAGES and current_page != label:
            _reset_outbound_work_state()
            st.session_state["_outbound_screen_mode"] = "outbound"
        st.session_state["page"] = label
        if label == "로케이션 맵":
            st.session_state["_scroll_map_top"] = True
        st.rerun()

    def nav_button(label):
        active = st.session_state.get("page") == label
        if st.sidebar.button(label, use_container_width=True, type="primary" if active else "secondary"):
            _go_to(label)

    def submenu_button(label):
        active = st.session_state.get("page") == label
        if st.button(
            label,
            use_container_width=True,
            type="primary" if active else "secondary",
            key=f"export_submenu_btn_{label}",
        ):
            _go_to(label)

    def render_collapsible_section(section, labels):
        expanded = bool(st.session_state.get(_EXPORT_SUBMENU_EXPANDED_KEY, False))
        with st.sidebar.container():
            header_col, toggle_col = st.columns([2, 1])
            header_col.markdown(f"### {section}")
            if not expanded and toggle_col.button(
                "펼치기", key="export_submenu_expand", use_container_width=True
            ):
                st.session_state[_EXPORT_SUBMENU_EXPANDED_KEY] = True
                st.rerun()
            if not expanded:
                return
            for label in labels:
                submenu_button(label)
            if st.button("수출 메뉴 접기", key="export_submenu_collapse", use_container_width=True):
                st.session_state[_EXPORT_SUBMENU_EXPANDED_KEY] = False
                st.rerun()

    for section, labels in MENU_SECTIONS:
        visible_labels = [label for label in labels if label not in HIDDEN_PAGES and is_allowed(label)]
        if not visible_labels:
            continue
        if section == _COLLAPSIBLE_SECTION:
            render_collapsible_section(section, visible_labels)
            continue
        if section:
            st.sidebar.markdown(f"### {section}")
        for label in visible_labels:
            nav_button(label)
    return st.session_state["page"]
