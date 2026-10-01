from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

try:
    from st_keyup import st_keyup
except ImportError:
    st_keyup = None

from nohtus.export_app.components.case_selector import select_export_case
from nohtus.export_app.components.delivery_method_input import delivery_method_input, is_courier_delivery
from nohtus.export_app.components.streamlit_compat import dialog
from nohtus.export_app.services import delivery_service, export_service, folder_service, history_service, packing_service
from nohtus.export_app.utils.dates import parse_date
from nohtus.export_app.utils.formatters import fmt_number


def date_value(value: str | None):
    parsed = parse_date(value)
    return parsed.date() if parsed else date.today()


def render_packed_details(case_id: int) -> None:
    packed_rows = packing_service.list_packed_rows(case_id)
    st.markdown('### 패킹 완료 내역')

    if not packed_rows:
        st.info('표시할 패킹 완료 내역이 없습니다.')
        return

    rows = []
    seen_boxes: set[int] = set()
    total_qty = 0.0
    total_weight = 0.0

    for row in packed_rows:
        box_no = int(row['box_no'])
        first_box_row = box_no not in seen_boxes
        total_qty += float(row['requested_qty'] or 0)

        if first_box_row:
            total_weight += float(row['weight_kg'] or 0)
            seen_boxes.add(box_no)

        size_values = [row['length_cm'], row['width_cm'], row['height_cm']]
        box_size = (
            ' × '.join(fmt_number(value) for value in size_values) + ' cm'
            if first_box_row and all(float(value or 0) > 0 for value in size_values)
            else ('' if not first_box_row else '-')
        )
        rows.append({
            'CTN No.': f'CTN {box_no}' if first_box_row else '',
            '출고처': row['business_unit'] or '',
            '제품명': row['product_name'] or '',
            '제조번호': row['lot_no'] or '',
            '유통기한': row['expiry_date'] or '',
            '수량': float(row['requested_qty'] or 0),
            'GW (kg)': float(row['weight_kg'] or 0) if first_box_row else None,
            'CTN 사이즈': box_size,
        })

    st.dataframe(
        pd.DataFrame(rows),
        hide_index=True,
        use_container_width=True,
        column_config={
            '수량': st.column_config.NumberColumn('수량', format='%.0f'),
            'GW (kg)': st.column_config.NumberColumn('GW (kg)', format='%.2f'),
        },
    )
    st.caption(
        f'총 {len(seen_boxes)} CTN · 출고수량 {fmt_number(total_qty)} · 총중량 {fmt_number(total_weight)} kg'
    )


@dialog('주소록에서 선택', width='small')
def _address_book_dialog(case_id: int) -> None:
    query_key = f'address_book_query_{case_id}'
    if st_keyup is not None:
        query = st_keyup(
            '수하인명 검색',
            value=st.session_state.get(query_key, ''),
            key=query_key,
            placeholder='이름을 입력하면 실시간으로 검색됩니다',
            debounce=250,
        ) or ''
    else:
        query = st.text_input(
            '수하인명 검색',
            key=query_key,
            placeholder='이름을 입력하고 Enter를 누르면 검색됩니다',
        )
    entries = delivery_service.search_address_book(query)

    if not entries:
        st.info('일치하는 주소록 항목이 없습니다.' if query.strip() else '아직 저장된 수하인 정보가 없습니다.')
        return

    for index, entry in enumerate(entries):
        if st.button(
            f"{entry['name']} · {entry['address']}",
            key=f'address_book_pick_{case_id}_{index}',
            use_container_width=True,
        ):
            st.session_state[f'delivery_consignee_name_{case_id}'] = entry['name']
            st.session_state[f'delivery_consignee_address_{case_id}'] = entry['address']
            st.rerun()


def render() -> None:
    st.title('국내배송')
    st.caption('국내배송 방식, 수하인 정보와 송장 또는 배송기사 정보를 입력합니다.')
    if message := st.session_state.pop('delivery_save_message', None):
        st.success(message)
    if warning := st.session_state.pop('delivery_folder_warning', None):
        st.warning(warning)

    cases = [
        case for case in export_service.active_cases()
        if str(case['stage'] or '').strip() == '패킹 완료'
    ]
    if not cases:
        st.info('패킹 완료된 수출 건이 없습니다.')
        st.stop()

    case_id = select_export_case(
        cases,
        key_prefix='delivery_export_selector',
        saved_case_id=st.session_state.get('actual_packing_case_id'),
        show_stage=False,
    )
    case = export_service.get_case(case_id)

    render_packed_details(case_id)
    st.divider()

    saved_method = str(case['domestic_method'] or '').strip()
    method = delivery_method_input(
        saved_method=saved_method,
        key_prefix=f'delivery_method_{case_id}',
    )

    consignee_name_key = f'delivery_consignee_name_{case_id}'
    consignee_address_key = f'delivery_consignee_address_{case_id}'
    if consignee_name_key not in st.session_state:
        st.session_state[consignee_name_key] = case['consignee_name'] or ''
    if consignee_address_key not in st.session_state:
        st.session_state[consignee_address_key] = case['consignee_address'] or ''

    if method != '핸드캐리' and st.button('📇 주소록에서 선택'):
        _address_book_dialog(case_id)

    with st.form(f'delivery_{case_id}_{method}'):
        actual_date = st.date_input('국내배송 일자', value=date_value(case['actual_ship_date']))

        if method == '핸드캐리':
            consignee_name = ''
            consignee_address = ''
            tracking = ''
            driver = ''
            phone = ''
        else:
            receiver_cols = st.columns([1, 2])
            consignee_name = receiver_cols[0].text_input('수하인명', key=consignee_name_key)
            consignee_address = receiver_cols[1].text_input('수하인주소', key=consignee_address_key)
            tracking = st.text_input('송장번호', value=case['tracking_no'] or '') if is_courier_delivery(method) else ''
            if method == '퀵배송':
                c1, c2 = st.columns(2)
                driver = c1.text_input('배송기사 이름', value=case['driver_name'] or '')
                phone = c2.text_input('연락처', value=case['driver_phone'] or '')
            else:
                driver = phone = ''

        save_col, complete_col = st.columns(2)
        save_draft = save_col.form_submit_button('배송정보 저장', use_container_width=True)
        submitted = complete_col.form_submit_button('완료 처리', type='primary', use_container_width=True)

    if save_draft:
        delivery_service.save_delivery_draft(
            case_id,
            method=method,
            actual_ship_date=str(actual_date),
            tracking_no=tracking,
            driver_name=driver,
            driver_phone=phone,
            consignee_name=consignee_name,
            consignee_address=consignee_address,
        )
        st.session_state['delivery_save_message'] = '배송정보를 저장했습니다. (아직 완료 처리 전)'
        st.rerun()

    if submitted:
        delivery_service.save_delivery(
            case_id,
            method=method,
            actual_ship_date=str(actual_date),
            tracking_no=tracking,
            driver_name=driver,
            driver_phone=phone,
            consignee_name=consignee_name,
            consignee_address=consignee_address,
        )
        folder, folder_error = folder_service.try_sync_case_folder(case_id)
        folder_detail = str(folder) if folder else f'폴더 동기화 보류: {folder_error}'
        history_service.add(case_id, '국내배송 완료', f'{method} / {consignee_name} / {folder_detail}')
        st.session_state['delivery_save_message'] = '배송정보를 저장하고 완료 처리했습니다.'
        if folder_error:
            st.session_state['delivery_folder_warning'] = (
                '배송정보는 정상 저장됐지만 수출 폴더 이름 변경은 보류됐습니다. '
                f'폴더를 사용 중인 프로그램을 닫은 뒤 다시 동기화하세요: {folder_error}'
            )
        st.rerun()
