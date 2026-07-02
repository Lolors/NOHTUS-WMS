"""Stocktake page for NOHTUS WMS.

Migrated from app.py. This module intentionally imports Streamlit because it
contains page rendering code.
"""

from __future__ import annotations

import sqlite3

from datetime import date
import streamlit as st


from nohtus.db import q
from nohtus.dates import display_date_only
from nohtus.services.inventory import adjust_inventory

# Several Excel/import helper functions still live in app.py until later steps.
# The migration script injects runtime imports inside page_stocktake as needed.


def page_stocktake():
    from app import current_baseline_stock_excel_bytes, full_inventory_excel_bytes, import_stock_survey_excel
    from app import full_inventory_excel_bytes, current_baseline_stock_excel_bytes, import_stock_survey_excel
    st.title("재고 실사")
    st.caption("제품명/LOT/유통기한/로케이션 단위로 필요한 재고를 먼저 조정하고, 실사용 엑셀과 기준재고 양식을 내려받거나 업로드합니다.")

    st.subheader("재고조정")
    adj_df = q("""
        SELECT id, location, company, product_name, warehouse_name, lot, exp_date, qty
        FROM inventory
        WHERE 1=1
        ORDER BY product_name, lot, exp_date, location
    """)
    if adj_df.empty:
        st.info("조정할 현재 재고가 없습니다.")
    else:
        adjust_area, _adjust_blank = st.columns([7, 3], gap="large")
        with adjust_area:
            form_left, form_right = st.columns(2, gap="large")

            with form_left:
                search = st.text_input("조정 대상 제품 검색", placeholder="제품명/전산상 명칭/LOT/로케이션 일부를 입력하세요", key="stock_adjust_search")
                filtered = adj_df.copy()
                if search.strip():
                    term = search.strip().lower()
                    filtered = filtered[
                        filtered["product_name"].fillna("").str.lower().str.contains(term, regex=False)
                        | filtered["warehouse_name"].fillna("").str.lower().str.contains(term, regex=False)
                        | filtered["lot"].fillna("").str.lower().str.contains(term, regex=False)
                        | filtered["location"].fillna("").str.lower().str.contains(term, regex=False)
                    ]

                if filtered.empty:
                    st.warning("검색어와 일치하는 재고가 없습니다.")
                    return

                products = filtered["product_name"].dropna().astype(str).drop_duplicates().tolist()
                product = st.selectbox("제품명", products, key="stock_adjust_product")
                lot_df = filtered[filtered["product_name"] == product].copy()

                lots = lot_df["lot"].fillna("-").astype(str).drop_duplicates().tolist()
                lot = st.selectbox("LOT/제조번호", lots, key=f"stock_adjust_lot_{product}")

                exp_df = lot_df[lot_df["lot"].fillna("-").astype(str) == lot].copy()
                exps = exp_df["exp_date"].fillna("-").astype(str).drop_duplicates().tolist()
                exp = st.selectbox("유통기한", exps, key=f"stock_adjust_exp_{product}_{lot}", format_func=display_date_only)

            target_df = exp_df[exp_df["exp_date"].fillna("-").astype(str) == exp].copy()
            labels = []
            id_by_label = {}
            for r in target_df.itertuples():
                label = f"{r.location} / {r.company} / 현재 {int(r.qty)}EA"
                labels.append(label)
                id_by_label[label] = int(r.id)

            with form_right:
                selected = st.selectbox("조정 대상 로케이션", labels, key=f"stock_adjust_inv_{product}_{lot}_{exp}")
                inv_id = id_by_label[selected]
                row = target_df[target_df["id"] == inv_id].iloc[0]

                actual = st.number_input("실물수량", min_value=0, value=int(row["qty"]), step=1, key=f"stock_adjust_actual_{inv_id}")
                reason = st.selectbox("사유", ["실사차이", "파손", "유통기한만료", "오출고", "기타"], key=f"stock_adjust_reason_{inv_id}")
                memo = st.text_input("메모", placeholder="필요 시 입력", key=f"stock_adjust_memo_{inv_id}")

            st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
            btn_left, btn_mid, btn_right = st.columns([1, 1, 1])
            with btn_mid:
                if st.button("재고조정 저장", type="primary", use_container_width=False, key=f"stock_adjust_submit_{inv_id}"):
                    try:
                        before, after, diff = adjust_inventory(int(inv_id), int(actual), reason, memo)
                        st.session_state["_stock_adjust_success_msg"] = f"재고조정 완료: {before}EA → {after}EA ({diff:+d}EA)"
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))

            st.markdown("#### 선택 재고")
            show = target_df[["id", "location", "company", "product_name", "warehouse_name", "lot", "exp_date", "qty"]].copy()
            show = show.rename(columns={
                "id": "ID", "location": "로케이션", "company": "사업장", "product_name": "표준제품명",
                "warehouse_name": "전산상명칭", "lot": "제조번호", "exp_date": "유통기한", "qty": "수량"
            })
            show["유통기한"] = show["유통기한"].apply(display_date_only)
            st.dataframe(show, hide_index=True, use_container_width=True)

        stock_adjust_msg = st.session_state.pop("_stock_adjust_success_msg", None)
        if stock_adjust_msg:
            st.success(stock_adjust_msg)

    st.markdown("---")
    st.subheader("실사/기준재고 파일")
    file_area, _file_blank = st.columns([6, 4], gap="large")
    with file_area:
        file_left, file_right = st.columns(2, gap="large")
        with file_left:
            st.markdown("#### 재고 실사용 엑셀")
            exclude_zero = bool(st.session_state.get("stocktake_exclude_zero", True))
            excel_data = full_inventory_excel_bytes(exclude_zero=exclude_zero)
            st.download_button(
                "재고 실사용 엑셀 내려받기",
                data=excel_data,
                file_name=f"NOHTUS_전체재고실사_{date.today().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
            st.checkbox(
                "재고가 0인 경우는 포함하지 않기",
                value=exclude_zero,
                key="stocktake_exclude_zero",
            )

        with file_right:
            st.markdown("#### 기준재고")
            st.download_button(
                "현재 기준 재고 양식 다운로드",
                data=current_baseline_stock_excel_bytes(exclude_zero=False),
                file_name=f"NOHTUS_현재기준재고양식_{date.today().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
            survey_file = st.file_uploader("기준재고 엑셀 선택", type=["xlsx"], key="stock_survey_upload")
            replace_current = st.checkbox("기존 현재재고를 삭제하고 업로드 파일로 교체", value=True, key="stock_survey_replace_current")
            if survey_file is not None:
                st.warning("업로드 실행 시 현재재고가 바뀔 수 있습니다. 운영 DB에서는 파일을 한 번 더 확인하세요.")
                if st.button("기준재고 DB 반영", type="primary", use_container_width=True):
                    try:
                        survey_file.seek(0)
                        inserted, skipped, prod_inserted, ambiguous_skipped = import_stock_survey_excel(survey_file, replace_current=replace_current)
                        st.success(f"반영 완료: 재고 {inserted}건 / 제품매칭표 신규 {prod_inserted}건 / 제외 {skipped}건")
                        st.rerun()
                    except Exception as e:
                        st.error(f"반영 실패: {e}")
