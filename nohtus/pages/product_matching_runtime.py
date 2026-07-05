from datetime import date

import streamlit as st

from nohtus.db import q, exec_sql
from nohtus.services.products import product_master_excel_bytes, import_product_master_excel
from nohtus.services.master import (
    apply_standard_name_change,
    approve_mapping_conflict,
    delete_product,
    find_mapping_conflicts_from_inventory,
)


def page_product_matching():
    st.title("제품 매칭 관리")
    st.caption("표준제품명과 사업장별 ERP명/비자료명을 관리합니다.")

    action_col, _spacer = st.columns([4, 6], gap="large")
    with action_col:
        st.download_button(
            "제품 매칭표 엑셀 파일 내려받기",
            data=product_master_excel_bytes(),
            file_name=f"NOHTUS_제품매칭표_{date.today().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
        uploaded = st.file_uploader("수정한 제품 매칭표 엑셀 업로드", type=["xlsx"], key="product_matching_upload")
        if uploaded is not None and st.button("업로드 파일로 제품 매칭표 업데이트", type="primary", use_container_width=True):
            try:
                u, i, sk = import_product_master_excel(uploaded)
                total = u + i + sk
                st.success("✅ 제품 매칭표 업데이트 완료")
                st.markdown(f"""
                - 총 처리 : **{total}건**
                - 업로드 파일 기준 반영 : **{i}건**
                - 건너뜀 : **{sk}건**
                - 반영 방식 : **기존 제품매칭표 완전 교체**
                """)
                st.rerun()
            except Exception as e:
                st.error(f"업로드 실패: {e}")

    st.markdown("### 🔍 매칭 이상 검사")
    conflict_df = find_mapping_conflicts_from_inventory()
    if conflict_df.empty:
        st.success("확인이 필요한 ERP명/비자료명 공유 충돌이 없습니다.")
    else:
        st.warning("같은 ERP명/비자료명이 기존 다른 표준제품명에도 등록되어 있습니다. 실제 충돌인지, 여러 표준제품명이 함께 쓰는 것이 맞는지 확인하세요.")
        edit_df = conflict_df.copy()
        edit_df.insert(0, "문제없음", False)
        edited_conflict = st.data_editor(
            edit_df,
            hide_index=True,
            use_container_width=True,
            disabled=[c for c in edit_df.columns if c != "문제없음"],
            column_config={"문제없음": st.column_config.CheckboxColumn("문제없음", help="이 공유 매칭이 의도된 것이면 체크하세요.")},
            key="pm_conflict_editor",
        )
        st.caption("문제없음으로 확인한 ERP명/비자료명은 시스템이 기억하며, 이후 같은 원본명으로는 다시 묻지 않습니다.")
        if st.button("체크한 공유 매칭 확인 완료", type="primary", use_container_width=True):
            checked = edited_conflict[edited_conflict["문제없음"] == True]
            if checked.empty:
                st.info("체크된 행이 없습니다.")
            else:
                for _, rr in checked.iterrows():
                    approve_mapping_conflict(str(rr.get("사업장", "")), str(rr.get("ERP명/비자료명", "")))
                st.success(f"{len(checked)}건을 문제없음으로 확인했습니다.")
                st.rerun()

    st.markdown("### 제품 매칭표 보완용 파일")
    st.caption("제품매칭표 전체를 내려받아 누락된 ERP명/비자료명 정보를 보완한 뒤 다시 업로드할 수 있습니다.")
    st.download_button(
        "제품 매칭표 보완용 파일 내려받기",
        data=product_master_excel_bytes(highlight_missing=True),
        file_name=f"NOHTUS_제품매칭표_보완용_{date.today().strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

    st.markdown("### 제품 매칭표 수정")
    df = q("""SELECT id, standard_name AS 표준제품명, erp_nohtuspharm_name AS '노투스팜 ERP명', product_code AS '노투스팜 ERP 제품코드', erp_noh_name AS 'NOH ERP명', erp_noh_code AS 'NOH ERP 제품코드', erp_nohtus_name AS '노투스 ERP명', bidata_name AS '비자료명', aliases AS 별칭
              FROM products ORDER BY standard_name""")
    if df.empty:
        st.info("등록된 제품이 없습니다.")
        return

    term = st.text_input("수정할 제품 검색", placeholder="표준제품명/ERP명/별칭 일부 입력", key="pm_edit_term")
    shown = df.copy()
    if term.strip():
        mask = False
        for col in ["표준제품명","노투스팜 ERP명","노투스팜 ERP 제품코드","NOH ERP명","NOH ERP 제품코드","노투스 ERP명","비자료명","별칭"]:
            mask = mask | shown[col].fillna("").astype(str).str.contains(term.strip(), case=False, regex=False)
        shown = shown[mask]
    if shown.empty:
        st.info("검색 결과가 없습니다.")
        return

    choice_options = [""] + [f"{int(r.id)} | {r.표준제품명}" for r in shown.itertuples()]
    choice_label = st.selectbox("수정할 제품 선택", choice_options, index=0, key="pm_edit_choice", format_func=lambda x: "제품명을 입력하거나 선택하세요" if x == "" else x)
    if not choice_label:
        return

    pid = int(choice_label.split(" | ")[0])
    row = df[df["id"] == pid].iloc[0]
    edit_key = f"pm_edit_{pid}"
    ec1, ec2, ec3, ec4 = st.columns(4)
    with ec1:
        e_std = st.text_input("표준제품명", value=str(row["표준제품명"] or ""), key=f"{edit_key}_std")
        e_alias = st.text_input("별칭", value=str(row["별칭"] or ""), key=f"{edit_key}_alias")
    with ec2:
        e_np = st.text_input("노투스팜 ERP명", value=str(row["노투스팜 ERP명"] or ""), key=f"{edit_key}_np")
        e_code = st.text_input("노투스팜 ERP 제품코드", value=str(row["노투스팜 ERP 제품코드"] or ""), key=f"{edit_key}_code")
    with ec3:
        e_noh = st.text_input("NOH ERP명", value=str(row["NOH ERP명"] or ""), key=f"{edit_key}_noh")
        e_noh_code = st.text_input("NOH ERP 제품코드", value=str(row["NOH ERP 제품코드"] or ""), key=f"{edit_key}_noh_code")
    with ec4:
        e_nt = st.text_input("노투스 ERP명", value=str(row["노투스 ERP명"] or ""), key=f"{edit_key}_nt")
        e_bidata = st.text_input("비자료명", value=str(row["비자료명"] or ""), key=f"{edit_key}_bidata")

    save_col, delete_col = st.columns(2)
    with save_col:
        if st.button("제품명 수정", type="primary", use_container_width=True, key=f"{edit_key}_save"):
            old_std = str(row["표준제품명"] or "").strip()
            new_std = e_std.strip()
            if not new_std:
                st.error("표준제품명은 비워둘 수 없습니다.")
            else:
                exec_sql("""UPDATE products SET standard_name=?, warehouse_name=?, aliases=?, product_code=?, erp_nohtuspharm_name=?, erp_noh_name=?, erp_noh_code=?, erp_nohtus_name=?, bidata_name=? WHERE id=?""",
                         (new_std, new_std, e_alias.strip(), str(e_code).strip(), e_np.strip(), e_noh.strip(), str(e_noh_code).strip(), e_nt.strip(), e_bidata.strip(), pid))
                apply_standard_name_change(old_std, new_std)
                st.success("수정했습니다. 이미 등록된 재고/이력 화면에도 변경된 표준제품명을 반영했습니다.")
                st.rerun()
    with delete_col:
        if st.button("제품명 삭제", type="secondary", use_container_width=True, key=f"{edit_key}_delete"):
            st.session_state["confirm_delete_product_id"] = pid
            st.rerun()

    if st.session_state.get("confirm_delete_product_id") == pid:
        st.warning("정말로 삭제하시겠습니까?")
        dc1, dc2 = st.columns(2)
        with dc1:
            if st.button("취소", use_container_width=True):
                st.session_state.pop("confirm_delete_product_id", None)
                st.rerun()
        with dc2:
            if st.button("삭제", type="primary", use_container_width=True):
                try:
                    delete_product(pid)
                    st.session_state.pop("confirm_delete_product_id", None)
                    st.success("제품을 삭제했습니다.")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

