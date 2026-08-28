"""Move page for NOHTUS WMS.

Migrated from app.py. This module intentionally imports Streamlit because it
contains page rendering code.
"""

from __future__ import annotations

import streamlit as st

from nohtus.config import COMPANIES
from nohtus.db import connect, q
from nohtus.dates import display_date_only
from nohtus.locations import parse_location
from nohtus.services.inventory import move_inventory
from nohtus.services.products import product_options

# These UI helpers still live in app.py until later refactor steps.
# The migration script injects compatibility imports dynamically when needed.


def _destination_mapping_column(company):
    return {
        "노투스팜": "erp_nohtuspharm_name",
        "NOH": "erp_noh_name",
        "노투스": "erp_nohtus_name",
        "비자료": "bidata_name",
    }.get(company)


def _save_destination_mapping(company, product, erp_name):
    col = _destination_mapping_column(company)
    product = str(product or "").strip()
    erp_name = str(erp_name or "").strip()
    if not col or not product or not erp_name:
        return
    with connect() as con:
        con.execute(f"UPDATE products SET {col}=? WHERE standard_name=?", (erp_name, product))
        con.commit()


def page_move():
    from nohtus.ui.location_picker import location_picker, render_location_range_grid_picker_button
    from nohtus.services.inbound import product_mapping_name_for
    from nohtus.services.move_bridge_runtime import _apply_move_prefill_pending
    from inbound_map import render_move_quick_location_map

    _apply_move_prefill_pending()
    prefill = st.session_state.get("_move_prefill") or {}
    prefill_token = int(st.session_state.get("_move_prefill_token", 0) or 0)

    st.title("이동 등록")
    st.caption("제품 → 유통기한 → LOT/제조번호를 선택하면 출발 재고가 자동 표시됩니다.")
    if prefill:
        info_col, clear_col = st.columns([5, 1])
        info_col.info(f"로케이션 맵에서 넘어옴: {prefill.get('location')} / {prefill.get('product')}")
        if clear_col.button("선택 해제", key=f"move_prefill_clear_{prefill_token}"):
            st.session_state.pop("_move_prefill", None)
            st.rerun()

    input_col, src_col, dest_col = st.columns([30, 40, 30], gap="large")

    with input_col:
        st.markdown("#### 이동 제품")
        term = st.text_input(
            "제품 검색",
            value=prefill.get("product", ""),
            placeholder="제품명, 전산상 명칭, 별칭 일부 입력",
            key=f"move_term_{prefill_token}",
        )
        opts = product_options(term)
        if opts.empty:
            st.warning("일치하는 제품이 없습니다.")
            return

        product_choices = [""] + opts["standard_name"].tolist()
        default_product = prefill.get("product", "")
        product_index = product_choices.index(default_product) if default_product in product_choices else 0
        product = st.selectbox(
            "추천 제품",
            product_choices,
            index=product_index,
            key=f"move_product_select_{prefill_token}",
            format_func=lambda x: "제품명을 입력하거나 선택하세요" if x == "" else x
        )
        if not product:
            st.info("이동할 제품을 선택하세요.")
            return

        exp_df = q(
            "SELECT DISTINCT exp_date FROM inventory "
            "WHERE product_name=? AND qty>0 ORDER BY exp_date",
            (product,),
        )
        if exp_df.empty:
            st.info("현재 재고가 0이 아닌 유통기한이 없습니다.")
            return

        exp_col, lot_col = st.columns(2)
        with exp_col:
            exp_choices = exp_df["exp_date"].tolist()
            default_exp = prefill.get("exp", "")
            exp_index = exp_choices.index(default_exp) if default_exp in exp_choices else 0
            exp = st.selectbox(
                "유통기한",
                exp_choices,
                index=exp_index,
                format_func=display_date_only,
                key=f"move_exp_{product}_{prefill_token}",
            )

        lot_df = q(
            "SELECT DISTINCT lot FROM inventory "
            "WHERE product_name=? AND exp_date=? AND qty>0 ORDER BY lot",
            (product, exp),
        )
        if lot_df.empty:
            st.info("선택한 유통기한에 재고가 0이 아닌 LOT/제조번호가 없습니다.")
            return
        with lot_col:
            lot_choices = lot_df["lot"].tolist()
            default_lot = prefill.get("lot", "")
            lot_index = lot_choices.index(default_lot) if default_lot in lot_choices else 0
            lot = st.selectbox(
                "LOT/제조번호",
                lot_choices,
                index=lot_index,
                key=f"move_lot_{product}_{exp}_{prefill_token}",
            )

    src_df = q("""SELECT id, company AS 출발사업장, location AS 출발위치, qty AS 현재수량, warehouse_name AS 전산상명칭
                  FROM inventory
                  WHERE product_name=? AND lot=? AND exp_date=? AND qty>0
                  ORDER BY company, location""", (product, lot, exp))

    with src_col:
        st.markdown("#### 출발 재고")
        if src_df.empty:
            st.info("선택한 조건의 출발 재고가 없습니다.")
            return

        if len(src_df) == 1:
            src_id = int(src_df.iloc[0]["id"])
            r = src_df.iloc[0]
            st.info(f"{r['출발사업장']} / {r['출발위치']} / 현재 {int(r['현재수량'])}EA")
        else:
            labels = [f"{r.출발사업장} / {r.출발위치} / {r.현재수량}EA" for r in src_df.itertuples()]
            default_row_index = 0
            prefill_inv_id = prefill.get("inventory_id")
            for i, r in enumerate(src_df.itertuples()):
                if prefill_inv_id and int(r.id) == int(prefill_inv_id):
                    default_row_index = i
                    break
                if r.출발사업장 == prefill.get("company") and r.출발위치 == prefill.get("location"):
                    default_row_index = i
            selected = st.selectbox("출발 재고 선택", labels, index=default_row_index, key=f"move_src_select_{prefill_token}")
            src_id = int(src_df.iloc[labels.index(selected)]["id"])

        src_row = src_df[src_df["id"] == src_id].iloc[0]
        src_company = str(src_row["출발사업장"])
        max_qty = int(src_row["현재수량"])
        st.dataframe(src_df.drop(columns=["id"]), use_container_width=True, hide_index=True)

    with dest_col:
        st.markdown("#### 도착 재고")
        default_idx = COMPANIES.index(src_company) if src_company in COMPANIES else 0
        to_company = st.selectbox("도착 사업장", COMPANIES, index=default_idx, key=f"move_company_{src_id}")
        if to_company != src_company:
            st.warning("정말로 다른 사업장으로 재고를 이동하시겠습니까?")

        dest_mapping_name = product_mapping_name_for(to_company, product)
        dest_mapping_input = ""
        if to_company != src_company and not dest_mapping_name:
            label = "비자료명" if to_company == "비자료" else f"{to_company} ERP명"
            st.warning(f"{product}을 {to_company}로 이동시키기 위해서는 {to_company} ERP에 등록된 해당 제품의 제품명이 필요합니다.")
            dest_mapping_input = st.text_input(label, key=f"move_dest_erp_{src_id}_{to_company}_{product}").strip()

        existing_loc_df = q("""SELECT location, SUM(qty) AS qty
                              FROM inventory
                              WHERE company=? AND product_name=? AND qty>0
                              GROUP BY location
                              ORDER BY qty DESC, location
                              LIMIT 1""", (to_company, product))
        if not existing_loc_df.empty:
            preferred_loc = str(existing_loc_df.iloc[0]["location"] or "").strip()
            preferred_qty = int(existing_loc_df.iloc[0]["qty"] or 0)
            if preferred_loc:
                auto_key = f"{src_id}|{to_company}|{product}|{preferred_loc}"
                if st.session_state.get("_move_auto_loc_key") != auto_key:
                    area, line, level = parse_location(preferred_loc)
                    st.session_state["_move_picker_defaults"] = {"area": area, "line": line, "level": level}
                    st.session_state["_move_picker_token"] = int(st.session_state.get("_move_picker_token", 0) or 0) + 1
                    st.session_state["_move_auto_loc_key"] = auto_key
                st.caption(f"기존 위치 자동 선택: {preferred_loc} ({preferred_qty}EA)")

    st.markdown("---")
    st.markdown("#### 도착 위치 선택")
    st.caption("도면에서 위치를 클릭하면 오른쪽 구역/라인/단이 그 위치로 바뀝니다.")
    move_map_col, move_pos_col = st.columns([7.3, 2.7], gap="large")
    with move_pos_col:
        to_location = location_picker("move", "A1")
        range_end_on = st.checkbox(
            "여러 칸 범위를 통째로 차지",
            key="move_range_end_on",
            help="한 제품이 여러 로케이션 칸을 통째로 차지할 때, 재고는 위 위치 하나로만 관리하면서 로케이션맵에는 범위 전체가 채워진 것으로 표시합니다.",
        )
        to_area, to_line, _to_level = parse_location(to_location)
        if not range_end_on:
            # 체크를 끄면 "범위 없음"으로 완전히 되돌린다. 꺼도 값이 남아있으면
            # 나중에 다시 켰을 때 지금 위치와 상관없는 옛 범위가 그대로
            # 되살아나 마치 "안 지워진다"처럼 보인다.
            st.session_state["_move_range_cells"] = []
            st.session_state.pop("_move_range_cells_area", None)
        elif st.session_state.get("_move_range_cells_area") != to_area:
            # 도착 위치의 구역이 바뀌면 이전 구역 기준 범위는 더 이상 의미가
            # 없으므로 함께 비운다.
            st.session_state["_move_range_cells"] = []
            st.session_state["_move_range_cells_area"] = to_area
        range_cells = st.session_state.get("_move_range_cells") or [] if range_end_on else []
        if range_end_on:
            render_location_range_grid_picker_button("move", to_area, to_line)
            if range_cells:
                clear_col, info_col = st.columns([1, 3])
                with clear_col:
                    if st.button("범위 지우기", key="move_range_end_clear"):
                        st.session_state["_move_range_cells"] = []
                        range_cells = []
                        st.rerun()
                with info_col:
                    st.caption(f"추가로 채워질 칸 ({len(range_cells)}개): " + ", ".join(sorted(range_cells)))
            else:
                st.caption("위 버튼으로 범위를 선택하세요.")
        qty = st.number_input("이동 수량", min_value=1, max_value=max_qty, value=min(1, max_qty), step=1)
        memo = st.text_input("메모", value="")
        st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

        if st.button("이동 저장", type="primary", use_container_width=True):
            try:
                if to_company != src_company and not dest_mapping_name:
                    if not dest_mapping_input:
                        st.error(f"{to_company} ERP명을 입력해야 이동할 수 있습니다.")
                        return
                    _save_destination_mapping(to_company, product, dest_mapping_input)
                move_inventory(src_id, to_company, to_location, int(qty), memo, location_range_cells=range_cells)
                st.session_state["_move_range_cells"] = []
                st.session_state.pop("_move_range_cells_area", None)
                st.session_state.pop("_move_prefill", None)
                st.session_state["_move_toast"] = f"이동 저장 완료: {product} / {qty}EA → {to_company} {to_location}"
                # 이동을 마치면 로케이션 맵에서 결과를 바로 확인할 수 있도록 되돌아간다.
                st.session_state["page"] = "로케이션 맵"
                st.session_state["_scroll_map_top"] = True
                st.rerun()
            except Exception as e:
                st.error(str(e))

    with move_map_col:
        range_locations = ([to_location] + list(range_cells)) if range_end_on else []
        render_move_quick_location_map(range_locations=range_locations)
