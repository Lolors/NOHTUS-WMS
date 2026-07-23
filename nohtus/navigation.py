import streamlit as st

from nohtus.auth import is_admin


MENU_SECTIONS = [
    (None, ["로케이션 맵", "유통기한 임박", "매입가 조회", "자사제품 조회", "전체 조회"]),
    ("출고", ["출고지시", "저장된 출고지시", "마감"]),
    ("수출", ["수출대기 등록", "저장된 수출대기"]),
    ("재고", ["입고 등록", "이동 등록", "이력 조회", "재고 실사", "출고가능 관리"]),
    ("기초", ["제품 매칭 관리", "거래처 관리"]),
]

HIDDEN_PAGES = {
    "재고 찾기": "RC3.3: 모바일용 재고 찾기 메뉴는 임시 숨김. 기능 함수는 유지한다.",
}

ADMIN_ONLY_PAGES = {"출고가능 관리"}
DEFAULT_PAGE = "로케이션 맵"
_OUTBOUND_WORK_PAGES = {"출고지시", "수출대기 등록"}
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

    def nav_button(label):
        active = st.session_state.get("page") == label
        if st.sidebar.button(label, use_container_width=True, type="primary" if active else "secondary"):
            current_page = st.session_state.get("page")
            if label in _OUTBOUND_WORK_PAGES and current_page != label:
                # 저장된 수출대기에서 수정 진입할 때는 미리 적재한 장바구니를 지우지 않는다.
                is_export_edit = label == "수출대기 등록" and st.session_state.get("export_editing_order_id")
                if not is_export_edit:
                    _reset_outbound_work_state()
                st.session_state["_outbound_screen_mode"] = "export_waiting" if label == "수출대기 등록" else "outbound"
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
