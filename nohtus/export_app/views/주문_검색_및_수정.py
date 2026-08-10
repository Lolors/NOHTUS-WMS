from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from nohtus.config import COMPANIES
from nohtus.export_app.components.delivery_method_input import delivery_method_input, is_courier_delivery
from nohtus.export_app.components.editors import historical_box_editor, historical_order_editor, order_editor
from nohtus.export_app.config import TRANSPORT_MODES
from nohtus.export_app.services import export_confirm_service, export_service, folder_service, history_service, order_save_guard, order_service
from nohtus.export_app.services.case_merge_service import merge_case_into
from nohtus.export_app.services.order_edit_service import (
    box_items,
    date_value as dval,
    historical_items,
    number_value as num,
    optional_date_value as odval,
    save_historical,
    text_value as txt,
)
from nohtus.services.export_waiting import (
    cancel_export_waiting_order,
    confirm_export_waiting_items,
    update_confirmed_export_waiting_items,
)


def _company_selection_editor(source: pd.DataFrame, *, key_prefix: str) -> pd.DataFrame:
    """사업장 단위 빠른 선택을 지원하는 품목 체크 편집기."""
    selected_key = f'{key_prefix}_selected_ids'
    version_key = f'{key_prefix}_version'
    selected_ids = set(map(int, st.session_state.get(selected_key, [])))
    companies = [str(value) for value in source['출고사업장'].dropna().unique() if str(value).strip()]
    controls = st.columns(len(companies) + 1)
    for column, company in zip(controls, companies):
        company_ids = source.loc[source['출고사업장'].astype(str) == company, 'id'].astype(int).tolist()
        if column.button(f'{company} 전체 선택', use_container_width=True, key=f'{key_prefix}_select_{company}'):
            selected_ids.update(company_ids)
            st.session_state[selected_key] = sorted(selected_ids)
            st.session_state[version_key] = int(st.session_state.get(version_key, 0)) + 1
    if controls[-1].button('선택 해제', use_container_width=True, key=f'{key_prefix}_clear'):
        selected_ids.clear()
        st.session_state[selected_key] = []
        st.session_state[version_key] = int(st.session_state.get(version_key, 0)) + 1

    editor_source = source.copy()
    editor_source.insert(0, '선택', editor_source['id'].astype(int).isin(selected_ids))
    edited = st.data_editor(
        editor_source,
        hide_index=True,
        use_container_width=True,
        key=f'{key_prefix}_editor_{st.session_state.get(version_key, 0)}',
        disabled=[column for column in editor_source.columns if column != '선택'],
        column_config={'선택': st.column_config.CheckboxColumn('선택'), 'id': None},
    )
    st.session_state[selected_key] = edited.loc[edited['선택'] == True, 'id'].astype(int).tolist()  # noqa: E712
    return edited


def render_wms_confirmation_section(export_no: str) -> None:
    wms_orders = export_confirm_service.list_orders_for_export_no(export_no)
    if wms_orders.empty:
        return

    st.divider()
    st.markdown('### 실재고 수출확정')

    active_rows = wms_orders[wms_orders['status'].isin(['waiting', 'partial', 'confirmed'])]
    done_rows = wms_orders[~wms_orders['status'].isin(['waiting', 'partial', 'confirmed'])]

    if not done_rows.empty:
        st.caption(
            '이미 처리된 실재고 연결: '
            + ', '.join(f"{row['title']} ({row['status']})" for _, row in done_rows.iterrows())
        )

    if active_rows.empty:
        st.info('진행 중인 실재고 연결 건이 없습니다. 수출대기 저장에서 실재고를 먼저 연결하세요.')
        return
    if len(active_rows.index) > 1:
        st.error(
            '같은 수출번호에 진행 중인 실재고 연결 건이 여러 개입니다. '
            '주문 병합으로 하나로 합치거나, 별도 건에는 새 수출번호를 사용하세요.'
        )
        return

    order_id = int(active_rows.iloc[0]['id'])
    order_title = str(active_rows.iloc[0]['title'] or export_no)
    items = export_confirm_service.order_items(order_id)
    confirmed_count = int((items['confirmed'] == 1).sum()) if not items.empty else 0
    total_count = len(items)
    if total_count:
        st.progress(confirmed_count / total_count, text=f'{confirmed_count} / {total_count} 품목 확정')

    display_cols = ['출고사업장', '표준제품명', '출고사업장ERP명', 'LOT', '유통기한', '수량', '원래로케이션', '확정사업장', '확정매출처', '확정일시']
    st.dataframe(items[display_cols], hide_index=True, use_container_width=True)

    confirmed_items = items[items['confirmed'] == 1].copy() if not items.empty else pd.DataFrame()
    if not confirmed_items.empty:
        st.markdown('#### 확정 품목 매출·출고 등록 및 수정')
        st.caption(
            '확정 품목을 선택해 ERP 사업장·수출처·출고일자를 다시 저장할 수 있습니다. '
            '제품 교체나 수량 변경은 수출대기 저장에서 수정하면 기존 출고가 원복되고 새 품목이 수출대기로 전환됩니다.'
        )
        confirmed_source = confirmed_items[
            ['id', '출고사업장', '표준제품명', '출고사업장ERP명', 'LOT', '유통기한', '수량', '확정사업장', '확정매출처']
        ].copy()
        confirmed_edited = _company_selection_editor(
            confirmed_source,
            key_prefix=f'export_link_edit_confirmed_items_{order_id}_{confirmed_count}',
        )
        selected_confirmed = confirmed_edited[confirmed_edited['선택'] == True]  # noqa: E712
        selected_confirmed_ids = selected_confirmed['id'].astype(int).tolist()
        default_confirmed_company = str(confirmed_items.iloc[0]['확정사업장'] or '').replace('-', '')
        company_index = COMPANIES.index(default_confirmed_company) if default_confirmed_company in COMPANIES else 0
        edit_company = st.selectbox(
            '수정할 ERP 매출 사업장', COMPANIES, index=company_index,
            key=f'export_link_edit_company_{order_id}_{confirmed_count}',
        )
        edit_term = st.text_input(
            '수정할 ERP 수출 매출처 검색',
            placeholder='매출처명 일부를 입력하세요',
            key=f'export_link_edit_customer_term_{order_id}_{confirmed_count}',
        )
        edit_customers = export_confirm_service.customer_options(edit_company, edit_term)
        if not edit_customers.empty:
            edit_labels = [f"{str(row.customer_code or '').strip() or '-'} | {row.customer_name}" for row in edit_customers.itertuples()]
            edit_customer = edit_customers.iloc[edit_labels.index(st.selectbox(
                '수정할 ERP 수출 매출처', edit_labels,
                key=f'export_link_edit_customer_select_{order_id}_{confirmed_count}',
            ))]
            edit_ship_date = st.date_input(
                '수정할 출고일자',
                value=dval(active_rows.iloc[0]['order_date']),
                key=f'export_link_edit_order_date_{order_id}_{confirmed_count}',
            )
            if st.button(
                '선택 확정 품목 매출·출고 이력 수정',
                type='primary',
                disabled=not selected_confirmed_ids,
                key=f'export_link_edit_confirmed_{order_id}_{confirmed_count}',
            ):
                try:
                    update_confirmed_export_waiting_items(
                        order_id,
                        selected_confirmed_ids,
                        erp_company=edit_company,
                        customer_code=edit_customer['customer_code'],
                        customer_name=edit_customer['customer_name'],
                        shipment_date=edit_ship_date,
                    )
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    st.success(f'{len(selected_confirmed_ids)}개 확정 품목의 매출·출고 이력을 수정했습니다.')
                    st.rerun()
        else:
            st.warning('해당 사업장의 ERP 매출처가 없습니다.')

    cancel_key = f'confirm_wms_link_cancel_{order_id}'
    if st.session_state.get(cancel_key):
        st.warning('이미 확정된 품목은 유지되고, 아직 확정되지 않은 품목만 원래 위치로 복구됩니다.')
        no_col, yes_col = st.columns(2)
        with no_col:
            if st.button('취소하지 않기', use_container_width=True, key=f'wms_link_cancel_no_{order_id}'):
                st.session_state.pop(cancel_key, None)
                st.rerun()
        with yes_col:
            if st.button(
                '남은 실재고 연결을 원래 위치로 복구',
                type='primary',
                use_container_width=True,
                key=f'wms_link_cancel_yes_{order_id}',
            ):
                try:
                    cancel_export_waiting_order(order_id)
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    st.session_state.pop(cancel_key, None)
                    st.success(f'{order_title}의 남은 실재고 연결을 취소하고 원래 위치로 복구했습니다.')
                    st.rerun()
        return

    remaining_items = items[items['confirmed'] == 0].copy() if not items.empty else pd.DataFrame()
    if remaining_items.empty:
        st.success('이 실재고 연결 건의 모든 품목이 수출확정되었습니다.')
        return

    st.markdown('#### 선택 품목 수출확정')
    st.caption('아직 확정되지 않은 품목을 체크하고, ERP 매출 정보와 출고일자를 설정하세요.')
    selection_source = remaining_items[['id', '출고사업장', '표준제품명', '출고사업장ERP명', 'LOT', '유통기한', '수량', '원래로케이션']].copy()
    edited = _company_selection_editor(
        selection_source,
        key_prefix=f'export_link_confirm_items_{order_id}_{confirmed_count}',
    )
    selected_rows = edited[edited['선택'] == True] if not edited.empty else pd.DataFrame()  # noqa: E712
    selected_ids = selected_rows['id'].astype(int).tolist() if not selected_rows.empty else []
    selected_qty = int(selected_rows['수량'].sum()) if not selected_rows.empty else 0
    st.caption(f'선택: {len(selected_ids)}개 품목 / {selected_qty}EA')

    confirm_info_col, shipment_date_col = st.columns(2)
    with confirm_info_col:
        default_company = (
            str(selected_rows.iloc[0]['출고사업장'] or '')
            if not selected_rows.empty
            else str(remaining_items.iloc[0]['출고사업장'] or '')
        )
        default_index = COMPANIES.index(default_company) if default_company in COMPANIES else 0
        erp_company = st.selectbox(
            'ERP 매출 사업장',
            COMPANIES,
            index=default_index,
            key=f'export_link_confirm_company_{order_id}_{confirmed_count}',
        )
        term = st.text_input(
            'ERP 수출 매출처 검색',
            placeholder='매출처명 일부를 입력하세요',
            key=f'export_link_customer_term_{order_id}_{confirmed_count}',
        )
        customers = export_confirm_service.customer_options(erp_company, term)
        if customers.empty:
            st.warning('해당 사업장의 ERP 매출처가 없습니다. 거래처 관리에서 ERP 매출처 목록을 먼저 등록하거나 갱신하세요.')
            return
        labels = [f"{str(row.customer_code or '').strip() or '-'} | {row.customer_name}" for row in customers.itertuples()]
        customer = customers.iloc[
            labels.index(
                st.selectbox(
                    'ERP 수출 매출처',
                    labels,
                    key=f'export_link_customer_select_{order_id}_{confirmed_count}',
                )
            )
        ]
    with shipment_date_col:
        shipment_date = st.date_input(
            '출고일자',
            key=f'export_link_confirm_order_date_{order_id}_{confirmed_count}',
            help='이번에 선택한 품목에 적용할 출고일자를 선택하세요.',
        )

    action_col, cancel_link_col = st.columns([3, 1])
    with action_col:
        if st.button(
            '선택 품목 수출확정',
            type='primary',
            use_container_width=True,
            disabled=not selected_ids,
            key=f'export_link_confirm_{order_id}_{confirmed_count}',
        ):
            try:
                confirm_export_waiting_items(
                    order_id,
                    selected_ids,
                    erp_company=erp_company,
                    customer_code=customer['customer_code'],
                    customer_name=customer['customer_name'],
                    shipment_date=shipment_date,
                )
            except ValueError as exc:
                st.error(str(exc))
            else:
                st.success(f'{order_title}에서 {len(selected_ids)}개 품목 / {selected_qty}EA를 수출확정했습니다.')
                st.rerun()
    with cancel_link_col:
        if st.button('실재고 연결 취소', use_container_width=True, key=f'wms_link_cancel_open_{order_id}'):
            st.session_state[cancel_key] = True
            st.rerun()


def render() -> None:
    st.title('주문 검색 및 수정')

    if message := st.session_state.pop('order_cancel_success_message', None):
        st.success(message)

    cases=order_service.list_editable_cases()
    if not cases:
        st.info('수정할 수출 건이 없습니다.'); st.stop()

    cols=st.columns([2.2,1.4,1.8,1.5,2.5])
    today=date.today()
    period=cols[0].date_input('기간',value=(today-timedelta(days=30),today),key='editable_case_period')
    if isinstance(period,(tuple,list)) and len(period)==2:
        start_date,end_date=period
    else:
        start_date=end_date=period
    country_filter=cols[1].selectbox('국가',['전체']+sorted({txt(c['country']) for c in cases if txt(c['country'])}))
    buyer_filter=cols[2].selectbox('바이어',['전체']+sorted({txt(c['buyer']) for c in cases if txt(c['buyer'])}))
    transport_filter=cols[3].selectbox('운송방식',['전체']+sorted({txt(c['transport_mode']) for c in cases if txt(c['transport_mode'])}))
    query=cols[4].text_input('제품명 검색').strip().casefold()
    filtered=[]
    for c in cases:
        d=txt(c['actual_ship_date'])[:10] or txt(c['created_at'])[:10]
        try: case_date=date.fromisoformat(d)
        except ValueError: case_date=None
        if case_date is None or case_date<start_date or case_date>end_date: continue
        if country_filter!='전체' and txt(c['country'])!=country_filter: continue
        if buyer_filter!='전체' and txt(c['buyer'])!=buyer_filter: continue
        if transport_filter!='전체' and txt(c['transport_mode'])!=transport_filter: continue
        if query and query not in txt(c['product_names']).casefold(): continue
        filtered.append(c)
    if not filtered:
        st.warning('조건에 맞는 수출 건이 없습니다.'); st.stop()

    df=pd.DataFrame([{'_id':int(c['id']),'출고일자':txt(c['actual_ship_date'])[:10],'수출번호':c['export_no'],
        '국가':c['country'],'바이어':c['buyer'] or '','운송방식':c['transport_mode'],'단계':c['stage'],'주문제품':txt(c['product_names'])} for c in filtered])
    event=st.dataframe(df,hide_index=True,use_container_width=True,on_select='rerun',selection_mode='single-row',column_config={'_id':None},key='editable_case_table_v2')
    if not event.selection.rows:
        st.info('수정할 수출 건의 행을 선택하세요.'); st.stop()
    idx=int(event.selection.rows[0])
    if idx<0 or idx>=len(df): st.stop()
    case_id=int(df.iloc[idx]['_id']); case=next(c for c in filtered if int(c['id'])==case_id); detail=export_service.get_case(case_id)
    is_his=txt(case['export_no']).upper().startswith('HIS')

    st.divider()
    if is_his:
        st.markdown('### 과거 수출 건 수정')
        ship_date=st.date_input('과거 수출일',value=dval(detail['actual_ship_date']),key=f'his_date_{case_id}')
        a=st.columns(3)
        a[0].text_input('수출번호',value=case['export_no'],disabled=True,key=f'his_no_{case_id}')
        country=a[1].text_input('국가 *',value=case['country'],key=f'his_country_{case_id}')
        buyer=a[2].text_input('바이어 (선택)',value=case['buyer'] or '',key=f'his_buyer_{case_id}')
        b=st.columns(3); ti=TRANSPORT_MODES.index(case['transport_mode']) if case['transport_mode'] in TRANSPORT_MODES else 0
        transport=b[0].selectbox('운송방식',TRANSPORT_MODES,index=ti,key=f'his_transport_{case_id}')
        note=b[1].text_input('비고',value=case['note'] or '',key=f'his_note_{case_id}')
        st.markdown('#### 실출고 제품 및 CTN 연결')
        edited=historical_order_editor(historical_items(case_id),key=f'his_items_v2_{case_id}')
        st.markdown('#### CTN 정보'); boxes=historical_box_editor(box_items(case_id),key=f'his_boxes_v2_{case_id}')
        st.markdown('#### 국내배송 정보')
        r=st.columns([1,2]); consignee=r[0].text_input('수하인명',value=detail['consignee_name'] or '',key=f'his_consignee_{case_id}'); address=r[1].text_input('수하인주소',value=detail['consignee_address'] or '',key=f'his_address_{case_id}')
        saved_method=txt(detail['domestic_method'])
        method=delivery_method_input(saved_method=saved_method,key_prefix=f'his_method_{case_id}')
        if is_courier_delivery(method):
            tracking=st.text_input('송장번호',value=detail['tracking_no'] or '',key=f'his_tracking_{case_id}'); driver=phone=''
        elif method=='퀵배송':
            q=st.columns(2); driver=q[0].text_input('배송기사 이름',value=detail['driver_name'] or '',key=f'his_driver_{case_id}'); phone=q[1].text_input('배송기사 연락처',value=detail['driver_phone'] or '',key=f'his_phone_{case_id}'); tracking=''
        else:
            tracking=driver=phone=''
        if st.button('과거 수출 건 저장',type='primary',key=f'save_his_{case_id}'):
            if not country.strip(): st.error('국가는 필수입니다.')
            else:
                try: save_historical(case_id,edited,boxes,(country.strip(),buyer.strip(),transport,note.strip(),str(ship_date)),(method,tracking.strip(),driver.strip(),phone.strip(),consignee.strip(),address.strip()))
                except ValueError as e: st.error(str(e))
                else:
                    order_service.clear_editable_cases_cache(); folder_service.sync_case_folder(case_id); history_service.add_history(case_id,'과거 수출 건 전체 수정',f'{len(edited)}행'); st.success('저장했습니다.'); st.rerun()
    else:
        st.markdown('### 주문 수정')
        a=st.columns(4)
        country=a[0].text_input('국가 *',value=case['country'])
        buyer=a[1].text_input('바이어',value=case['buyer'] or '')
        ti=TRANSPORT_MODES.index(case['transport_mode']) if case['transport_mode'] in TRANSPORT_MODES else 0
        transport=a[2].selectbox('운송방식',TRANSPORT_MODES,index=ti)
        note=a[3].text_input('비고',value=case['note'] or '')
        date_row=st.columns(4)
        actual_ship_date=date_row[0].date_input(
            '출고일자',
            value=odval(detail['actual_ship_date']),
            key=f'current_ship_date_{case_id}',
        )
        if st.button('기본 정보 저장'):
            export_service.update_basic(
                case_id,
                country,
                buyer,
                transport,
                note,
                actual_ship_date=str(actual_ship_date) if actual_ship_date else '',
            )
            order_service.clear_editable_cases_cache()
            folder_service.sync_case_folder(case_id)
            st.rerun()
        existing=order_service.get_order_items_dataframe(case_id)
        if existing.empty: existing=pd.DataFrame([{'_id':None,'제품명':'','수량':0.0,'단위':'EA','매입가':0.0}])
        edited=order_editor(existing,key=f'orders_{case_id}')
        if st.button('주문 목록 저장',type='primary'):
            order_service.save_order_items(case_id,edited); folder_service.sync_case_folder(case_id); st.rerun()

    st.divider()
    action_left, action_right = st.columns([7, 3], gap='large')

    with action_left:
        st.markdown('#### 다른 주문으로 이관·병합')
        st.caption('현재 수출 건의 주문목록, 연결된 입고 상세정보와 CTN 정보를 대상 수출번호의 기존 내용에 추가한 뒤 현재 건을 취소합니다.')

        merge_targets = [
            candidate for candidate in cases
            if int(candidate['id']) != case_id and candidate['case_type'] == case['case_type']
        ]
        if merge_targets:
            target_by_label = {
                (
                    f"{candidate['export_no']} · {txt(candidate['country'], '-')} · "
                    f"{txt(candidate['buyer'], '바이어 미입력')} · {txt(candidate['stage'])}"
                ): int(candidate['id'])
                for candidate in merge_targets
            }
            merge_cols = st.columns([4, 3, 2])
            selected_target_label = merge_cols[0].selectbox(
                '병합할 대상 수출번호',
                list(target_by_label),
                key=f'merge_target_{case_id}',
            )
            target_case_id = target_by_label[selected_target_label]
            target_case = next(candidate for candidate in merge_targets if int(candidate['id']) == target_case_id)
            merge_confirm = merge_cols[1].checkbox(
                f"{case['export_no']} → {target_case['export_no']} 이관 확인",
                key=f'merge_confirm_{case_id}_{target_case_id}',
            )
            merge_clicked = merge_cols[2].button(
                '이관 후 취소',
                type='secondary',
                disabled=not merge_confirm,
                use_container_width=True,
                key=f'merge_case_{case_id}_{target_case_id}',
            )

            if merge_clicked:
                try:
                    result = merge_case_into(case_id, target_case_id)
                    order_service.clear_editable_cases_cache()
                    for folder_case_id in (target_case_id, case_id):
                        try:
                            folder_service.sync_case_folder(folder_case_id)
                        except OSError:
                            pass
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    # The target case may already have an intake-order editor draft in
                    # session state.  Its shipment rows are read directly from the DB,
                    # while that stale draft would hide the newly moved order rows.
                    order_save_guard.reset_intake_order_editor_state(target_case_id)
                    order_save_guard.reset_intake_order_editor_state(case_id)
                    for key in list(st.session_state):
                        if key in {'editable_case_table_v2', 'order_case_id'} or key.endswith(f'_{case_id}'):
                            st.session_state.pop(key, None)
                    st.session_state['order_cancel_success_message'] = (
                        f"{result['source_export_no']}의 주문 {result['order_count']}행과 "
                        f"입고 상세 {result['shipment_count']}행을 {result['target_export_no']}에 병합하고 "
                        '원본 주문을 취소했습니다.'
                    )
                    st.rerun()
        else:
            st.info('병합 대상으로 선택할 다른 수출 건이 없습니다.')

    with action_right:
        st.markdown('#### 주문 취소')
        st.caption('취소한 건은 목록에서 제외되고 기존 데이터는 보관됩니다.')
        cancel_confirm = st.checkbox(
            f"{case['export_no']} 주문 취소 확인",
            key=f'cancel_confirm_{case_id}',
        )
        cancel_order = st.button(
            '주문 취소',
            type='secondary',
            disabled=not cancel_confirm,
            use_container_width=True,
            key=f'cancel_order_{case_id}',
        )

        if cancel_order:
            export_service.cancel_case(case_id)
            order_service.clear_editable_cases_cache()
            history_service.add_history(case_id, '주문 취소', case['export_no'])
            try:
                folder_service.sync_case_folder(case_id)
            except OSError:
                pass
            for key in list(st.session_state):
                if key in {'editable_case_table_v2', 'order_case_id'} or key.endswith(f'_{case_id}'):
                    st.session_state.pop(key, None)
            st.session_state['order_cancel_success_message'] = f"{case['export_no']} 주문을 취소했습니다."
            st.rerun()
