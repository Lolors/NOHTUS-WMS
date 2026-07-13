"""Inbound page for NOHTUS WMS.

입고 등록 화면을 app.py에서 분리한 페이지 모듈이다.
기존 도면 클릭/위치 연동 코어는 서비스 보조 함수를 재사용한다.
"""

from __future__ import annotations

import streamlit as st

from nohtus.dates import normalize_exp_date
from nohtus.services.inventory import add_inventory
from nohtus.services.products import product_options
from nohtus.services.inbound import (
    ensure_inbound_first_product_mapping,
    inbound_company_options_for,
    normalize_blank,
    product_mapping_name_for,
    product_mapping_names_for,
    strip_company_stock_label,
)
from nohtus.services.inbound_bridge_runtime import _apply_inbound_location_pending, _inbound_js_loc_changed


FIRST_PRODUCT_DRAFT_KEYS = [
    "inbound_new_product_name",
    "inbound_new_erp_name",
    "inbound_new_product_code",
]


def _has_first_product_draft():
    """최초 등록 입력값이 하나라도 남아 있으면 입력 영역을 계속 열어둔다."""
    return any(str(st.session_state.get(k) or "").strip() for k in FIRST_PRODUCT_DRAFT_KEYS)


def _keep_first_product_section_open_if_needed():
    """도면 클릭 후 rerun되어도 최초 등록 체크/입력칸이 접히지 않게 한다."""
    if bool(st.session_state.get("inbound_first_product")) or _has_first_product_draft():
        st.session_state["inbound_first_product"] = True


def _erp_choice_label(value):
    return str(value or "")


def page_inbound():
    from styles import apply_inbound_bridge_style
    from nohtus.ui.location_picker import inbound_location_picker
    from inbound_map import render_inbound_quick_location_map

    _apply_inbound_location_pending()
    _keep_first_product_section_open_if_needed()
    st.title("입고 등록")

    apply_inbound_bridge_style()
    st.text_input(
        "__입고도면선택값",
        key="_inbound_js_loc_buffer",
        label_visibility="collapsed",
        on_change=_inbound_js_loc_changed,
    )
    if st.button("__입고도면적용", key="_inbound_apply_btn"):
        _inbound_js_loc_changed()
        _apply_inbound_location_pending()
        _keep_first_product_section_open_if_needed()
        st.rerun()

    _apply_inbound_location_pending()
    _keep_first_product_section_open_if_needed()

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
            first_product = st.checkbox("최초 등록", key="inbound_first_product")

        # 체크박스가 도면 클릭 rerun 중 잠깐 false로 평가되어도,
        # 이미 입력된 최초 등록 값이 있으면 바로 다시 열린 상태로 유지한다.
        if not first_product and _has_first_product_draft():
            st.session_state["inbound_first_product"] = True
            first_product = True

        products = product_options(inbound_product_term)
        product_list = products["standard_name"].dropna().astype(str).drop_duplicates().tolist() if not products.empty else []

        if first_product:
            st.markdown("##### 최초 제품 등록")
            product = st.text_input("표준제품명", placeholder="WMS 표준제품명", key="inbound_new_product_name").strip()
            first_erp_name = st.text_input(
                "ERP명" if company != "비자료" else "비자료명",
                placeholder="선택한 사업장의 ERP명/비자료명",
                key="inbound_new_erp_name",
            ).strip()
            first_product_code = st.text_input("제품코드", placeholder="노투스팜/NOH ERP 제품코드", key="inbound_new_product_code").strip()
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
            mapping_options = product_mapping_names_for(company, product)
            if len(mapping_options) > 1:
                st.warning("해당 표준제품명에 연결된 ERP명이 여러 개입니다. 입고할 ERP명을 선택하세요.")
                wh = st.selectbox(
                    "입고 ERP명 선택" if company != "비자료" else "입고 비자료명 선택",
                    mapping_options,
                    key=f"inbound_erp_choice_{company}_{product}",
                    format_func=_erp_choice_label,
                )
            elif len(mapping_options) == 1:
                wh = mapping_options[0]
            else:
                wh = product_mapping_name_for(company, product) or product

    with top_right:
        lot = st.text_input("LOT/제조번호", value="", placeholder="미입력 시 '-' 저장", key="inbound_lot")
        exp = st.text_input(
            "유통기한",
            value="",
            placeholder="예) 28/3 → 2028-03-30, 28.3.2 → 2028-03-02 / 미입력 시 '-' 저장",
            key="inbound_exp",
        )

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
                    save_msg.success(f"입고 저장 완료: {company} / {product} / {wh} / {loc} / {qty}EA")
                except Exception as e:
                    save_msg.error(str(e))
