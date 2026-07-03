"""Move page for NOHTUS WMS.

Migrated from app.py. This module intentionally imports Streamlit because it
contains page rendering code.
"""

from __future__ import annotations

import streamlit as st

from nohtus.config import COMPANIES
from nohtus.db import q
from nohtus.dates import display_date_only
from nohtus.locations import parse_location
from nohtus.services.inventory import move_inventory
from nohtus.services.products import product_options

# These UI helpers still live in app.py until later refactor steps.
# The migration script injects compatibility imports dynamically when needed.


def page_move():
    from app import location_picker, product_mapping_name_for
    st.title("이동 등록")
    st.caption("제품 → LOT/유통기한을 선택하면 출발 재고가 자동 표시됩니다.")

    input_col, src_col, dest_col = st.columns([30, 40, 30], gap="large")

    with input_col:
        st.markdown("#### 이동 제품")
        term = st.text_input("제품 검색", placeholder="제품명, 전산상 명칭, 별칭 일부 입력")
        opts = product_options(term)
        if opts.empty:
            st.warning("일치하는 제품이 없습니다.")
            return

        product = st.selectbox(
            "추천 제품",
            [""] + opts["standard_name"].tolist(),
            index=0,
            format_func=lambda x: "제품명을 입력하거나 선택하세요" if x == "" else x
        )
        if not product:
            st.info("이동할 제품을 선택하세요.")
            return

        lot_df = q("SELECT DISTINCT lot FROM inventory WHERE product_name=? AND qty>0 ORDER BY lot", (product,))
        if lot_df.empty:
            st.info("현재 재고가 0이 아닌 LOT/제조번호가 없습니다.")
            return
        lot = st.selectbox("LOT/제조번호", lot_df["lot"].tolist())

        exp_df = q("SELECT DISTINCT exp_date FROM inventory WHERE product_name=? AND lot=? AND qty>0 ORDER BY exp_date", (product, lot))
        exp = st.selectbox("유통기한", exp_df["exp_date"].tolist(), format_func=display_date_only)

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
            selected = st.selectbox("출발 재고 선택", labels)
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

        to_location = location_picker("move", "A1")
        qty = st.number_input("이동 수량", min_value=1, max_value=max_qty, value=min(1, max_qty), step=1)
        memo = st.text_input("메모", value="")
        st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

        if st.button("이동 저장", type="primary", use_container_width=True):
            try:
                move_inventory(src_id, to_company, to_location, int(qty), memo)
                st.success(f"이동 저장 완료: {product} / {qty}EA → {to_company} {to_location}")
                st.rerun()
            except Exception as e:
                st.error(str(e))
