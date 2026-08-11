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


def inventory_selection_source(current_rows: list[dict], stock_rows: pd.DataFrame) -> pd.DataFrame:
    """기존 연결과 검색 재고를 한 편집표로 합친다."""
    rows: dict[int, dict] = {}
    for current in current_rows:
        inventory_id = int(current['source_inventory_id'])
        qty = safe_number(current['requested_qty'])
        if inventory_id in rows:
            rows[inventory_id]['보유수량'] += qty
            rows[inventory_id]['선택수량'] += qty
            continue
        rows[inventory_id] = {
            '_inventory_id': inventory_id,
            '_location': current.get('source_location') or current.get('location') or '',
            '_product_name': current.get('product_name') or '',
            '선택': True,
            '사업장': current.get('business_unit') or '',
            '제조번호': current.get('lot_no') or '',
            '유통기한': current.get('expiry_date') or '',
            '보유수량': qty,
            '선택수량': qty,
        }
    for _, stock in stock_rows.iterrows():
        inventory_id = int(stock['id'])
        available = safe_number(stock['qty'])
        if inventory_id in rows:
            rows[inventory_id]['보유수량'] += available
            continue
        rows[inventory_id] = {
            '_inventory_id': inventory_id,
            '_location': stock['location'] or '',
            '_product_name': stock['product_name'] or '',
            '선택': False,
            '사업장': stock['company'] or '',
            '제조번호': stock['lot'] or '',
            '유통기한': stock['exp_date'] or '',
            '보유수량': available,
            '선택수량': 0.0,
        }
    return pd.DataFrame(rows.values(), columns=[
        '_inventory_id', '_location', '_product_name', '선택', '사업장',
        '제조번호', '유통기한', '보유수량', '선택수량',
    ])


def saved_inventory_source(current_rows: list[dict]) -> pd.DataFrame:
    """이미 출고 저장된 실재고를 보유수량 없이 수정/삭제 가능한 표로 만든다."""
    return pd.DataFrame([
        {
            '_shipment_id': int(row['id']),
            '_inventory_id': int(row['source_inventory_id']),
            '_location': row.get('source_location') or row.get('location') or '',
            '_product_name': row.get('product_name') or '',
            '사업장': row.get('business_unit') or '',
            '제품명': row.get('product_name') or '',
            '제조번호': row.get('lot_no') or '',
            '유통기한': row.get('expiry_date') or '',
            '선택수량': safe_number(row.get('requested_qty')),
        }
        for row in current_rows
        if row.get('source_inventory_id')
    ])


def recommended_inventory_search_term(product_name: object) -> str:
    """주문 제품명의 첫 괄호 앞부분만 재고 추천 검색어로 사용한다."""
    return str(product_name or '').split('(', 1)[0].strip()


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
    st.title('수출대기 저장')
    st.caption('국내배송 단계까지 진행된 건도 선택해 주문과 실제 출고제품을 수정·저장할 수 있습니다.')

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
    try:
        restored_legacy_count = wms_link_service.restore_legacy_waiting_links(case_id)
    except ValueError as exc:
        restored_legacy_count = 0
        st.warning(str(exc))
    if restored_legacy_count:
        st.success(
            f'기존 WMS 수출대기(P 로케이션) 재고 {restored_legacy_count}개 행을 '
            '이 수출번호에 다시 연결했습니다.'
        )
    selected_case = next(case for case in cases if int(case['id']) == case_id)
    orders = order_service.list_for_case(case_id)
    all_linked_rows = shipment_service.list_case_items(case_id)
    linked_rows_by_order: dict[int, list] = {}
    for linked_row in all_linked_rows:
        linked_order_id = int(linked_row['order_item_id'])
        linked_rows_by_order.setdefault(linked_order_id, []).append(linked_row)

    unlinked_count = shipment_service.count_unlinked(case_id)
    if unlinked_count:
        with st.expander(f'구형 미연결 저장 데이터 {unlinked_count}개 정리'):
            legacy_rows = shipment_service.list_unlinked(case_id)
            st.dataframe(
                [
                    {
                        '사업장': row['business_unit'],
                        '실제 제품명': row['product_name'],
                        '제조번호': row['lot_no'],
                        '유통기한': row['expiry_date'],
                        '출고수량': row['requested_qty'],
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
                st.success('구형 미연결 저장 데이터를 삭제했습니다.')
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
        st.markdown('### 수출대기 저장제품')

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

            st.markdown('##### 저장된 재고')
            saved_source = saved_inventory_source(real_linked_current)
            if saved_source.empty:
                edited_saved = saved_source
                if not legacy_current:
                    st.info('아직 출고 저장된 재고가 없습니다.')
            else:
                edited_saved = st.data_editor(
                    saved_source,
                    hide_index=True,
                    use_container_width=True,
                    num_rows='dynamic',
                    disabled=['사업장', '제품명', '제조번호', '유통기한'],
                    column_order=['사업장', '제품명', '제조번호', '유통기한', '선택수량'],
                    column_config={
                        '_shipment_id': None,
                        '_inventory_id': None,
                        '_location': None,
                        '_product_name': None,
                        '선택수량': st.column_config.NumberColumn('선택수량', min_value=0, step=1, format='%g'),
                    },
                    key=f'saved_wms_editor_{case_id}_{selected_order_id}',
                )

            if legacy_current:
                legacy_view = pd.DataFrame([
                    {
                        '사업장': row.get('business_unit') or '',
                        '제품명': row.get('product_name') or '',
                        '제조번호': row.get('lot_no') or '',
                        '유통기한': row.get('expiry_date') or '',
                        '선택수량': safe_number(row.get('requested_qty')),
                    }
                    for row in legacy_current
                ])
                st.dataframe(legacy_view, hide_index=True, use_container_width=True)
                st.caption('위 행은 기존 저장 데이터입니다. WMS 재고 연결이 복원되면 수정 가능한 저장행으로 자동 전환됩니다.')

            saved_qty = (
                float(pd.to_numeric(edited_saved['선택수량'], errors='coerce').fillna(0).sum())
                if not edited_saved.empty else 0.0
            )
            legacy_qty = sum(safe_number(row.get('requested_qty')) for row in legacy_current)
            summary_slot = st.empty()

            st.markdown('##### 재고 선택')
            search_key = f'wms_pick_search_{case_id}_{selected_order_id}'
            recommended_search_term = recommended_inventory_search_term(selected_order_name)
            search_term = st.text_input(
                '제품 검색',
                value=st.session_state.get(search_key, recommended_search_term),
                key=search_key,
            ).strip()
            products_df = wms_inventory_picker_service.search_products(search_term)
            stock_rows = pd.DataFrame()
            editor_product = '새재고'
            if products_df.empty:
                st.info('일치하는 WMS 제품이 없습니다. 검색어를 바꿔 보세요.')
            else:
                picked_product = st.selectbox(
                    '추천 제품',
                    products_df['standard_name'].tolist(),
                    key=f'wms_pick_product_{case_id}_{selected_order_id}',
                )
                editor_product = picked_product
                stock_rows = wms_inventory_picker_service.product_stock_rows(picked_product)

            selection_source = inventory_selection_source([], stock_rows)
            edited_stock = st.data_editor(
                selection_source,
                hide_index=True,
                use_container_width=True,
                disabled=['사업장', '제조번호', '유통기한', '보유수량'],
                column_order=['선택', '사업장', '제조번호', '유통기한', '보유수량', '선택수량'],
                column_config={
                    '_inventory_id': None,
                    '_location': None,
                    '_product_name': None,
                    '선택': st.column_config.CheckboxColumn('선택'),
                    '보유수량': st.column_config.NumberColumn('보유수량', format='%g'),
                    '선택수량': st.column_config.NumberColumn('선택수량', min_value=0, step=1, format='%g'),
                },
                key=f'wms_pick_editor_{case_id}_{selected_order_id}_{editor_product}',
            )
            selected_stock = edited_stock[edited_stock['선택']].copy() if not edited_stock.empty else edited_stock
            added_qty = float(selected_stock['선택수량'].sum()) if not selected_stock.empty else 0.0
            preview_qty = saved_qty + legacy_qty + added_qty
            preview_icon, preview_state = order_state(order_qty, preview_qty)
            summary_slot.info(
                f'{preview_icon} 선택 합계 {fmt_number(preview_qty)} / '
                f'주문 {fmt_number(order_qty)} {unit} · {preview_state}'
            )
            packing_impact = shipment_service.packing_impact_for_order(case_id, selected_order_id)
            if packing_impact['packed_row_count']:
                st.caption(
                    f"패킹된 {packing_impact['packed_row_count']}개 행의 기존 CTN 번호는 "
                    '실재고 연결을 바꿔도 그대로 유지됩니다. 새로 담은 행만 미패킹 상태로 생성됩니다.'
                )

            if st.button(
                '출고 저장',
                type='primary',
                use_container_width=True,
                key=f'save_wms_link_{case_id}_{selected_order_id}',
            ):
                invalid_saved = edited_saved[
                    pd.to_numeric(edited_saved['선택수량'], errors='coerce').fillna(0) <= 0
                ] if not edited_saved.empty else edited_saved
                invalid_rows = selected_stock[
                    (selected_stock['선택수량'] <= 0)
                    | (selected_stock['선택수량'] > selected_stock['보유수량'])
                ] if not selected_stock.empty else selected_stock
                if not invalid_saved.empty:
                    st.error('저장된 재고의 선택수량은 1 이상이어야 합니다. 삭제하려는 행은 표에서 행 자체를 삭제하세요.')
                elif not selected_stock.empty and not invalid_rows.empty:
                    st.error('새로 선택한 재고의 선택수량은 1 이상, 보유수량 이하여야 합니다.')
                elif legacy_current:
                    st.error('WMS 재고 연결이 복원되지 않은 기존 저장행이 있어 안전하게 수정 저장할 수 없습니다. 표시된 기존 저장정보를 먼저 확인하세요.')
                else:
                    current_by_shipment_id = {int(row['id']): dict(row) for row in real_linked_current}
                    kept_rows = []
                    for _, row in edited_saved.iterrows():
                        shipment_id = int(row['_shipment_id'])
                        original = current_by_shipment_id.get(shipment_id)
                        if not original:
                            continue
                        item = dict(original)
                        item['requested_qty'] = float(row['선택수량'])
                        kept_rows.append(item)

                    picked_rows = [{
                        'inventory_id': int(row['_inventory_id']),
                        'company': row['사업장'],
                        'product_name': row['_product_name'],
                        'lot': row['제조번호'],
                        'exp_date': row['유통기한'],
                        'location': row['_location'],
                        'qty': float(row['선택수량']),
                    } for _, row in selected_stock.iterrows()]

                    # 같은 실재고를 다시 추가한 경우 새 행을 만들지 않고 기존 저장행 수량에 합산한다.
                    merged_picks = []
                    kept_by_inventory = {
                        int(row.get('source_inventory_id')): row
                        for row in kept_rows if row.get('source_inventory_id')
                    }
                    for pick in picked_rows:
                        existing = kept_by_inventory.get(int(pick['inventory_id']))
                        if existing is not None:
                            existing['requested_qty'] = safe_number(existing.get('requested_qty')) + safe_number(pick.get('qty'))
                        else:
                            merged_picks.append(pick)

                    try:
                        wms_link_service.save_picked_inventory(
                            case_id=case_id,
                            order_item_id=selected_order_id,
                            kept_rows=kept_rows,
                            picked_rows=merged_picks,
                        )
                    except ValueError as exc:
                        st.error(str(exc))
                    else:
                        folder_service.sync_case_folder(case_id)
                        history_service.add(
                            case_id,
                            '주문품목별 출고 저장',
                            f'{selected_order_name} · {fmt_number(preview_qty)} / {fmt_number(order_qty)} {unit}',
                        )
                        st.session_state['actual_packing_case_id'] = case_id
                        st.session_state['shipment_intake_success_message'] = (
                            '출고를 저장했습니다. 박스 패킹에 바로 반영됩니다.'
                        )
                        st.rerun()

        progress = intake_progress(orders, linked_rows_by_order)
        progress_ratio = progress['ratio']
        completed_item_count = progress['completed_count']
        order_item_count = progress['item_count']
        all_items_received = progress['all_received']

        st.divider()
        st.markdown('#### 전체 저장 진행률')
        st.progress(
            progress_ratio,
            text=(
                f'완료 품목 {completed_item_count} / {order_item_count}개 '
                f'({progress_ratio * 100:.1f}%)'
            ),
        )
        st.caption('각 주문품목의 저장률을 최대 100%로 계산한 뒤 품목별 저장률의 평균을 표시합니다.')
        if all_items_received:
            st.success('🎉 모든 주문품목이 각각 100% 저장되었습니다!')

    st.divider()
    with st.container():
        st.markdown('<div class="shipment-price-lookup-anchor"></div>', unsafe_allow_html=True)
        render_similar_price_lookup(key=f'shipment_price_lookup_query_{case_id}')