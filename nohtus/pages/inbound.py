"""Inbound page for NOHTUS WMS.

입고 등록 화면을 app.py에서 분리한 페이지 모듈이다.
기존 도면 클릭/위치 연동 코어는 서비스 보조 함수를 재사용한다.
"""

from __future__ import annotations

import streamlit as st

from nohtus.dates import normalize_exp_date
from nohtus.services.inventory import add_inventory
from nohtus.services.products import product_options
from nohtus.services.inbound import ensure_inbound_first_product_mapping, inbound_company_options_for, normalize_blank, product_mapping_name_for, strip_company_stock_label
from nohtus.services.inbound_bridge_runtime import _apply_inbound_location_pending, _inbound_js_loc_changed


_FIRST_INBOUND_SHADOW_MAP = {
    "inbound_first_product": "_keep_inbound_first_product",
    "inbound_new_product_name": "_keep_inbound_new_product_name",
    "inbound_new_erp_name": "_keep_inbound_new_erp_name",
    "inbound_new_product_code": "_keep_inbound_new_product_code",
}


def _restore_first_inbound_widgets_before_render():
    """도면 클릭/쿼리 이동 뒤에도 최초등록 체크와 입력창이 사라지지 않게 한다."""
    if st.session_state.get("_keep_inbound_first_product") is True:
        st.session_state["inbound_first_product"] = True
    for widget_key, keep_key in _FIRST_INBOUND_SHADOW_MAP.items():
        if widget_key == "inbound_first_product":
            continue
        keep_value = st.session_state.get(keep_key)
        if keep_value not in [None, ""] and st.session_state.get(widget_key, "") in [None, ""]:
            st.session_state[widget_key] = keep_value


def _remember_first_inbound_widgets():
    for widget_key, keep_key in _FIRST_INBOUND_SHADOW_MAP.items():
        st.session_state[keep_key] = st.session_state.get(widget_key)


def page_inbound():
    from styles import apply_inbound_bridge_style
    from nohtus.ui.location_picker import inbound_location_picker
    from inbound_map import render_inbound_quick_location_map

    _restore_first_inbound_widgets_before_render()
    _apply_inbound_location_pending()
    _restore_first_inbound_widgets_before_render()

    st.title("입고 등록")

    apply_inbound_bridge_style()
    st.text_input(
        "__입고도면선택값",
        key="_inbound_js_loc_buffer",
        label_visibility="collapsed",
        on_change=_inbound_js_loc_changed,
    )
    if st.button("__입고도면적용", key="_inbound_apply_btn"):
        _remember_first_inbound_widgets()
        _inbound_js_loc_changed()
        _apply_inbound_location_pending()
        _restore_first_inbound_widgets_before_render()
        st.rerun()

    _apply_inbound_location_pending()
    _restore_first_inbound_widgets_before_render()

    def inbound_product_label(value):
        if value == "":
            return "제품명을 입력하거나 선택하세요"
        return str(value)

    top_left, top_right = st.columns(2, gap="large")
    with top_left:
        in_src_col, in_company_col = st.columns(2, gap="small")
        with in_src_col:
            inbound_source = st.text_input("매입처", value="", placeholder="예: 거래처명/수입처", key="inbound_source")
        with in_company_col:
            _inbound_selected_product_for_stock = st.session_state.get("inbound_product", "")
            company_label = st.selectbox("사업장", inbound_company_options_for(_inbound_selected_product_for_stock), key="inbound_company")
            company = strip_company_stock_label(company_label)

        search_col, first_col = st.columns([8, 2], gap="small")
        with search_col:
            inbound_product_term = st.text_input("제품 검색", placeholder="제품명, ERP명, 비자료명, 별칭 일부 입력", key="inbound_product_term")
        with first_col:
            st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
            first_product = st.checkbox("최초 등록", key="inbound_first_product", on_change=_remember_first_inbound_widgets)

        if first_product:
            st.session_state["_keep_inbound_first_product"] = True
        else:
            st.session_state["_keep_inbound_first_product"] = False

        products = product_options(inbound_product_term)
        product_list = products["standard_name"].dropna().astype(str).drop_duplicates().tolist() if not products.empty else []

        if first_product:
            st.markdown("##### 최초 제품 등록")
            product = st.text_input(
                "표준제품명",
                value=st.session_state.get("_keep_inbound_new_product_name", ""),
                placeholder="WMS 표준제품명",
                key="inbound_new_product_name",
                on_change=_remember_first_inbound_widgets,
            ).strip()
            first_erp_name = st.text_input(
                "ERP명" if company != "비자료" else "비자료명",
                value=st.session_state.get("_keep_inbound_new_erp_name", ""),
                placeholder="선택한 사업장의 ERP명/비자료명",
                key="inbound_new_erp_name",
                on_change=_remember_first_inbound_widgets,
            ).strip()
            first_product_code = st.text_input(
                "제품코드",
                value=st.session_state.get("_keep_inbound_new_product_code", ""),
                placeholder="노투스팜/NOH ERP 제품코드",
                key="inbound_new_product_code",
                on_change=_remember_first_inbound_widgets,
            ).strip()
            _remember_first_inbound_widgets()
            wh = first_erp_name or product
        else:
            selected_product = st.selectbox(
                "제품",
                [""] + product_list,
                index=0,
                key="inbound_product",
                format_func=inbound_product_label,
            )
            product = selected_product
            first_erp_name = ""
            first_product_code = ""
            wh = product_mapping_name_for(company, product) or product

    with top_right:
        lot = st.text_input("LOT/제조번호", value="", placeholder="미입력 시 '-' 저장", key="inbound_lot")
        exp = st.text_input("유통기한", value="", placeholder="예: 28/3/2, 28.3.2, 2028-03-02 / 미입력 시 '-' 저장", key="inbound_exp")

    st.markdown("---")
    map_col, pos_col = st.columns([7.3, 2.7], gap="large")
    with map_col:
        render_inbound_quick_location_map()
    with pos_col:
        st.markdown("#### 입고 위치")
        loc = inbound_location_picker("REC")
        qty = st.number_input("수량", min_value=1, step=1, key="inbound_qty")
        memo = st.text_input("메모", value="", key="inbound_memo")
        st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
        _save_left, save_col, _save_right = st.columns([1, 2, 1])
        with save_col:
            save_clicked = st.button("입고 저장", type="primary", use_container_width=True)
        st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
        save_msg = st.empty()
        if save_clicked:
            if not product:
                save_msg.error("제품을 선택하거나 표준제품명을 입력하세요.")
            else:
                try:
                    if first_product:
                        product, wh = ensure_inbound_first_product_mapping(product, company, first_erp_name, first_product_code)
                    memo_parts = []
                    if inbound_source:
                        memo_parts.append(f"매입처: {inbound_source}")
                    if memo:
                        memo_parts.append(memo)
                    inbound_memo = " / ".join(memo_parts) if memo_parts else "입고 등록"
                    add_inventory(company, product, wh, normalize_blank(lot), normalize_exp_date(exp), loc, int(qty), inbound_memo)
                    for key in _FIRST_INBOUND_SHADOW_MAP.values():
                        st.session_state.pop(key, None)
                    save_msg.success(f"입고 저장 완료: {company} / {product} / {loc} / {qty}EA")
                except Exception as e:
                    save_msg.error(str(e))
