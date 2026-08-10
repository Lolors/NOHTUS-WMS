from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from nohtus.export_app.components.delivery_method_input import delivery_method_input, is_courier_delivery
from nohtus.export_app.components.editors import historical_box_editor, historical_order_editor, order_editor
from nohtus.export_app.config import TRANSPORT_MODES
from nohtus.export_app.services import export_service, folder_service, history_service, order_service
from nohtus.export_app.utils.numbering import next_export_no


HISTORICAL_ORDER_EDITOR_KEY = 'historical_order_items_table_v2'
FORM_VERSION_KEY = 'new_case_form_version'

FORM_KEYS = {
    'historical_export_date',
    'new_export_no',
    'new_country',
    'new_buyer',
    'new_transport',
    'new_note',
    'new_order_items',
    HISTORICAL_ORDER_EDITOR_KEY,
    'historical_box_items',
    'historical_delivery_method',
    'historical_tracking_no',
    'historical_driver_name',
    'historical_driver_phone',
    'historical_consignee_name',
    'historical_consignee_address',
    'create_case',
    'price_lookup_query',
}


def historical_order_source() -> pd.DataFrame:
    return pd.DataFrame([
        {
            '출고처': '',
            '제품명': '',
            '제조번호': '',
            '유효기간': '',
            '수량': 0.0,
            '단위': 'EA',
            '매입가': 0.0,
            'CTN 번호': 1,
        }
    ])


def safe_text(value: object, default: str = '') -> str:
    if value is None or pd.isna(value):
        return default
    text = str(value).strip()
    return default if text.casefold() in {'nan', 'none', '<na>'} else text


def safe_float(value: object, default: float = 0.0) -> float:
    if value is None or pd.isna(value):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value: object, default: int = 0) -> int:
    if value is None or pd.isna(value):
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def reset_new_case_form() -> None:
    for key in list(st.session_state):
        if (
            key in FORM_KEYS
            or any(key.startswith(f'{base_key}_') for base_key in FORM_KEYS)
            or key.startswith('new_order_items')
            or key.startswith('historical_box_items')
            or key.startswith('historical_order_')
        ):
            st.session_state.pop(key, None)
    st.session_state[FORM_VERSION_KEY] = (
        int(st.session_state.get(FORM_VERSION_KEY, 0)) + 1
    )


if st.session_state.pop('reset_new_case_form_pending', False):
    reset_new_case_form()


form_version = int(st.session_state.get(FORM_VERSION_KEY, 0))


def form_widget_key(base_key: str) -> str:
    return f'{base_key}_{form_version}'


def render_similar_price_lookup(*, key: str) -> None:
    st.markdown('#### 유사 제품 매입가 조회')
    query = st.text_input(
        '제품명 검색',
        key=key,
        placeholder='예: 리드카인 1% 10Am',
    ).strip()
    st.caption('공백·기호와 일부 표현 차이를 보정해 과거 매입가 이력을 찾습니다.')

    if not query:
        st.info('제품명을 입력하면 유사한 과거 매입가가 표시됩니다.')
        return

    similar_prices = order_service.find_similar_purchase_prices(query)
    if not similar_prices:
        st.info('유사한 제품명의 매입가 이력이 없습니다.')
        return

    history_df = pd.DataFrame([
        {
            '유사 제품명': item['product_name'],
            '매입가': item['purchase_price'],
            '수량': item['quantity'],
            '단위': item['unit'],
            '수출번호': item['export_no'],
            '바이어': item['buyer'] or '',
            '등록일': str(item['created_at'])[:10],
            '유사도': f"{item['similarity'] * 100:.0f}%",
        }
        for item in similar_prices
    ])
    st.dataframe(
        history_df,
        hide_index=True,
        use_container_width=True,
        column_config={
            '매입가': st.column_config.NumberColumn('매입가', format='₩ %,.0f'),
        },
    )


st.title('주문 입력')
st.caption('현재 진행 건은 주문목록을 등록하고, 과거 수출 건은 제품·CTN·국내배송 정보를 한 번에 저장합니다.')

if success_message := st.session_state.pop('new_case_success_message', None):
    st.success(success_message)

st.markdown(
    '''
    <style>
    div[data-testid="stVerticalBlock"] div[data-testid="stVerticalBlock"]:has(#new-case-basic-info-anchor) {
        width: 60vw;
        max-width: 60vw;
    }
    div[data-testid="stVerticalBlock"] div[data-testid="stVerticalBlock"]:has(#order-price-layout-anchor) {
        width: 70vw;
        max-width: 70vw;
    }
    div[data-testid="stVerticalBlock"] div[data-testid="stVerticalBlock"]:has(#historical-order-layout-anchor) {
        width: 80vw;
        max-width: 80vw;
    }
    div[data-testid="stHorizontalBlock"]:has(#create-case-button-anchor) {
        align-items: center;
        justify-content: center;
    }
    div[data-testid="stHorizontalBlock"]:has(#create-case-button-anchor) > div {
        display: flex;
        align-items: center;
        justify-content: center;
    }
    @media (max-width: 900px) {
        div[data-testid="stVerticalBlock"] div[data-testid="stVerticalBlock"]:has(#new-case-basic-info-anchor),
        div[data-testid="stVerticalBlock"] div[data-testid="stVerticalBlock"]:has(#order-price-layout-anchor),
        div[data-testid="stVerticalBlock"] div[data-testid="stVerticalBlock"]:has(#historical-order-layout-anchor) {
            width: 100%;
            max-width: 100%;
        }
    }
    </style>
    ''',
    unsafe_allow_html=True,
)

st.markdown('#### 수출 주문 등록')
case_type_label = st.radio(
    '등록 유형',
    ['현재 진행 건', '과거 수출 건'],
    horizontal=True,
    key='new_case_type',
)
is_historical = case_type_label == '과거 수출 건'

historical_date = None
if is_historical:
    historical_date = st.date_input(
        '과거 수출일',
        value=date.today(),
        help='수출번호의 연도와 폴더 연도를 결정하며, 국내배송 완료일로 저장됩니다.',
        key=form_widget_key('historical_export_date'),
    )
    export_no_preview = next_export_no('HIS', historical_date.year)
else:
    export_no_preview = next_export_no('EXP')

with st.container():
    st.markdown('<span id="new-case-basic-info-anchor"></span>', unsafe_allow_html=True)

    first_row = st.columns(3)
    first_row[0].text_input('수출번호', value=export_no_preview, disabled=True, key=form_widget_key('new_export_no'))
    country = first_row[1].text_input('국가 *', key=form_widget_key('new_country'))
    buyer = first_row[2].text_input('바이어 (선택)', key=form_widget_key('new_buyer'))

    second_row = st.columns(3)
    transport = second_row[0].selectbox('운송방식', TRANSPORT_MODES, key=form_widget_key('new_transport'))
    note = second_row[1].text_input('비고', key=form_widget_key('new_note'))

order_layout_anchor = (
    'historical-order-layout-anchor'
    if is_historical
    else 'order-price-layout-anchor'
)
with st.container():
    st.markdown(
        f'<span id="{order_layout_anchor}"></span>',
        unsafe_allow_html=True,
    )
    st.markdown('#### 주문 목록' if not is_historical else '#### 실출고 제품 및 CTN 연결')
    if is_historical:
        st.caption('엑셀에서 출고처·제품명·제조번호·유효기간·수량·단위·매입가·CTN 번호 순서로 복사해 표의 첫 셀에 붙여넣을 수 있습니다.')
        new_orders = historical_order_editor(
            historical_order_source(),
            key=form_widget_key(HISTORICAL_ORDER_EDITOR_KEY),
        )
    else:
        new_order_source = pd.DataFrame([{'제품명': '', '수량': 0.0, '단위': 'EA', '매입가': 0.0}])
        new_orders = order_editor(new_order_source, key=form_widget_key('new_order_items'))

    render_similar_price_lookup(key=form_widget_key('price_lookup_query'))

if is_historical:
    st.markdown('#### CTN 정보')
    box_source = pd.DataFrame([
        {'CTN 번호': 1, '가로 (cm)': 0.0, '세로 (cm)': 0.0, '높이 (cm)': 0.0, 'GW (kg)': 0.0}
    ])
    historical_boxes = historical_box_editor(box_source, key=form_widget_key('historical_box_items'))

    st.markdown('#### 국내배송 정보')
    receiver_cols = st.columns([1, 2])
    consignee_name = receiver_cols[0].text_input('수하인명', key=form_widget_key('historical_consignee_name'))
    consignee_address = receiver_cols[1].text_input('수하인주소', key=form_widget_key('historical_consignee_address'))
    delivery_method = delivery_method_input(
        key_prefix=form_widget_key('historical_delivery_method'),
    )
    if is_courier_delivery(delivery_method):
        tracking_no = st.text_input('송장번호', key=form_widget_key('historical_tracking_no'))
        driver_name = ''
        driver_phone = ''
    elif delivery_method == '퀵배송':
        delivery_cols = st.columns(2)
        driver_name = delivery_cols[0].text_input('배송기사 이름', key=form_widget_key('historical_driver_name'))
        driver_phone = delivery_cols[1].text_input('배송기사 연락처', key=form_widget_key('historical_driver_phone'))
        tracking_no = ''
    else:
        tracking_no = ''
        driver_name = ''
        driver_phone = ''
else:
    historical_boxes = pd.DataFrame()
    delivery_method = ''
    tracking_no = ''
    driver_name = ''
    driver_phone = ''
    consignee_name = ''
    consignee_address = ''

button_left, button_center, button_right = st.columns([4, 2, 4])
button_center.markdown('<span id="create-case-button-anchor"></span>', unsafe_allow_html=True)
create_case = button_center.button(
    '수출 건 생성',
    type='primary',
    key=form_widget_key('create_case'),
    use_container_width=True,
)

if create_case:
    valid_orders = []
    for _, row in new_orders.iterrows():
        product_name = safe_text(row.get('제품명'))
        if not product_name:
            continue
        quantity = safe_float(row.get('수량'))
        unit = safe_text(row.get('단위'), 'EA') or 'EA'
        purchase_price = safe_float(row.get('매입가'))
        if is_historical:
            ship_from = safe_text(row.get('출고처'))
            lot_no = safe_text(row.get('제조번호'))
            expiry_date = safe_text(row.get('유효기간'))
            box_no = safe_int(row.get('CTN 번호'))
            valid_orders.append((ship_from, product_name, unit, lot_no, expiry_date, quantity, purchase_price, box_no))
        else:
            valid_orders.append((product_name, quantity, unit, purchase_price))

    valid_boxes = []
    if is_historical:
        for _, row in historical_boxes.iterrows():
            box_no = safe_int(row.get('CTN 번호'))
            if box_no <= 0:
                continue
            valid_boxes.append((
                box_no,
                safe_float(row.get('가로 (cm)')),
                safe_float(row.get('세로 (cm)')),
                safe_float(row.get('높이 (cm)')),
                safe_float(row.get('GW (kg)')),
            ))

    if not country.strip():
        st.error('국가는 필수입니다.')
    elif not valid_orders:
        st.error('제품을 한 개 이상 입력하세요.')
    elif is_historical and any(item[7] <= 0 for item in valid_orders):
        st.error('모든 제품에 CTN 번호를 입력하세요.')
    elif is_historical and not valid_boxes:
        st.error('CTN 정보를 한 개 이상 입력하세요.')
    elif is_historical and not {item[7] for item in valid_orders}.issubset({box[0] for box in valid_boxes}):
        st.error('제품에 연결한 모든 CTN 번호의 규격과 GW를 입력하세요.')
    else:
        prefix = 'HIS' if is_historical else 'EXP'
        number_year = historical_date.year if historical_date else None
        export_no = next_export_no(prefix, number_year)
        case_type = 'historical' if is_historical else 'current'
        actual_ship_date = str(historical_date) if historical_date else ''
        stage = '국내배송' if is_historical else '주문 접수'
        status = '완료' if is_historical else '진행중'
        case_id = export_service.create_case(
            export_no=export_no,
            buyer=buyer,
            country=country,
            transport=transport,
            note=note,
            actual_ship_date=actual_ship_date,
            case_type=case_type,
            stage=stage,
            status=status,
        )
        if is_historical:
            order_service.create_historical_case_details(
                case_id,
                valid_orders,
                valid_boxes,
                method=delivery_method,
                actual_ship_date=actual_ship_date,
                tracking_no=tracking_no,
                driver_name=driver_name,
                driver_phone=driver_phone,
                consignee_name=consignee_name,
                consignee_address=consignee_address,
            )
        else:
            order_service.create_order_items(case_id, valid_orders)
        folder_service.sync_case_folder(case_id)
        history_detail = f'{export_no} / 제품 {len(valid_orders)}개'
        if is_historical:
            history_detail += f' / CTN {len(valid_boxes)}개 / {delivery_method} / {consignee_name}'
        history_service.add_history(case_id, '수출 건 생성', history_detail)
        st.session_state['order_case_id'] = case_id
        st.session_state['new_case_success_message'] = f'{export_no} 생성 완료'
        st.session_state['reset_new_case_form_pending'] = True
        st.rerun()
