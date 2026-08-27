"""Inbound page for NOHTUS WMS.

입고 등록 화면을 app.py에서 분리한 페이지 모듈이다.
기존 도면 클릭/위치 연동 코어는 서비스 보조 함수를 재사용한다.
"""

from __future__ import annotations

from datetime import date, datetime

import streamlit as st

from nohtus.config import AREA_CONFIG
from nohtus.locations import expand_location_block, make_location, parse_location
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
from nohtus.services.inbound_bridge_runtime import _apply_inbound_location_pending
from nohtus.db import connect


FIRST_PRODUCT_DRAFT_KEYS = [
    "inbound_new_product_name",
    "inbound_new_erp_name",
    "inbound_new_product_code",
]


def _on_first_product_toggle():
    """체크 해제 시 표준제품명/ERP명/제품코드 입력값도 함께 지운다.

    이 콜백 없이는 체크를 해제해도 남아있는 입력값 때문에 다음 렌더에서
    다시 체크된 것처럼 보이는 문제가 있었다(입력값이 남아있으면 계속 열어두는
    로직이 해제 자체를 무시했기 때문).
    """
    if not st.session_state.get("inbound_first_product"):
        for key in FIRST_PRODUCT_DRAFT_KEYS:
            st.session_state.pop(key, None)


def _erp_choice_label(value):
    return str(value or "")


def _sync_inbound_company_option(options):
    """제품 변경으로 재고수량 라벨이 바뀌어도 기존 사업장 선택을 유지한다."""
    if not options:
        return
    current_label = st.session_state.get("inbound_company", "")
    current_company = strip_company_stock_label(current_label)
    matching_label = next(
        (option for option in options if strip_company_stock_label(option) == current_company),
        None,
    )
    if matching_label:
        st.session_state["inbound_company"] = matching_label


def _apply_selected_inbound_date(*, company, product, warehouse, lot, exp, location, qty, memo, inbound_date):
    """방금 저장한 입고 이력의 날짜를 사용자가 지정한 입고일자로 바꾼다.

    재고의 실제 수정 시각은 유지하고, 이력조회에 표시되는 transactions.created_at만
    선택한 입고일자와 현재 시각 조합으로 기록한다.
    """
    selected_at = datetime.combine(inbound_date, datetime.now().time()).strftime("%Y-%m-%d %H:%M:%S")
    with connect() as con:
        row = con.execute(
            """
            SELECT id
            FROM transactions
            WHERE tx_type='입고'
              AND product_name=?
              AND IFNULL(warehouse_name,'')=?
              AND IFNULL(lot,'-')=?
              AND IFNULL(exp_date,'-')=?
              AND IFNULL(to_company,'')=?
              AND IFNULL(to_location,'')=?
              AND qty=?
              AND IFNULL(memo,'')=?
            ORDER BY id DESC
            LIMIT 1
            """,
            (
                product,
                warehouse or "",
                lot,
                exp,
                company,
                location,
                int(qty),
                memo,
            ),
        ).fetchone()
        if row:
            con.execute("UPDATE transactions SET created_at=? WHERE id=?", (selected_at, int(row[0])))
            con.commit()


def page_inbound():
    from nohtus.ui.location_picker import inbound_location_picker, render_location_range_grid_picker_button
    from inbound_map import render_inbound_quick_location_map

    _apply_inbound_location_pending()
    st.title("입고 등록")

    inbound_date = st.date_input(
        "입고일자",
        value=date.today(),
        key="inbound_date",
        help="선택한 날짜가 이력조회 입고 기록일로 저장됩니다.",
    )

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
            company_options = inbound_company_options_for(_inbound_selected_product_for_stock)
            _sync_inbound_company_option(company_options)
            company_label = st.selectbox("사업장", company_options, key="inbound_company")
            company = strip_company_stock_label(company_label)

        search_col, first_col = st.columns([8, 2], gap="small")
        with search_col:
            inbound_product_term = st.text_input("제품 검색", placeholder="제품명, ERP명, 비자료명, 별칭 일부 입력", key="inbound_product_term")
        with first_col:
            st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
            first_product = st.checkbox(
                "최초 등록",
                key="inbound_first_product",
                on_change=_on_first_product_toggle,
            )

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
    with pos_col:
        st.markdown("#### 입고 위치")
        loc = inbound_location_picker("REC")
        range_end_on = st.checkbox(
            "여러 칸 범위를 통째로 차지",
            key="inbound_range_end_on",
            help="한 제품이 여러 로케이션 칸을 통째로 차지할 때, 재고는 위 위치 하나로만 관리하면서 로케이션맵에는 범위 전체가 채워진 것으로 표시합니다.",
        )
        range_end_raw = st.session_state.get("_inbound_range_end_loc", "")
        range_end_loc = ""
        pick_target = "start"
        if range_end_on:
            render_location_range_grid_picker_button("inbound", parse_location(loc)[0])
            pick_label = st.radio(
                "도면 클릭 시 지정할 위치",
                ["시작 위치", "끝 위치"],
                horizontal=True,
                key="inbound_range_pick_target",
            )
            pick_target = "end" if pick_label == "끝 위치" else "start"
            if range_end_raw:
                clear_col, info_col = st.columns([1, 3])
                with clear_col:
                    if st.button("끝 위치 지우기", key="inbound_range_end_clear"):
                        st.session_state["_inbound_range_end_loc"] = ""
                        range_end_raw = ""
                        st.rerun()
                with info_col:
                    st.caption(f"끝 위치(도면 클릭): {range_end_raw}")
                # 도면은 구역/라인 단위로만 클릭이 가능하고 칸(단)까지는 구분되지
                # 않으므로, 끝 위치의 단은 별도 선택으로 정확히 지정한다.
                end_area, end_line, end_level = parse_location(range_end_raw)
                end_levels = list(AREA_CONFIG.get(end_area, {}).get("levels") or [])
                if end_area != parse_location(loc)[0]:
                    st.warning("끝 위치가 시작 위치와 같은 구역이 아닙니다. 도면에서 같은 구역 안의 칸을 클릭하세요.")
                elif end_levels:
                    end_level = st.selectbox(
                        "끝 단",
                        end_levels,
                        index=end_levels.index(end_level) if end_level in end_levels else 0,
                        key="inbound_range_end_level",
                    )
                    range_end_loc = make_location(end_area, end_line, end_level)
                else:
                    range_end_loc = range_end_raw
            else:
                st.caption("도면에서 범위의 끝 칸을 클릭하세요.")
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
                    normalized_lot = normalize_blank(lot)
                    normalized_exp = normalize_exp_date(exp)
                    add_inventory(company, product, wh, normalized_lot, normalized_exp, loc, int(qty), inbound_memo,
                                 location_range_end=range_end_loc)
                    _apply_selected_inbound_date(
                        company=company,
                        product=product,
                        warehouse=wh,
                        lot=normalized_lot,
                        exp=normalized_exp,
                        location=loc,
                        qty=int(qty),
                        memo=inbound_memo,
                        inbound_date=inbound_date,
                    )
                    save_msg.success(f"입고 저장 완료: {inbound_date.strftime('%Y-%m-%d')} / {company} / {product} / {wh} / {loc} / {qty}EA")
                    st.session_state["_inbound_range_end_loc"] = ""
                except Exception as e:
                    save_msg.error(str(e))

    with map_col:
        range_locations = expand_location_block(loc, range_end_loc) if range_end_on else []
        render_inbound_quick_location_map(pick_target=pick_target, range_locations=range_locations)
