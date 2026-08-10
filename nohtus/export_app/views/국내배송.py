from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from nohtus.export_app.components.case_selector import select_export_case
from nohtus.export_app.components.delivery_method_input import delivery_method_input, is_courier_delivery
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


st.title('국내배송')
st.caption('국내배송 방식, 수하인 정보와 송장 또는 배송기사 정보를 입력합니다.')

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
        consignee_name = receiver_cols[0].text_input('수하인명', value=case['consignee_name'] or '')
        consignee_address = receiver_cols[1].text_input('수하인주소', value=case['consignee_address'] or '')
        tracking = st.text_input('송장번호', value=case['tracking_no'] or '') if is_courier_delivery(method) else ''
        if method == '퀵배송':
            c1, c2 = st.columns(2)
            driver = c1.text_input('배송기사 이름', value=case['driver_name'] or '')
            phone = c2.text_input('연락처', value=case['driver_phone'] or '')
        else:
            driver = phone = ''

    submitted = st.form_submit_button('배송정보 저장 및 완료 처리', type='primary')

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
    folder = folder_service.sync_case_folder(case_id)
    history_service.add(case_id, '국내배송 완료', f'{method} / {consignee_name} / {folder}')
    st.success('저장했습니다.')
    st.rerun()
