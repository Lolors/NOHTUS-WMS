from __future__ import annotations

import pandas as pd
import streamlit as st

from nohtus.export_app.components.case_selector import select_export_case
from nohtus.export_app.components.editors import order_editor
from nohtus.export_app.components.streamlit_compat import dialog
from nohtus.export_app.services import (
    export_service,
    folder_service,
    history_service,
    order_save_guard,
    order_service,
    shipment_service,
    wms_link_service,
    wms_inventory_picker_service,
)
from nohtus.export_app.utils.formatters import fmt_number


from nohtus.export_app.services.shipment_intake_view_service import (
    intake_progress,
    order_state,
    safe_number,
    sort_orders_for_intake,
)


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
        show_stage=False,
        show_transport=True,
        case_label='product_summary',
    )

    st.session_state['actual_packing_case_id'] = case_id

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
            real_linked_current = [row for row in current if row.get('source_inventory_id')]
            legacy_current = [row for row in current if not row.get('source_inventory_id')]

            st.markdown(f'**선택 주문:** {selected_order_name}')

            pending_key = f'wms_pick_pending_{case_id}_{selected_order_id}'
            removed_key = f'wms_pick_removed_{case_id}_{selected_order_id}'
            pending: list[dict] = st.session_state.setdefault(pending_key, [])
            removed_ids: set[int] = st.session_state.setdefault(removed_key, set())

            st.markdown('##### 이미 연결된 실재고')
            kept_rows = [row for row in real_linked_current if int(row['id']) not in removed_ids]
            if not kept_rows:
                st.caption('아직 연결된 실재고가 없습니다.')
            else:
                row_labels = {
                    (
                        f"{row['business_unit'] or '-'} · {row['product_name']} · "
                        f"{row['lot_no'] or '-'} · {row['expiry_date'] or '-'} · "
                        f"{fmt_number(safe_number(row['requested_qty']))}{unit}"
                    ): int(row['id'])
                    for row in kept_rows
                }
                st.dataframe(
                    pd.DataFrame([
                        {
                            '사업장': row['business_unit'] or '',
                            '실제 제품명': row['product_name'] or '',
                            '제조번호': row['lot_no'] or '',
                            '유통기한': row['expiry_date'] or '',
                            '출고수량': safe_number(row['requested_qty']),
                            '단위': unit,
                        }
                        for row in kept_rows
                    ]),
                    hide_index=True,
                    use_container_width=True,
                )
                rows_to_remove = st.multiselect(
                    '연결을 해제할 항목 선택',
                    list(row_labels),
                    key=f'wms_pick_remove_select_{case_id}_{selected_order_id}',
                )
                if st.button(
                    '선택한 연결 해제',
                    disabled=not rows_to_remove,
                    key=f'wms_pick_remove_apply_{case_id}_{selected_order_id}',
                ):
                    for label in rows_to_remove:
                        removed_ids.add(row_labels[label])
                    st.rerun()

            if legacy_current:
                st.caption(
                    f"실재고 연동 이전에 직접 입력된 값이 {len(legacy_current)}건 있습니다: "
                    + ', '.join(
                        f"{row['product_name']} {fmt_number(safe_number(row['requested_qty']))}{unit}"
                        for row in legacy_current
                    )
                    + '. 아래에서 실재고 연결을 저장하면 이 값은 새 연결로 대체됩니다.'
                )

            if pending:
                st.markdown('##### 새로 담은 실재고 (저장 전)')
                for index, item in enumerate(pending):
                    row_col, delete_col = st.columns([5, 1])
                    row_col.write(
                        f"{item['company']} · {item['product_name']} · LOT {item['lot']} · "
                        f"유통기한 {item['exp_date']} · {fmt_number(item['qty'])}{unit}"
                    )
                    if delete_col.button('삭제', key=f'wms_pick_remove_pending_{case_id}_{selected_order_id}_{index}'):
                        pending.pop(index)
                        st.rerun()

            preview_qty = sum(safe_number(row['requested_qty']) for row in kept_rows) + sum(
                item['qty'] for item in pending
            )
            preview_icon, preview_state = order_state(order_qty, preview_qty)
            st.info(
                f'{preview_icon} 담을 합계 {fmt_number(preview_qty)} / '
                f'주문 {fmt_number(order_qty)} {unit} · {preview_state}'
            )
            packing_impact = shipment_service.packing_impact_for_order(case_id, selected_order_id)
            if packing_impact['packed_row_count']:
                st.caption(
                    f"패킹된 {packing_impact['packed_row_count']}개 행의 기존 CTN 번호는 "
                    '실재고 연결을 바꿔도 그대로 유지됩니다. 새로 담은 행만 미패킹 상태로 생성됩니다.'
                )

            if not kept_rows:
                st.markdown('##### WMS 실재고에서 담기')
                search_key = f'wms_pick_search_{case_id}_{selected_order_id}'
                search_term = st.text_input(
                    '제품 검색',
                    value=st.session_state.get(search_key, selected_order_name),
                    key=search_key,
                ).strip()
                products_df = wms_inventory_picker_service.search_products(search_term)
                if products_df.empty:
                    st.info('일치하는 WMS 제품이 없습니다. 검색어를 바꿔 보세요.')
                else:
                    product_choices = products_df['standard_name'].tolist()
                    picked_product = st.selectbox(
                        '추천 제품',
                        product_choices,
                        key=f'wms_pick_product_{case_id}_{selected_order_id}',
                    )
                    expiry_choices = wms_inventory_picker_service.expiry_options(picked_product)
                    if not expiry_choices:
                        st.info(f'{picked_product}의 재고가 없습니다.')
                    else:
                        picked_expiry = st.selectbox(
                            '유통기한',
                            expiry_choices,
                            key=f'wms_pick_exp_{case_id}_{selected_order_id}_{picked_product}',
                        )
                        lot_choices = wms_inventory_picker_service.lot_options(picked_product, picked_expiry)
                        picked_lot = st.selectbox(
                            'LOT/제조번호',
                            lot_choices,
                            key=f'wms_pick_lot_{case_id}_{selected_order_id}_{picked_product}_{picked_expiry}',
                        )
                        stock_rows = wms_inventory_picker_service.resolve_stock_rows(
                            picked_product, picked_lot, picked_expiry
                        )
                        if stock_rows.empty:
                            st.info('선택한 조건의 재고가 없습니다.')
                        else:
                            if len(stock_rows) == 1:
                                stock_row = stock_rows.iloc[0]
                                st.caption(
                                    f"{stock_row['company']} / {stock_row['location']} / "
                                    f"현재고 {int(stock_row['qty'])}EA"
                                )
                            else:
                                stock_labels = [
                                    f"{r['company']} / {r['location']} / {int(r['qty'])}EA"
                                    for _, r in stock_rows.iterrows()
                                ]
                                stock_choice = st.selectbox(
                                    '사업장/위치',
                                    stock_labels,
                                    key=f'wms_pick_stock_{case_id}_{selected_order_id}',
                                )
                                stock_row = stock_rows.iloc[stock_labels.index(stock_choice)]
    
                            max_qty = int(stock_row['qty'])
                            pick_qty = st.number_input(
                                '담을 수량',
                                min_value=0,
                                max_value=max_qty,
                                step=1,
                                key=f'wms_pick_qty_{case_id}_{selected_order_id}',
                            )
                            if st.button(
                                '이 항목에 담기',
                                use_container_width=True,
                                disabled=pick_qty <= 0,
                                key=f'wms_pick_add_{case_id}_{selected_order_id}',
                            ):
                                pending.append({
                                    'inventory_id': int(stock_row['id']),
                                    'company': stock_row['company'],
                                    'product_name': picked_product,
                                    'lot': picked_lot,
                                    'exp_date': picked_expiry,
                                    'location': stock_row['location'],
                                    'qty': float(pick_qty),
                                })
                                st.rerun()

            if st.button(
                '실재고 연결 저장',
                type='primary',
                use_container_width=True,
                disabled=not pending and not removed_ids,
                key=f'save_wms_link_{case_id}_{selected_order_id}',
            ):
                try:
                    wms_link_service.save_picked_inventory(
                        case_id=case_id,
                        order_item_id=selected_order_id,
                        kept_rows=kept_rows,
                        picked_rows=pending,
                    )
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    folder_service.sync_case_folder(case_id)
                    history_service.add(
                        case_id,
                        '주문품목별 실재고 연결',
                        f'{selected_order_name} · {fmt_number(preview_qty)} / {fmt_number(order_qty)} {unit}',
                    )
                    st.session_state.pop(pending_key, None)
                    st.session_state.pop(removed_key, None)
                    st.session_state['actual_packing_case_id'] = case_id
                    st.session_state['shipment_intake_success_message'] = (
                        '실재고 연결을 저장했습니다. 박스 패킹에 바로 반영됩니다.'
                    )
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