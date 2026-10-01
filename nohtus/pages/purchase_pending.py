"""매입대기 행 선택 및 사업장별 매입등록 완료 화면."""
import hashlib
import streamlit as st

from nohtus.config import COMPANIES
from nohtus.services.purchase_pending import complete_pending, cancel_pending, pending_product_catalog


def render_pending(frame):
    st.markdown("""<style>
    .st-key-purchase_pending_panel {width:70vw;max-width:100%;}
    @media(max-width:900px){.st-key-purchase_pending_panel {width:100%;}}
    </style>""", unsafe_allow_html=True)
    with st.container(key="purchase_pending_panel"):
        _render_pending_contents(frame)


def _render_pending_contents(frame):
    st.caption("제품 행을 선택하고 사업장과 ERP명을 지정하면 해당 수량이 정상재고에 반영됩니다.")
    if frame.empty:
        st.info("매입등록을 기다리는 제품이 없습니다.")
        return
    display = frame[["id", "inbound_date", "product_name", "supplier", "lot", "exp_date", "location", "qty", "memo"]].rename(columns={
        "id": "대기번호", "inbound_date": "입고일자", "product_name": "표준제품명", "supplier": "매입처",
        "lot": "LOT/제조번호", "exp_date": "유통기한", "location": "위치", "qty": "수량", "memo": "메모",
    })
    # 목록이 바뀌면 이전 행 인덱스 선택을 재사용하지 않는다.
    fingerprint = hashlib.sha256("_".join(frame['id'].astype(str)).encode()).hexdigest()[:16]
    selection_key = "purchase_pending_rows_" + fingerprint
    event = st.dataframe(display, hide_index=True, use_container_width=True,
                         on_select="rerun", selection_mode="single-cell", key=selection_key)
    selected = event.selection.cells
    if not selected:
        return
    row = frame.iloc[selected[0][0]]
    pending_id = int(row['id'])
    st.markdown(f"**선택한 제품: {row['product_name']} · {int(row['qty']):,} EA**")
    company_col, product_col, erp_col, code_col = st.columns([1, 2, 2, 1.2], gap="medium")
    with company_col:
        company = st.selectbox("매입등록 사업장", COMPANIES, index=None, placeholder="사업장을 선택하세요",
                               key=f"pending_company_{pending_id}")
    with product_col:
        term = st.text_input("표준제품명 검색", value=str(row['product_name']),
                             disabled=company is None, placeholder="표준제품명·ERP명·제품코드 검색",
                             key=f"pending_product_search_{pending_id}_{company}").strip()
        results = pending_product_catalog(company, term)
        search_key = hashlib.sha256(f"{company}:{term}".encode()).hexdigest()[:12]
        names = results['standard_name'].drop_duplicates().tolist()
        if names:
            standard_name = st.selectbox("표준제품명", names, key=f"pending_product_choice_{pending_id}_{search_key}")
        elif company and term:
            st.caption("검색 결과가 없습니다. 새 표준제품명을 입력하세요.")
            standard_name = st.text_input("표준제품명 직접 입력", value=term,
                                          key=f"pending_new_name_{pending_id}_{search_key}").strip()
        else:
            standard_name = ""
            if company:
                st.caption("표준제품명을 검색하세요.")
    name_key = hashlib.sha256(standard_name.encode()).hexdigest()[:12]
    catalog = pending_product_catalog(company) if company and standard_name else results.iloc[0:0]
    matches = catalog.loc[(catalog['standard_name'] == standard_name) & catalog['erp_name'].ne('')]
    mapping_id = None
    saved_code = ""
    with erp_col:
        field_label = "비자료명" if company == "비자료" else "ERP명"
        erp_key = f"pending_erp_{pending_id}_{company}_{name_key}"
        if not matches.empty:
            mappings = {int(r.id): r for r in matches.itertuples()}
            mapping_id = st.selectbox(f"{field_label} 선택", list(mappings),
                format_func=lambda value: mappings[value].erp_name + (f" · {mappings[value].product_code}" if mappings[value].product_code else ""),
                key=erp_key + "_mapping")
            erp_name = mappings[mapping_id].erp_name
            saved_code = str(mappings[mapping_id].product_code or '').strip()
        else:
            erp_name = st.text_input(field_label, placeholder="연결된 이름이 없을 때 직접 입력",
                                     disabled=not company or not standard_name, key=erp_key).strip()
    with code_col:
        code_key = hashlib.sha256(f"{mapping_id}:{saved_code}".encode()).hexdigest()[:12]
        product_code = st.text_input("ERP 제품코드 (선택)", value=saved_code,
                                     disabled=bool(saved_code) or not standard_name or company not in ("노투스팜", "NOH"),
                                     key=f"pending_code_{pending_id}_{company}_{name_key}_{code_key}").strip()
    _, cancel_col, complete_col, _ = st.columns([1, 1, 1, 1])
    with cancel_col:
        cancel_clicked = st.button("매입대기 취소", use_container_width=True, key=f"cancel_pending_{pending_id}",
                                   help="선택한 행을 매입대기 목록과 로케이션맵에서 제외합니다. 정상재고는 변경되지 않습니다.")
    with complete_col:
        complete_clicked = st.button("매입등록 완료", type="primary", use_container_width=True,
                                     disabled=not company or not standard_name or not erp_name, key=f"complete_pending_{pending_id}")
    if cancel_clicked:
        try:
            cancel_pending(pending_id)
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.session_state['purchase_registration_message'] = f"매입대기 취소: {row['product_name']} / {int(row['qty']):,} EA"
            st.rerun()
    elif complete_clicked:
        try:
            complete_pending(pending_id, company, erp_name, product_code, standard_name=standard_name, mapping_id=mapping_id)
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.session_state['purchase_registration_message'] = f"매입등록 완료: {company} / {standard_name} / {int(row['qty']):,} EA"
            st.rerun()
