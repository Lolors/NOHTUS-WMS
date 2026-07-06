"""Master page for NOHTUS WMS.

Migrated from app.py. This module intentionally imports Streamlit because it
contains page rendering code.
"""

from __future__ import annotations

from nohtus.services.products import import_product_master_excel, product_master_excel_bytes
import calendar
import json
import re
from datetime import date, datetime
from io import BytesIO

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from nohtus.config import AREA_COLOR, AREA_CONFIG, COMPANIES, INBOUND_COMPANIES
from nohtus.db import connect, exec_sql, q
from nohtus.dates import display_date_only, expiry_status, normalize_exp_date
from nohtus.locations import location_picking_key, make_location, parse_location


def page_master():
    from nohtus.services.master import match_erp_name
    st.title("제품 마스터")
    st.caption("제품 자체의 기준명은 표준제품명으로 관리하고, ERP별 이름은 별도 매핑으로 관리합니다. 노투스팜/NOH ERP 제품코드는 각 ERP명 바로 뒤에서 관리하고, 노투스 ERP명 오른쪽에는 비자료명을 관리합니다.")
    df = q("SELECT id, product_code, standard_name, aliases, erp_nohtuspharm_name, erp_noh_name, erp_noh_code, erp_nohtus_name, bidata_name FROM products ORDER BY standard_name")

    top1, top2 = st.columns(2, gap="large")
    with top1:
        st.download_button(
            "제품 마스터 엑셀 양식 다운로드",
            data=product_master_excel_bytes(),
            file_name=f"NOHTUS_제품마스터_{date.today().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
    with top2:
        uploaded = st.file_uploader("수정한 제품 마스터 엑셀 업로드", type=["xlsx"], key="product_master_upload")
        if uploaded is not None:
            if st.button("업로드 파일로 제품 마스터 업데이트", type="primary", use_container_width=True):
                try:
                    updated, inserted, skipped = import_product_master_excel(uploaded)
                    st.success(f"업데이트 완료: 수정 {updated}건 / 추가 {inserted}건 / 건너뜀 {skipped}건")
                    st.rerun()
                except Exception as e:
                    st.error(f"업로드 실패: {e}")

    st.markdown("### 제품 목록")
    view = df[["standard_name", "erp_nohtuspharm_name", "product_code", "erp_noh_name", "erp_noh_code", "erp_nohtus_name", "bidata_name", "aliases"]].rename(columns={
        "standard_name":"표준제품명",
        "erp_nohtuspharm_name":"노투스팜 ERP명",
        "product_code":"노투스팜 ERP 제품코드",
        "erp_noh_name":"NOH ERP명",
        "erp_noh_code":"NOH ERP 제품코드",
        "erp_nohtus_name":"노투스 ERP명",
        "bidata_name":"비자료명",
        "aliases":"별칭",
    })
    st.dataframe(view, use_container_width=True, hide_index=True)

    with st.expander("기존 제품 수정", expanded=False):
        if df.empty:
            st.info("수정할 제품이 없습니다.")
        else:
            edit_term = st.text_input("수정할 제품 검색", placeholder="표준제품명/ERP명/별칭 일부 입력")
            edit_df = df.copy()
            if edit_term.strip():
                term = edit_term.strip().lower()
                edit_df = edit_df[
                    edit_df["standard_name"].fillna("").str.lower().str.contains(term, regex=False)
                    | edit_df["aliases"].fillna("").str.lower().str.contains(term, regex=False)
                    | edit_df["product_code"].fillna("").str.lower().str.contains(term, regex=False)
                    | edit_df["erp_nohtuspharm_name"].fillna("").str.lower().str.contains(term, regex=False)
                    | edit_df["erp_noh_name"].fillna("").str.lower().str.contains(term, regex=False)
                    | edit_df["erp_noh_code"].fillna("").str.lower().str.contains(term, regex=False)
                    | edit_df["erp_nohtus_name"].fillna("").str.lower().str.contains(term, regex=False)
                    | edit_df["bidata_name"].fillna("").str.lower().str.contains(term, regex=False)
                ]
            if edit_df.empty:
                st.warning("일치하는 제품이 없습니다.")
            else:
                options = [f"{r.standard_name} / 노투스팜:{r.erp_nohtuspharm_name or '-'} / NOH:{r.erp_noh_name or '-'} / 노투스:{r.erp_nohtus_name or '-'}" for r in edit_df.itertuples()]
                selected = st.selectbox("수정할 제품 선택", options)
                row = edit_df.iloc[options.index(selected)]
                with st.form("edit_product"):
                    name = st.text_input("표준제품명", value=str(row["standard_name"] or ""))
                    erp_np = st.text_input("노투스팜 ERP명", value=str(row.get("erp_nohtuspharm_name", "") or ""))
                    code = st.text_input("노투스팜 ERP 제품코드", value=str(row["product_code"] or ""))
                    erp_noh = st.text_input("NOH ERP명", value=str(row.get("erp_noh_name", "") or ""))
                    erp_noh_code = st.text_input("NOH ERP 제품코드", value=str(row.get("erp_noh_code", "") or ""))
                    erp_nt = st.text_input("노투스 ERP명", value=str(row.get("erp_nohtus_name", "") or ""))
                    bidata_name = st.text_input("비자료명", value=str(row.get("bidata_name", "") or ""))
                    aliases = st.text_input("별칭", value=str(row["aliases"] or ""))
                    if st.form_submit_button("수정 저장", use_container_width=True):
                        if not name.strip():
                            st.error("표준제품명은 필수입니다.")
                        else:
                            exec_sql("UPDATE products SET product_code=?, standard_name=?, warehouse_name=?, aliases=?, erp_nohtuspharm_name=?, erp_noh_name=?, erp_noh_code=?, erp_nohtus_name=?, bidata_name=? WHERE id=?", (code.strip(), name.strip(), name.strip(), aliases.strip(), erp_np.strip(), erp_noh.strip(), erp_noh_code.strip(), erp_nt.strip(), bidata_name.strip(), int(row["id"])))
                            st.success("제품 수정 완료")
                            st.rerun()

    with st.expander("제품 추가"):
        with st.form("add_product"):
            name=st.text_input("표준제품명")
            erp_np=st.text_input("노투스팜 ERP명")
            code=st.text_input("노투스팜 ERP 제품코드")
            erp_noh=st.text_input("NOH ERP명")
            erp_noh_code=st.text_input("NOH ERP 제품코드")
            erp_nt=st.text_input("노투스 ERP명")
            bidata_name=st.text_input("비자료명")
            aliases=st.text_input("별칭")
            if st.form_submit_button("추가", use_container_width=True) and name:
                exec_sql("INSERT INTO products(product_code,standard_name,warehouse_name,aliases,erp_nohtuspharm_name,erp_noh_name,erp_noh_code,erp_nohtus_name,bidata_name) VALUES(?,?,?,?,?,?,?,?,?)", (code.strip(),name.strip(),name.strip(),aliases.strip(),erp_np.strip(),erp_noh.strip(),erp_noh_code.strip(),erp_nt.strip(),bidata_name.strip()))
                st.success("제품 추가 완료"); st.rerun()

    with st.expander("ERP 확인 필요 후보 관리", expanded=True):
        st.caption("같은 ERP명칭이 실제 여러 제품일 수 있는 경우 후보를 등록합니다. ERP 업로드 시 후보가 2개 이상이면 사람이 선택해야 합니다.")
        c1, c2, c3 = st.columns([1,1.4,1.6], gap="medium")
        with c1:
            erp_company = st.selectbox("ERP구분", ["노투스팜", "NOH", "노투스"], key="amb_erp_company")
        with c2:
            erp_name = st.text_input("ERP명칭", placeholder="예: JS TOX", key="amb_erp_name")
        with c3:
            products = q("SELECT standard_name FROM products ORDER BY standard_name")
            cand = st.selectbox("후보 표준제품", products["standard_name"].tolist() if not products.empty else [], key="amb_candidate")
        memo = st.text_input("메모", placeholder="예: ERP명만으로 실제 출고제품 판단 불가", key="amb_memo")
        if st.button("확인 필요 후보 추가", type="primary", use_container_width=True):
            if not erp_name.strip() or not cand:
                st.error("ERP명칭과 후보 제품을 입력하세요.")
            else:
                exec_sql("INSERT INTO erp_ambiguous_candidates(erp_company, erp_name, candidate_product, memo) VALUES(?,?,?,?)", (erp_company, erp_name.strip(), cand, memo.strip()))
                st.success("후보 추가 완료")
                st.rerun()
        amb = q("SELECT id, erp_company AS ERP구분, erp_name AS ERP명칭, candidate_product AS 후보제품, memo AS 메모 FROM erp_ambiguous_candidates ORDER BY ERP구분, ERP명칭, 후보제품")
        if amb.empty:
            st.info("등록된 확인 필요 후보가 없습니다.")
        else:
            st.caption("삭제할 후보만 체크한 뒤 삭제 버튼을 누르세요.")
            amb_edit = amb.copy()
            amb_edit.insert(0, "삭제", False)
            edited_amb = st.data_editor(
                amb_edit,
                hide_index=True,
                use_container_width=True,
                disabled=["id", "ERP구분", "ERP명칭", "후보제품", "메모"],
                column_config={"id": None, "삭제": st.column_config.CheckboxColumn("삭제")},
                key="amb_delete_editor",
            )
            delete_ids = edited_amb.loc[edited_amb["삭제"] == True, "id"].astype(int).tolist()
            if st.button("체크한 후보 삭제", disabled=(len(delete_ids) == 0), use_container_width=True):
                with connect() as con:
                    con.executemany("DELETE FROM erp_ambiguous_candidates WHERE id=?", [(i,) for i in delete_ids])
                    con.commit()
                st.success(f"{len(delete_ids)}건 삭제 완료")
                st.rerun()

    with st.expander("ERP명칭 매칭 테스트"):
        t1, t2 = st.columns([1,2], gap="medium")
        with t1:
            test_company = st.selectbox("테스트 ERP구분", ["노투스팜", "NOH", "노투스"], key="test_erp_company")
        with t2:
            test_name = st.text_input("테스트 ERP명칭", placeholder="ERP 매입/매출 엑셀에 나온 제품명", key="test_erp_name")
        if st.button("매칭 확인", use_container_width=True):
            res = match_erp_name(test_company, test_name)
            if res["status"] == "auto":
                st.success(res["message"])
            elif res["status"] == "ambiguous":
                st.warning(res["message"])
                st.write("후보제품")
                st.write(res["candidates"])
            else:
                st.error(res["message"])


# ---------------- ERP / customer master ----------------

def page_customer_master():
    from nohtus.services.master import customer_export_excel_bytes, import_customer_master_excel
    st.title("거래처 관리")
    st.caption("거래처 엑셀을 업로드하면 출고지시와 업무일지에서 매출처/담당자 정보를 재사용할 수 있습니다.")
    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.download_button("등록된 거래처 내려받기", data=customer_export_excel_bytes(), file_name=f"NOHTUS_등록거래처_{date.today().strftime('%Y%m%d')}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
    with c2:
        up = st.file_uploader("거래처 관리 엑셀 업로드", type=["xlsx"], key="customer_master_upload")
        if up is not None and st.button("거래처 관리 업데이트", type="primary", use_container_width=True):
            try:
                updated, inserted, skipped = import_customer_master_excel(up)
                st.success(f"업데이트 완료: 수정 {updated}건 / 추가 {inserted}건 / 건너뜀 {skipped}건")
                st.rerun()
            except Exception as e:
                st.error(f"업로드 실패: {e}")
    df = q("SELECT customer_code AS 거래처코드, customer_name AS 거래처명, company AS 사업장, customer_type AS 유형, manager AS 담당자, phone AS 연락처, address AS 주소, memo AS 메모 FROM customers ORDER BY customer_name, company")
    st.markdown("### 등록된 거래처")
    if df.empty:
        st.info("등록된 거래처가 없습니다.")
    else:
        term = st.text_input("거래처 검색", placeholder="거래처명/담당자/주소 일부 입력")
        if term.strip():
            low = term.strip().lower()
            mask = False
            for col in df.columns:
                mask = mask | df[col].fillna("").astype(str).str.lower().str.contains(low, regex=False)
            df = df[mask]
        st.dataframe(df, use_container_width=True, hide_index=True)

def page_inventory_metadata_edit():
    from nohtus.services.master import render_inventory_metadata_editor
    st.title("재고정보 수정")
    st.caption("기존 재고의 제조번호/유통기한이 잘못 입력된 경우에만 사용합니다. 수량은 변경하지 않습니다.")
    render_inventory_metadata_editor()
