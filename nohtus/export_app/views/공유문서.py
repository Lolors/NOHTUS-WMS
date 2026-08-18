from __future__ import annotations

import os
import subprocess
from pathlib import Path

import streamlit as st
from nohtus.export_app.services import export_service, folder_service, history_service, order_service
from nohtus.export_app.services.shared_document_view_service import (
    default_document_period,
    filter_and_sort_cases,
    format_case_option as build_case_option_label,
)


def open_selected_path(path: Path, label: str) -> None:
    try:
        path = Path(path)
        if not path.exists():
            st.error(f'{label} 경로가 없습니다: {path}')
            return
        activation_script = f'Start-Process -FilePath "{str(path).replace(chr(34), chr(34) * 2)}"'
        subprocess.Popen(
            ['powershell.exe', '-NoProfile', '-WindowStyle', 'Hidden', '-Command', activation_script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as exc:
        st.error(f'{label}을(를) 열 수 없습니다: {exc}')


def render() -> None:
    st.title('공유용 자료')
    st.caption('수출 건을 선택한 뒤 필요한 자료를 출력하거나 관련 폴더를 열 수 있습니다.')

    cases = order_service.list_editable_cases()
    if not cases:
        st.info('표시할 수출 건이 없습니다.')
        st.stop()

    st.markdown(
        '''
        <style>
        div[data-testid="stVerticalBlock"] div[data-testid="stVerticalBlock"]:has(#document-case-filter-anchor) {
            width: 56vw;
            max-width: 56vw;
        }
        @media(max-width:900px) {
            div[data-testid="stVerticalBlock"] div[data-testid="stVerticalBlock"]:has(#document-case-filter-anchor) {
                width: 100%;
                max-width: 100%;
            }
        }
        </style>
        ''',
        unsafe_allow_html=True,
    )

    with st.container():
        st.markdown('<span id="document-case-filter-anchor"></span>', unsafe_allow_html=True)
        default_start_date, default_end_date = default_document_period()
        filter_cols = st.columns([3, 3, 4])
        selected_period = filter_cols[0].date_input(
            '출고 기간',
            value=(default_start_date, default_end_date),
            key='document_case_period',
        )
        if isinstance(selected_period, (tuple, list)) and len(selected_period) == 2:
            selected_start_date, selected_end_date = selected_period
        elif isinstance(selected_period, (tuple, list)) and selected_period:
            selected_start_date = selected_end_date = selected_period[0]
        else:
            selected_start_date = selected_end_date = default_end_date

        countries = sorted({str(case['country']).strip() for case in cases if str(case['country']).strip()})
        selected_country = filter_cols[1].selectbox('국가', ['전체'] + countries, key='document_case_country')
        product_query = filter_cols[2].text_input('제품명 검색', key='document_case_product_search').strip().casefold()

    filtered_cases = filter_and_sort_cases(
        cases,
        start_date=selected_start_date,
        end_date=selected_end_date,
        selected_country=selected_country,
        product_query=product_query,
    )
    if not filtered_cases:
        st.warning('조건에 맞는 수출 건이 없습니다.')
        st.stop()

    case_by_id = {int(case['id']): case for case in filtered_cases}
    case_options: list[int | None] = [None, *case_by_id.keys()]

    case_filter_key = (
        f"{selected_start_date}_{selected_end_date}_"
        f"{selected_country}_{product_query}_{len(filtered_cases)}"
    )
    selected_case_id = st.selectbox(
        '수출 건 선택',
        case_options,
        format_func=lambda selected_id: (
            '수출 건을 선택하세요'
            if selected_id is None
            else build_case_option_label(case_by_id[int(selected_id)])
        ),
        key=f'document_case_select_{case_filter_key}',
    )
    if selected_case_id is None:
        st.session_state.pop('document_case_id', None)
        st.session_state.pop('shared_document_view', None)
        st.info('공유용 자료를 만들 수출 건을 선택하세요.')
        st.stop()

    case_id = int(selected_case_id)
    previous_case_id = st.session_state.get('document_case_id')
    if previous_case_id != case_id:
        st.session_state['document_case_id'] = case_id
        st.session_state.pop('shared_document_view', None)
    case = export_service.get_case(case_id)

    is_domestic_delivery = (
        str(case['case_type'] or '').strip() != 'historical'
        and str(case['stage'] or '').strip() == '국내배송'
    )
    is_final_document_available = str(case['stage'] or '').strip() in {
        '패킹 대기',
        '패킹 완료',
        '국내배송',
    }
    action_cols = st.columns(4)
    return_to_packing = is_domestic_delivery and action_cols[0].button(
        '패킹완료 단계로 되돌리기',
        key=f'return_shared_document_to_packing_{case_id}',
        type='secondary',
        use_container_width=True,
    )
    open_folder = action_cols[1].button(
        '📂 폴더 열기',
        use_container_width=True,
    )
    open_final_document = action_cols[2].button(
        '최종문서 출력하기',
        type='primary',
        use_container_width=True,
        disabled=not is_final_document_available,
        help=(
            None
            if is_final_document_available
            else '패킹 대기, 패킹 완료 또는 국내배송 단계에서 최종문서를 출력할 수 있습니다.'
        ),
    )
    open_shipment_products = action_cols[3].button(
        '출고 예정 제품 리스트',
        type='primary',
        use_container_width=True,
    )

    if return_to_packing:
        try:
            export_service.return_domestic_to_packing_complete(case_id)
            folder_service.sync_case_folder(case_id)
            history_service.add(case_id, '단계 되돌리기', '국내배송 → 패킹 완료')
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.success('패킹완료 단계로 되돌렸습니다. 수출대기 저장과 박스 패킹에서 다시 선택할 수 있습니다.')
            st.rerun()

    if open_folder:
        try:
            case_folder = folder_service.ensure_case_folder(case_id)
            open_selected_path(case_folder, '수출 폴더')
        except Exception as exc:
            st.warning(f'수출 폴더를 준비하지 못했습니다: {exc}')
    else:
        stored_folder_path = str(case['folder_path'] or '').strip()
        if stored_folder_path:
            st.caption(stored_folder_path)

    if open_final_document:
        st.session_state['shared_document_view'] = 'final'
    if open_shipment_products:
        st.session_state['shared_document_view'] = 'shipment_products'

    if not is_final_document_available and st.session_state.get('shared_document_view') == 'final':
        st.session_state.pop('shared_document_view', None)

    selected_view = st.session_state.get('shared_document_view')
    if selected_view == 'final':
        from nohtus.export_app.components.shared_document_renderer import render_document
        from nohtus.export_app.services import document_service, shipment_service

        packed = document_service.get_packed_document_data(case_id)
        actual_rows = shipment_service.list_case_items(case_id)
        render_document(case, packed, actual_rows)
    elif selected_view == 'shipment_products':
        from nohtus.export_app.components.shared_document_renderer import render_shipment_product_list
        from nohtus.export_app.services import document_service

        shipment_product_rows = document_service.get_shipment_product_list_data(case_id)
        render_shipment_product_list(case, shipment_product_rows)
    else:
        if not is_final_document_available:
            st.caption('최종문서는 패킹 대기, 패킹 완료 또는 국내배송 단계에서 출력할 수 있습니다.')
        st.info('출력할 문서 종류를 선택하세요.')
