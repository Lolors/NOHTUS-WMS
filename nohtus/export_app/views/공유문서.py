from __future__ import annotations

import os
import subprocess
from pathlib import Path

import streamlit as st
from nohtus.export_app.services import (
    export_service,
    folder_service,
    history_service,
    order_service,
    photo_organizer_service,
)
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


def choose_local_folder(initial_path: Path) -> str | None:
    """Show the native Windows folder picker used by this local desktop app."""
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        selected = filedialog.askdirectory(initialdir=str(initial_path), title='사진 저장 경로 선택')
        root.destroy()
        return selected or None
    except Exception as exc:
        st.warning(f'폴더 선택 창을 열지 못했습니다: {exc}')
        return None


def choose_and_store_local_folder(state_key: str) -> None:
    selected = choose_local_folder(Path(st.session_state.get(state_key) or Path.home()))
    if selected:
        st.session_state[state_key] = selected


def render_photo_organizer(case_id: int) -> None:
    box_numbers = photo_organizer_service.list_ctn_numbers(case_id)
    if not box_numbers:
        st.warning('박스 패킹에서 저장된 CTN이 없습니다.')
        return

    st.markdown('### 사진 정리')
    st.caption('각 영역에 사진을 드래그해 넣으세요. CTN은 번호 오름차순으로 표시됩니다.')
    st.markdown(
        '''
        <style>
        div[data-testid="stVerticalBlock"]:has(> div .photo-drop-anchor) {
            border: 2px dashed #8a94a6;
            border-radius: 12px;
            padding: 14px 16px 8px;
            margin: 8px 0 16px;
            background: rgba(128, 128, 128, 0.05);
        }
        </style>
        ''',
        unsafe_allow_html=True,
    )

    area_names = [*(f'CTN{number}' for number in box_numbers), '전체']
    uploads: dict[str, list] = {}
    tags: dict[str, list[str]] = {}
    for area_name in area_names:
        with st.container():
            st.markdown(f'<div class="photo-drop-anchor"></div>#### {area_name}', unsafe_allow_html=True)
            area_files = list(st.file_uploader(
                f'{area_name} 사진',
                type=['jpg', 'jpeg', 'png', 'webp', 'bmp', 'gif', 'tif', 'tiff'],
                accept_multiple_files=True,
                key=f'photo_organizer_files_{case_id}_{area_name}',
                label_visibility='collapsed',
            ) or [])
            uploads[area_name] = area_files
            area_tags: list[str] = []
            if len(area_files) > 1:
                st.caption('사진이 여러 장이면 각 사진의 태그를 선택하세요.')
                for index, uploaded in enumerate(area_files):
                    cols = st.columns([3, 2])
                    cols[0].text_input(
                        f'{area_name} 파일 {index + 1}',
                        value=uploaded.name,
                        disabled=True,
                        key=f'photo_file_name_{case_id}_{area_name}_{index}',
                        label_visibility='collapsed',
                    )
                    area_tags.append(cols[1].selectbox(
                        f'{uploaded.name} 태그',
                        photo_organizer_service.PHOTO_TAGS,
                        key=f'photo_tag_{case_id}_{area_name}_{index}',
                        label_visibility='collapsed',
                    ))
            elif area_files:
                area_tags = ['내부']
            tags[area_name] = area_tags

    save_path_key = f'photo_organizer_save_path_{case_id}'
    if save_path_key not in st.session_state:
        st.session_state[save_path_key] = str(photo_organizer_service.default_save_root())
    path_cols = st.columns([4, 1])
    save_path = path_cols[0].text_input('저장 경로', key=save_path_key)
    path_cols[1].button(
        '저장 경로 설정',
        key=f'choose_photo_path_{case_id}',
        use_container_width=True,
        on_click=choose_and_store_local_folder,
        args=(save_path_key,),
    )

    if st.button('정리 완료', key=f'complete_photo_organizer_{case_id}', type='primary', use_container_width=True):
        try:
            destination = photo_organizer_service.organize_photos(case_id, Path(save_path), uploads, tags)
        except (OSError, ValueError) as exc:
            st.error(str(exc))
        else:
            history_service.add(case_id, '사진 정리', str(destination))
            st.success(f'사진 정리를 완료했습니다: {destination}')


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
    open_photo_organizer = action_cols[1].button(
        '사진 정리',
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
        except ValueError as exc:
            st.error(str(exc))
        else:
            _, folder_error = folder_service.try_sync_case_folder(case_id)
            history_service.add(case_id, '단계 되돌리기', '국내배송 → 패킹 완료')
            st.success(
                '패킹완료 단계로 되돌렸습니다. 수출대기 저장과 박스 패킹에서 다시 선택할 수 있습니다.'
                + (f' (폴더 저장 실패: {folder_error})' if folder_error else '')
            )
            st.rerun()

    if open_photo_organizer:
        st.session_state['shared_document_view'] = 'photo_organizer'

    if open_final_document:
        st.session_state['shared_document_view'] = 'final'
    if open_shipment_products:
        st.session_state['shared_document_view'] = 'shipment_products'

    if not is_final_document_available and st.session_state.get('shared_document_view') == 'final':
        st.session_state.pop('shared_document_view', None)

    selected_view = st.session_state.get('shared_document_view')
    if selected_view == 'photo_organizer':
        render_photo_organizer(case_id)
    elif selected_view == 'final':
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
