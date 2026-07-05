from datetime import date

import streamlit as st

from nohtus.db import q
from nohtus.pages.outbound import _render_last_sale_importer
from nohtus.services.master import customer_export_excel_bytes, import_customer_master_excel


def page_customer_master():
    st.title("거래처 관리")
    st.caption("거래처 엑셀을 업로드하면 출고지시와 업무일지에서 매출처/담당자 정보를 재사용할 수 있습니다.")

    c1, c2, c3 = st.columns([15, 15, 70], gap="large")
    with c1:
        st.download_button(
            "등록된 거래처 내려받기",
            data=customer_export_excel_bytes(),
            file_name=f"NOHTUS_등록거래처_{date.today().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
    with c2:
        up = st.file_uploader("거래처 관리 엑셀 업로드", type=["xlsx"], key="customer_master_upload")
        if up is not None and st.button("거래처 관리 업데이트", type="primary", use_container_width=True):
            try:
                updated, inserted, skipped = import_customer_master_excel(up)
                st.success(f"업데이트 완료: 수정 {updated}건 / 추가 {inserted}건 / 건너뜀 {skipped}건")
                st.rerun()
            except Exception as e:
                st.error(f"업로드 실패: {e}")
    with c3:
        _render_last_sale_importer()

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
