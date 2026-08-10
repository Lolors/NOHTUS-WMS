from __future__ import annotations

import pandas as pd
import streamlit as st

from nohtus.export_app.components.case_selector import select_export_case
from nohtus.export_app.components.editors import order_editor, shipment_editor
from nohtus.export_app.components.streamlit_compat import dialog
from nohtus.export_app.services import (
    export_service,
    folder_service,
    history_service,
    order_save_guard,
    order_service,
    shipment_service,
    wms_import_service,
)
from nohtus.export_app.utils.formatters import fmt_number


from nohtus.export_app.services.shipment_intake_view_service import (
    find_product_name_mismatches,
    intake_progress,
    order_state,
    safe_number,
    sort_orders_for_intake,
)


def save_linked_order(
    *,
    case_id: int,
    selected_order_id: int,
    selected_order_name: str,
    preview_qty: float,
    order_qty: float,
    unit: str,
    values: list[dict],
) -> None:
    shipment_service.save_for_order(case_id, selected_order_id, values)
    st.session_state['actual_packing_case_id'] = case_id
    folder_service.sync_case_folder(case_id)
    history_service.add(
        case_id,
        '주문품목별 입고 저장',
        f'{selected_order_name} · {fmt_number(preview_qty)} / {fmt_number(order_qty)} {unit}',
    )
    st.session_state['shipment_intake_success_message'] = '저장했습니다. 박스 패킹에 바로 반영됩니다.'


@dialog('입력한 제품명을 확인해 주세요')
def product_name_warning_dialog(
    *,
    case_id: int,
    selected_order_id: int,
    selected_order_name: str,
    preview_qty: float,
    order_qty: float,
    unit: str,
    values: list[dict],
    mismatches: list[dict],
) -> None:
    st.warning('주문목록의 제품명과 크게 다른 입고 제품명이 있습니다.')
    st.dataframe(
        pd.DataFrame(mismatches),
        hide_index=True,
        use_container_width=True,
    )
    st.caption('다른 주문품목의 제품을 잘못 입력한 것이 아닌지 확인하세요.')

    confirm_col, cancel_col = st.columns(2)
    if confirm_col.button('그래도 저장', type='primary', use_container_width=True):
        try:
            save_linked_order(
                case_id=case_id,
                selected_order_id=selected_order_id,
                selected_order_name=selected_order_name,
                preview_qty=preview_qty,
                order_qty=order_qty,
                unit=unit,
                values=values,
            )
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.rerun()

    if cancel_col.button('돌아가서 수정', use_container_width=True):
        st.rerun()


@dialog('수출대기로 되돌리기')
def reopen_export_waiting_dialog(*, case_id: int, export_no: str) -> None:
    st.warning(f'{export_no}의 수출확정을 취소하고 수출대기 상태로 되돌립니다.')
    st.caption('저장된 주문·입고·CTN·국내배송 정보는 삭제되지 않습니다.')
    confirm_col, cancel_col = st.columns(2)
    if confirm_col.button('수출대기로 되돌리기', type='primary', use_container_width=True):
        try:
            export_service.reopen_for_export_waiting(case_id)
            folder_service.sync_case_folder(case_id)
            history_service.add(case_id, '수출확정 취소', '수출대기 상태로 되돌림')
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.session_state['shipment_intake_success_message'] = (
                f'{export_no}을(를) 수출대기 상태로 되돌렸습니다.'
            )
            st.rerun()

    if cancel_col.button('취소', use_container_width=True):
        st.rerun()


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


def render() -> None:
    st.title('수출대기 입고')
    st.caption('국내배송 단계까지 진행된 건도 선택해 주문과 실제 입고제품을 수정할 수 있습니다.')

    if success_message := st.session_state.pop('shipment_intake_success_message', None):
        st.success(success_message)

    st.markdown(
        '''
        <style>
        div[data-testid="stVerticalBlock"] div[data-testid="stVerticalBlock"]:has(.shipment-price-lookup-anchor) {
            width: 60vw;
            max-width: 60vw;
        }
        @media (max-width: 900px) {
            div[data-testid="stVerticalBlock"] div[data-testid="stVerticalBlock"]:has(.shipment-price-lookup-anchor) {
                width: 100%;
                max-width: 100%;
            }
        }
        .shipment-price-lookup-anchor {
            height: 0;
            margin: 0;
            padding: 0;
            overflow: hidden;
        }
        </style>
        ''',
        unsafe_allow_html=True,
    )

    cases = export_service.intake_editable_cases()
    if not cases:
        st.info('수정할 수 있는 수출 건이 없습니다.')
        st.stop()

    case_id = select_export_case(
        cases,
        key_prefix='shipment_export_selector',
        saved_case_id=st.session_state.get('actual_packing_case_id'),
    )

    st.session_state['actual_packing_case_id'] = case_id

    with st.expander('WMS 수출대기 불러오기', expanded=False):
        st.caption('같은 수출번호로 WMS 수출대기 등록에 올라온 사업장·제조번호·유통기한·수량을 그대로 불러옵니다.')
        if st.button(
            '같은 수출번호의 수출대기 조회',
            type='secondary',
            use_container_width=True,
            key=f'preview_wms_{case_id}',
        ):
            try:
                st.session_state[f'wms_preview_{case_id}'] = wms_import_service.preview(case_id)
            except Exception as exc:
                st.error(str(exc))

        wms_preview = st.session_state.get(f'wms_preview_{case_id}')
        if wms_preview:
            preview_rows = pd.DataFrame(wms_preview['rows'])
            if preview_rows.empty:
                st.info('WMS에 같은 수출번호로 등록된 수출대기 품목이 없습니다.')
            else:
                st.dataframe(
                    preview_rows.drop(columns=['_order_item_id'], errors='ignore'),
                    hide_index=True,
                    use_container_width=True,
                )
                unmatched_count = int((preview_rows['매칭상태'] != '일치').sum())
                if wms_preview['differences']:
                    st.warning('주문수량과 WMS 수출대기 수량이 다른 제품이 있습니다.')
                    st.dataframe(pd.DataFrame(wms_preview['differences']), hide_index=True, use_container_width=True)
                if unmatched_count:
                    st.error(f'주문제품과 자동 매칭되지 않은 WMS 품목이 {unmatched_count}개 있습니다. 제품명을 확인하세요.')
                if st.button(
                    'WMS 수출대기 내용 전체 불러오기',
                    type='primary',
                    use_container_width=True,
                    disabled=bool(unmatched_count),
                    key=f'apply_wms_{case_id}',
                ):
                    try:
                        imported = wms_import_service.apply(case_id)
                        folder_service.sync_case_folder(case_id)
                        history_service.add(
                            case_id,
                            'WMS 수출대기 불러오기',
                            f"{imported['row_count']}개 재고행 / {imported['order_count']}개 주문품목",
                        )
                        st.session_state.pop(f'wms_preview_{case_id}', None)
                        st.session_state['shipment_intake_success_message'] = 'WMS의 제조번호·유통기한·수량을 불러왔습니다.'
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))

    shipment_service.cleanup_invalid_links(case_id)
    selected_case = next(case for case in cases if int(case['id']) == case_id)
    if (
        str(selected_case['stage'] or '').strip() == '국내배송'
        and str(selected_case['status'] or '').strip() == '완료'
    ):
        action_col, _ = st.columns([1, 3])
        if action_col.button(
            '수출대기로 되돌리기',
            use_container_width=True,
            key=f'reopen_export_waiting_{case_id}',
        ):
            reopen_export_waiting_dialog(
                case_id=case_id,
                export_no=str(selected_case['export_no'] or '').strip() or '선택한 수출 건',
            )
    orders = order_service.list_for_case(case_id)
    all_linked_rows = shipment_service.list_case_items(case_id)
    linked_rows_by_order: dict[int, list] = {}
    for linked_row in all_linked_rows:
        linked_order_id = int(linked_row['order_item_id'])
        linked_rows_by_order.setdefault(linked_order_id, []).append(linked_row)

    unlinked_count = shipment_service.count_unlinked(case_id)
    if unlinked_count:
        with st.expander(f'구형 미연결 입고 데이터 {unlinked_count}개 정리'):
            legacy_rows = shipment_service.list_unlinked(case_id)
            st.dataframe(
                [
                    {
                        '사업장': row['business_unit'],
                        '실제 제품명': row['product_name'],
                        '제조번호': row['lot_no'],
                        '유통기한': row['expiry_date'],
                        '입고수량': row['requested_qty'],
                        '박스번호': row['box_no'],
                    }
                    for row in legacy_rows
                ],
                hide_index=True,
                use_container_width=True,
            )
            delete_confirmed = st.checkbox(
                '위 미연결 데이터를 삭제합니다.',
                key=f'delete_legacy_confirm_{case_id}',
            )
            if st.button(
                '구형 미연결 데이터 삭제',
                disabled=not delete_confirmed,
                key=f'delete_legacy_{case_id}',
            ):
                shipment_service.delete_unlinked(case_id)
                folder_service.sync_case_folder(case_id)
                history_service.add(case_id, '구형 미연결 입고 삭제', f'{unlinked_count}개 행')
                st.success('구형 미연결 입고 데이터를 삭제했습니다.')
                st.rerun()

    left, right = st.columns([1.05, 1.45], gap='large')

    with left:
        st.markdown('### 주문목록')
        st.caption('제품명·주문수량·단위·매입가를 수정한 뒤 저장할 수 있습니다.')

        draft_key = f'shipment_order_draft_{case_id}'
        version_key = f'shipment_order_editor_version_{case_id}'
        merge_message_key = f'shipment_order_merge_message_{case_id}'

        if merge_message := st.session_state.pop(merge_message_key, None):
            st.success(merge_message)

        if draft_key not in st.session_state:
            order_source = order_service.get_order_items_dataframe(case_id)
            if order_source.empty:
                order_source = pd.DataFrame([
                    {'_id': None, '제품명': '', '수량': 0.0, '단위': 'EA', '매입가': 0.0}
                ])
            st.session_state[draft_key] = order_save_guard.with_row_numbers(order_source)

        editor_version = int(st.session_state.get(version_key, 0))
        edited_orders = order_editor(
            st.session_state[draft_key],
            key=f'shipment_orders_{case_id}_{editor_version}',
        )
        numbered_orders = order_save_guard.with_row_numbers(
            edited_orders.drop(columns=['행번호'], errors='ignore')
        )
        duplicate_order_rows = order_save_guard.find_duplicate_rows(numbered_orders)

        if duplicate_order_rows:
            order_save_guard.render_duplicate_notice(duplicate_order_rows)
            st.markdown('**중복된 행끼리 수량을 합칠까요?**')
            st.caption('가장 먼저 생성된 행의 제품명·단위·매입가를 보존하고, 수량만 모두 더한 뒤 나중 행을 삭제합니다.')
            if st.button(
                '중복 행 수량 합치기',
                type='secondary',
                use_container_width=True,
                key=f'merge_duplicate_orders_{case_id}_{editor_version}',
            ):
                merged_orders = order_save_guard.merge_duplicate_rows(numbered_orders)
                st.session_state[draft_key] = merged_orders
                st.session_state[version_key] = editor_version + 1
                st.session_state[merge_message_key] = '중복 행을 합쳤습니다. 합산된 수량을 확인한 뒤 주문목록을 저장하세요.'
                st.rerun()

        st.caption('주문행을 삭제하고 저장하면 그 주문에 연결된 실제 출고제품도 함께 삭제됩니다.')

        if st.button(
            '주문목록 저장',
            type='primary',
            use_container_width=True,
            disabled=bool(duplicate_order_rows),
            key=f'save_shipment_orders_{case_id}',
        ):
            try:
                order_service.save_order_items(case_id, numbered_orders)
            except ValueError as exc:
                st.error(str(exc))
            else:
                st.session_state.pop(draft_key, None)
                st.session_state[version_key] = editor_version + 1
                folder_service.sync_case_folder(case_id)
                history_service.add(case_id, '출고 단계 주문목록 수정', f'{len(numbered_orders)}개 행')
                st.success('주문목록을 저장했습니다.')
                st.rerun()

    with right:
        st.markdown('### 실제 수출대기 입고제품')

        if not orders:
            st.info('왼쪽에서 주문목록을 입력하고 저장하세요.')
        else:
            sorted_orders = sort_orders_for_intake(orders, linked_rows_by_order)
            order_options: dict[str, int] = {}
            for order in sorted_orders:
                order_id = int(order['id'])
                order_qty = safe_number(order['quantity'])
                unit = str(order['unit'] or 'EA')
                current_rows = linked_rows_by_order.get(order_id, [])
                linked_qty = sum(safe_number(row['requested_qty']) for row in current_rows)
                icon, _ = order_state(order_qty, linked_qty)
                label = (
                    f"{icon} {order['product_name']} · "
                    f'{fmt_number(linked_qty)} / {fmt_number(order_qty)} {unit}'
                )
                order_options[label] = order_id

            selected_label = st.selectbox(
                '출고제품을 입력할 주문',
                list(order_options),
                key=f'linked_selected_order_{case_id}',
            )
            selected_order_id = order_options[selected_label]
            selected_order = next(
                order for order in sorted_orders
                if int(order['id']) == selected_order_id
            )
            selected_order_name = str(selected_order['product_name'] or '').strip()
            order_qty = safe_number(selected_order['quantity'])
            unit = str(selected_order['unit'] or 'EA')
            current = linked_rows_by_order.get(selected_order_id, [])

            st.markdown(f'**선택 주문:** {selected_order_name}')

            if current:
                source = pd.DataFrame([
                    {
                        '_id': int(row['id']),
                        '사업장': row['business_unit'] or '',
                        '실제 제품명': row['product_name'] or '',
                        '제조번호': row['lot_no'] or '',
                        '유통기한': row['expiry_date'] or '',
                        '출고수량': safe_number(row['requested_qty']),
                    }
                    for row in current
                ])
            else:
                source = pd.DataFrame([{
                    '_id': None,
                    '사업장': '',
                    '실제 제품명': '',
                    '제조번호': '',
                    '유통기한': '',
                    '출고수량': 0.0,
                }])

            edited = shipment_editor(source, key=f'linked_order_editor_v2_{case_id}_{selected_order_id}')
            preview_qty = sum(safe_number(value) for value in edited.get('출고수량', []))
            preview_icon, preview_state = order_state(order_qty, preview_qty)
            st.info(
                f'{preview_icon} 입력 합계 {fmt_number(preview_qty)} / '
                f'주문 {fmt_number(order_qty)} {unit} · {preview_state}'
            )
            packing_impact = shipment_service.packing_impact_for_order(case_id, selected_order_id)
            if packing_impact['packed_row_count']:
                st.caption(
                    f"패킹된 {packing_impact['packed_row_count']}개 행의 기존 CTN 번호는 "
                    '제품명·사업장·제조번호·유통기한을 수정해도 그대로 유지됩니다. '
                    '새로 추가한 행만 미패킹 상태로 생성됩니다.'
                )

            if st.button(
                '선택 주문품목 입고 저장',
                type='primary',
                use_container_width=True,
                key=f'save_linked_order_{case_id}_{selected_order_id}',
            ):
                values: list[dict] = []
                for _, row in edited.iterrows():
                    actual_name = str(row.get('실제 제품명', '') or '').strip()
                    quantity = safe_number(row.get('출고수량', 0))
                    has_any_value = any(
                        str(row.get(column, '') or '').strip()
                        for column in ['사업장', '실제 제품명', '제조번호', '유통기한']
                    ) or quantity > 0
                    if not has_any_value:
                        continue
                    values.append({
                        '_id': row.get('_id'),
                        'business_unit': row.get('사업장', ''),
                        'product_name': actual_name,
                        'lot_no': row.get('제조번호', ''),
                        'expiry_date': row.get('유통기한', ''),
                        'requested_qty': quantity,
                    })

                mismatches = find_product_name_mismatches(selected_order_name, values)
                if mismatches:
                    product_name_warning_dialog(
                        case_id=case_id,
                        selected_order_id=selected_order_id,
                        selected_order_name=selected_order_name,
                        preview_qty=preview_qty,
                        order_qty=order_qty,
                        unit=unit,
                        values=values,
                        mismatches=mismatches,
                    )
                else:
                    try:
                        save_linked_order(
                            case_id=case_id,
                            selected_order_id=selected_order_id,
                            selected_order_name=selected_order_name,
                            preview_qty=preview_qty,
                            order_qty=order_qty,
                            unit=unit,
                            values=values,
                        )
                    except ValueError as exc:
                        st.error(str(exc))
                    else:
                        st.rerun()

        progress = intake_progress(orders, linked_rows_by_order)
        progress_ratio = progress['ratio']
        completed_item_count = progress['completed_count']
        order_item_count = progress['item_count']
        all_items_received = progress['all_received']

        st.divider()
        st.markdown('#### 전체 입고 진행률')
        st.progress(
            progress_ratio,
            text=(
                f'완료 품목 {completed_item_count} / {order_item_count}개 '
                f'({progress_ratio * 100:.1f}%)'
            ),
        )
        st.caption('각 주문품목의 입고율을 최대 100%로 계산한 뒤 품목별 입고율의 평균을 표시합니다.')
        if all_items_received:
            st.success('🎉 모든 주문품목이 각각 100% 입고되었습니다!')

    st.divider()
    with st.container():
        st.markdown('<div class="shipment-price-lookup-anchor"></div>', unsafe_allow_html=True)
        render_similar_price_lookup(key=f'shipment_price_lookup_query_{case_id}')