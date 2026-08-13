from __future__ import annotations

import pandas as pd
import streamlit as st

from nohtus.export_app.components.case_selector import select_export_case
from nohtus.export_app.components.streamlit_compat import dialog
from nohtus.export_app import db
from nohtus.export_app.services import export_service, history_service, packing_edit_service, packing_service
from nohtus.export_app.utils.dates import now_text
from nohtus.export_app.services.packing_view_service import (
    expand_same_product_selection,
    filter_packing_items,
    items_by_box,
    packing_summary,
    product_summary,
)
from nohtus.export_app.utils.formatters import fmt_number


def sync_grid_checkbox_selection(
    widget_key: str,
    selection_key: str,
    version_key: str,
    row_ids: list[int],
) -> None:
    editor_state = st.session_state.get(widget_key, {})
    edited_rows = editor_state.get('edited_rows', {}) if isinstance(editor_state, dict) else {}
    selected_ids = {int(item_id) for item_id in st.session_state.get(selection_key, [])}

    for row_index, changes in edited_rows.items():
        index = int(row_index)
        if index < 0 or index >= len(row_ids) or '선택' not in changes:
            continue
        item_id = int(row_ids[index])
        if bool(changes['선택']):
            selected_ids.add(item_id)
        else:
            selected_ids.discard(item_id)

    st.session_state[selection_key] = sorted(selected_ids)
    st.session_state[version_key] = int(st.session_state.get(version_key, 0)) + 1


@db.backup_batch
def assign_repeated_ctns(
    case_id: int,
    item_id: int,
    *,
    quantity_per_box: int,
    length_cm: float,
    width_cm: float,
    height_cm: float,
    weight_kg: float,
) -> list[dict]:
    item = db.row(
        """SELECT id, case_id, order_item_id, business_unit, location, product_name,
                  lot_no, expiry_date, requested_qty, box_no, created_at
           FROM shipment_items
           WHERE id=? AND case_id=?""",
        (item_id, case_id),
    )
    if item is None:
        raise ValueError('선택한 실제 출고제품을 찾을 수 없습니다.')
    if item['box_no'] is not None:
        raise ValueError('이미 CTN에 담긴 제품은 반복 담기를 할 수 없습니다.')

    total_quantity = int(float(item['requested_qty'] or 0))
    if total_quantity <= 0:
        raise ValueError('남은 출고수량이 없습니다.')
    if quantity_per_box <= 0:
        raise ValueError('CTN당 수량은 1개 이상이어야 합니다.')

    full_count, remainder = divmod(total_quantity, quantity_per_box)
    quantities = [quantity_per_box] * full_count
    if remainder:
        quantities.append(remainder)
    if not quantities:
        quantities = [total_quantity]

    first_box_no = packing_service.next_box_no(case_id)
    target_box_numbers = [first_box_no + offset for offset in range(len(quantities))]
    placeholders = ','.join('?' for _ in target_box_numbers)
    occupied = db.rows(
        f'SELECT box_no FROM boxes WHERE case_id=? AND box_no IN ({placeholders})',
        (case_id, *target_box_numbers),
    )
    if occupied:
        raise ValueError('생성 예정 CTN 번호 중 이미 사용 중인 번호가 있습니다. 화면을 새로고침한 뒤 다시 시도하세요.')

    now = now_text()
    preview_rows: list[dict] = []
    for index, (box_no, quantity) in enumerate(zip(target_box_numbers, quantities)):
        is_remainder = remainder > 0 and index == len(quantities) - 1
        box_weight = 0.0 if is_remainder else float(weight_kg)
        db.execute(
            """INSERT INTO boxes(
                   case_id, box_no, length_cm, width_cm, height_cm, weight_kg, updated_at
               ) VALUES (?,?,?,?,?,?,?)""",
            (case_id, box_no, length_cm, width_cm, height_cm, box_weight, now),
        )

        if index == 0:
            db.execute(
                'UPDATE shipment_items SET requested_qty=?,box_no=?,updated_at=? WHERE id=? AND case_id=?',
                (quantity, box_no, now, item_id, case_id),
            )
        else:
            db.execute(
                """INSERT INTO shipment_items(
                       case_id, order_item_id, business_unit, location, product_name,
                       lot_no, expiry_date, requested_qty, box_no, created_at, updated_at
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    case_id,
                    item['order_item_id'],
                    item['business_unit'],
                    item['location'],
                    item['product_name'],
                    item['lot_no'],
                    item['expiry_date'],
                    quantity,
                    box_no,
                    item['created_at'] or now,
                    now,
                ),
            )

        preview_rows.append({
            'box_no': box_no,
            'quantity': quantity,
            'is_remainder': is_remainder,
            'weight_kg': box_weight,
        })

    packing_service._sync_packing_stage(case_id, now)
    return preview_rows


@dialog('프리셋 관리', width='small')
def box_preset_management_dialog(case_id: int) -> None:
    presets = packing_service.list_box_presets()

    st.markdown('#### 새 프리셋 추가')
    preset_name = st.text_input('프리셋 이름', key=f'manual_preset_name_{case_id}')
    add_cols = st.columns(2)
    preset_length = add_cols[0].number_input('가로(cm)', min_value=0, step=1, format='%d', key=f'manual_preset_length_{case_id}')
    preset_width = add_cols[1].number_input('세로(cm)', min_value=0, step=1, format='%d', key=f'manual_preset_width_{case_id}')
    preset_height = add_cols[0].number_input('높이(cm)', min_value=0, step=1, format='%d', key=f'manual_preset_height_{case_id}')
    preset_weight = add_cols[1].number_input('무게(kg)', min_value=0, step=1, format='%d', key=f'manual_preset_weight_{case_id}')
    if st.button('새 프리셋 추가', use_container_width=True):
        try:
            packing_service.save_box_preset(
                preset_name,
                preset_length,
                preset_width,
                preset_height,
                preset_weight,
            )
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.success(f'{preset_name.strip()} 프리셋을 추가했습니다.')
            st.rerun()

    st.divider()
    st.markdown('#### 기존 프리셋 수정·삭제')
    managed_name = st.selectbox(
        '관리할 프리셋', ['선택해주세요'] + sorted(presets),
        key=f'manage_box_preset_{case_id}',
    )
    if managed_name not in presets:
        return

    managed = presets[managed_name]
    edited_name = st.text_input('프리셋 이름 수정', value=managed_name, key=f'edit_box_preset_name_{case_id}_{managed_name}')
    edit_cols = st.columns(2)
    edit_length = edit_cols[0].number_input('길이(cm)', min_value=0, value=int(managed['length_cm']), step=1, format='%d', key=f'edit_box_preset_length_{case_id}_{managed_name}')
    edit_width = edit_cols[1].number_input('너비(cm)', min_value=0, value=int(managed['width_cm']), step=1, format='%d', key=f'edit_box_preset_width_{case_id}_{managed_name}')
    edit_height = edit_cols[0].number_input('높이(cm)', min_value=0, value=int(managed['height_cm']), step=1, format='%d', key=f'edit_box_preset_height_{case_id}_{managed_name}')
    edit_weight = edit_cols[1].number_input('GW(kg)', min_value=0, value=int(managed['weight_kg']), step=1, format='%d', key=f'edit_box_preset_weight_{case_id}_{managed_name}')
    manage_cols = st.columns(2)
    if manage_cols[0].button('프리셋 수정', type='primary', use_container_width=True, key=f'update_box_preset_{case_id}_{managed_name}'):
        try:
            packing_service.save_box_preset(edited_name, edit_length, edit_width, edit_height, edit_weight)
            if edited_name.strip() != managed_name:
                packing_service.delete_box_preset(managed_name)
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.session_state.pop(f'manage_box_preset_{case_id}', None)
            st.success('프리셋을 수정했습니다.')
            st.rerun()
    if manage_cols[1].button('프리셋 삭제', use_container_width=True, key=f'delete_box_preset_{case_id}_{managed_name}'):
        packing_service.delete_box_preset(managed_name)
        st.session_state.pop(f'manage_box_preset_{case_id}', None)
        st.session_state.pop(f'box_preset_select_{case_id}', None)
        st.rerun()


def render() -> None:
    st.title('박스 패킹')
    st.markdown(
        """
        <style>
        div[data-testid="stDataEditor"] {
            font-size: 0.76rem;
        }
        div[data-testid="stDataEditor"] [role="columnheader"],
        div[data-testid="stDataEditor"] [role="gridcell"] {
            font-size: 0.76rem !important;
            padding-left: 3px !important;
            padding-right: 3px !important;
        }
        div[data-testid="stMetric"] label,
        div[data-testid="stMetric"] [data-testid="stMetricLabel"] {
            display:flex !important;
            justify-content:center !important;
            width:100% !important;
            text-align:center !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.caption('미패킹 제품을 빠르게 선택해 현재 CTN에 담고, 오른쪽에서 CTN 정보와 관리 작업을 처리합니다.')

    cases = [
        case for case in export_service.active_cases()
        if str(case['stage'] or '').strip() != '국내배송'
        and str(case['stage'] or '').strip() in {'패킹 대기', '패킹 완료'}
    ]
    if not cases:
        st.info('패킹 대기 또는 패킹 완료 단계인 수출 건이 없습니다.')
        st.stop()

    case_id = select_export_case(
        cases,
        key_prefix='packing_export_selector',
        saved_case_id=st.session_state.get('actual_packing_case_id'),
        show_stage=False,
        show_transport=True,
        case_label='product_summary',
    )
    st.session_state['actual_packing_case_id'] = case_id

    items = packing_service.list_items(case_id)
    if not items:
        st.warning('연결된 입고 제품이 없습니다. 먼저 수출대기 입고에서 제품을 입력하세요.')
        st.stop()

    summary = packing_summary(items)
    boxes = packing_service.list_boxes(case_id)
    items_grouped_by_box = items_by_box(items)
    next_box_no = packing_service.next_box_no(case_id)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric('실제 출고 행', f"{summary['row_count']}개")
    m2.metric('총 출고수량', fmt_number(summary['total_quantity']))
    m3.metric('미패킹 행', f"{summary['unpacked_count']}개")
    m4.metric('사용 CTN', f"{summary['box_count']}개")

    active_label_key = f'packing_active_ctn_{case_id}'
    pending_active_key = f'pending_{active_label_key}'
    box_labels = [f"CTN {int(box['box_no'])}" for box in boxes]
    new_box_label = f'새 CTN {next_box_no}'
    active_options = [*box_labels, new_box_label]
    pending_active = st.session_state.pop(pending_active_key, None)
    if pending_active in active_options:
        st.session_state[active_label_key] = pending_active
    elif st.session_state.get(active_label_key) not in active_options:
        st.session_state[active_label_key] = new_box_label

    left_column, right_column = st.columns([5.6, 4.4], gap='large')

    # 오른쪽을 먼저 실행해 왼쪽 배정 버튼이 현재 CTN 번호를 바로 사용하게 합니다.
    with right_column:
        st.markdown('### 현재 CTN')
        active_label = st.selectbox('작업할 CTN', active_options, key=active_label_key)
        active_box_no = int(active_label.split()[-1])
        active_box = next((box for box in boxes if int(box['box_no']) == active_box_no), None)
        active_items = items_grouped_by_box.get(active_box_no, [])

        st.caption(
            f'CTN {active_box_no} · {len(active_items)}개 행 · '
            f'수량 {fmt_number(sum(float(item["requested_qty"] or 0) for item in active_items))}'
        )
        if active_items:
            active_item_rows = [
                {
                    '빼기': False,
                    '_id': int(item['id']),
                    '제품명': item['product_name'],
                    '제조번호': item['lot_no'],
                    '유통기한': item['expiry_date'],
                    '수량': float(item['requested_qty'] or 0),
                }
                for item in active_items
            ]
            edited_active_items = st.data_editor(
                pd.DataFrame(active_item_rows),
                hide_index=True,
                use_container_width=True,
                height=min(300, 70 + len(active_items) * 35),
                disabled=['_id', '제품명', '제조번호', '유통기한', '수량'],
                column_config={
                    '빼기': st.column_config.CheckboxColumn('빼기', width=46),
                    '_id': None,
                    '제품명': st.column_config.TextColumn('제품명', width=150),
                    '제조번호': st.column_config.TextColumn('제조번호', width=82),
                    '유통기한': st.column_config.TextColumn('유통기한', width=82),
                    '수량': st.column_config.NumberColumn('수량', format='%.0f', width=62),
                },
                key=f'active_ctn_items_{case_id}_{active_box_no}',
            )
            remove_item_ids = [
                int(row['_id'])
                for _, row in edited_active_items.iterrows()
                if bool(row['빼기'])
            ]
        else:
            remove_item_ids = []
            st.info('왼쪽에서 제품을 선택해 이 CTN에 담으세요.')

        _remove_space_left, remove_button_col, _remove_space_right = st.columns([1, 1.4, 1])
        with remove_button_col:
            if st.button(
                f'↩ 박스에서 빼기 ({len(remove_item_ids)})',
                use_container_width=True,
                disabled=not remove_item_ids,
                key=f'remove_active_ctn_items_{case_id}_{active_box_no}',
                help='표에서 체크한 제품을 현재 박스에서 빼기',
            ):
                packing_service.unassign_items(case_id, remove_item_ids)
                history_service.add(
                    case_id,
                    'CTN 배정 해제',
                    f'CTN {active_box_no}에서 {len(remove_item_ids)}개 실제 출고 행 제거',
                )
                st.success(f'{len(remove_item_ids)}개 제품을 CTN {active_box_no}에서 뺐습니다.')
                st.rerun()

        if active_box is not None:
            dimension_keys = {
                'length_cm': f'ctn_length_{case_id}_{active_box_no}',
                'width_cm': f'ctn_width_{case_id}_{active_box_no}',
                'height_cm': f'ctn_height_{case_id}_{active_box_no}',
                'weight_kg': f'ctn_weight_{case_id}_{active_box_no}',
            }
            pending_values_key = f'pending_ctn_values_{case_id}_{active_box_no}'
            active_values_key = f'active_box_values_{case_id}'

            if pending_values_key in st.session_state:
                pending_values = st.session_state.pop(pending_values_key)
                for field, key in dimension_keys.items():
                    st.session_state[key] = float(pending_values[field])
            with st.form(f'current_ctn_form_{case_id}_{active_box_no}'):
                dimension_columns = st.columns(4)
                length = dimension_columns[0].number_input(
                    '가로(cm)', min_value=0.0, value=float(active_box['length_cm'] or 0), key=dimension_keys['length_cm']
                )
                width = dimension_columns[1].number_input(
                    '세로(cm)', min_value=0.0, value=float(active_box['width_cm'] or 0), key=dimension_keys['width_cm']
                )
                height = dimension_columns[2].number_input(
                    '높이(cm)', min_value=0.0, value=float(active_box['height_cm'] or 0), key=dimension_keys['height_cm']
                )
                weight = dimension_columns[3].number_input(
                    'GW(kg)', min_value=0.0, value=float(active_box['weight_kg'] or 0), key=dimension_keys['weight_kg']
                )
                save_box = st.form_submit_button('CTN 저장 후 다음 CTN', type='primary', use_container_width=True)

            if save_box:
                packing_service.update_box(int(active_box['id']), length, width, height, weight)
                packing_service.save_last_box_values(length, width, height, weight)
                current_values = {
                    'length_cm': float(length), 'width_cm': float(width),
                    'height_cm': float(height), 'weight_kg': float(weight),
                }
                st.session_state[active_values_key] = current_values
                history_service.add(case_id, 'CTN 정보 수정', f'CTN {active_box_no}')
                current_index = box_labels.index(f'CTN {active_box_no}')
                if current_index + 1 < len(box_labels):
                    next_label = box_labels[current_index + 1]
                else:
                    next_label = new_box_label
                st.session_state[pending_active_key] = next_label
                st.success(f'CTN {active_box_no}을 저장했습니다.')
                st.rerun()

        else:
            st.caption('제품을 담으면 규격·GW 입력과 복제 기능이 활성화됩니다.')

        st.divider()
        st.markdown('#### 박스 프리셋')
        presets = packing_service.list_box_presets()
        last_values = packing_service.get_last_box_values()
        preset_save_col, _preset_save_space = st.columns([1, 1])
        with preset_save_col:
            st.markdown('###### 현재 규격을 프리셋으로 저장')
            preset_name = st.text_input('프리셋 이름', key=f'new_preset_name_{case_id}')
            if st.button('현재 규격 프리셋 저장', use_container_width=True, disabled=active_box is None):
                try:
                    packing_service.save_box_preset(
                        preset_name,
                        float(st.session_state.get(f'ctn_length_{case_id}_{active_box_no}', 0)),
                        float(st.session_state.get(f'ctn_width_{case_id}_{active_box_no}', 0)),
                        float(st.session_state.get(f'ctn_height_{case_id}_{active_box_no}', 0)),
                        float(st.session_state.get(f'ctn_weight_{case_id}_{active_box_no}', 0)),
                    )
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    st.success(f'{preset_name.strip()} 프리셋을 저장했습니다.')
                    st.rerun()

        preset_options = ['선택 안 함'] + (['마지막 사용값'] if last_values else []) + sorted(presets)
        preset_select_col, preset_manage_col = st.columns([7, 3])
        preset_select_key = f'box_preset_select_{case_id}'

        def apply_selected_preset() -> None:
            if active_box is None:
                return
            chosen = st.session_state.get(preset_select_key)
            values = last_values if chosen == '마지막 사용값' else presets.get(chosen)
            if values is None:
                return
            st.session_state[f'pending_ctn_values_{case_id}_{active_box_no}'] = values
            st.session_state[f'active_box_values_{case_id}'] = values

        selected_preset = preset_select_col.selectbox(
            '프리셋', preset_options, key=preset_select_key,
            on_change=apply_selected_preset,
        )
        preset_manage_col.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        if preset_manage_col.button('프리셋 관리', use_container_width=True, key=f'open_box_preset_manage_{case_id}'):
            box_preset_management_dialog(case_id)
        st.divider()
        box_manage_left, box_manage_middle, box_manage_right = st.columns(3, gap='large')
        with box_manage_left:
            if active_box is not None:
                st.markdown('##### 박스 번호 변경')
                with st.form(f'rename_ctn_{case_id}_{active_box_no}'):
                    new_box_no = st.number_input(
                        '새 박스 번호', min_value=1, step=1, value=int(active_box_no),
                        key=f'new_ctn_no_{case_id}_{active_box_no}',
                    )
                    rename_box_clicked = st.form_submit_button('박스 번호 변경', use_container_width=True)
                if rename_box_clicked:
                    try:
                        packing_edit_service.rename_box(case_id, active_box_no, int(new_box_no))
                    except ValueError as exc:
                        st.error(str(exc))
                    else:
                        history_service.add(case_id, '박스 번호 변경', f'CTN {active_box_no} → CTN {int(new_box_no)}')
                        st.session_state[pending_active_key] = f'CTN {int(new_box_no)}'
                        st.session_state.pop(active_label_key, None)
                        st.success(f'CTN {active_box_no}을 CTN {int(new_box_no)}으로 변경했습니다.')
                        st.rerun()

        with box_manage_middle:
            with st.expander('CTN 삭제'):
                delete_label_map = {}
                for delete_box in boxes:
                    delete_box_no = int(delete_box['box_no'])
                    delete_box_items = items_grouped_by_box.get(delete_box_no, [])
                    delete_label = (
                        f"CTN {delete_box_no} · {len(delete_box_items)}행 · "
                        f"{product_summary(delete_box_items)}"
                    )
                    delete_label_map[delete_label] = delete_box_no
                selected_delete_labels = st.multiselect('삭제할 CTN', list(delete_label_map))
                selected_delete_boxes = [delete_label_map[label] for label in selected_delete_labels]
                st.caption('삭제한 CTN의 제품은 다시 미패킹 상태로 돌아갑니다.')
                if st.button(
                    f'선택한 CTN 삭제 ({len(selected_delete_boxes)}개)',
                    disabled=not selected_delete_boxes,
                    use_container_width=True,
                    key=f'delete_ctns_{case_id}',
                ):
                    for delete_box_no in selected_delete_boxes:
                        packing_service.clear_box(case_id, delete_box_no)
                    history_service.add(
                        case_id,
                        'CTN 삭제',
                        ', '.join(f'CTN {number}' for number in selected_delete_boxes),
                    )
                    st.session_state.pop(active_label_key, None)
                    st.success('선택한 CTN을 삭제하고 포함 제품을 미패킹 상태로 돌렸습니다.')
                    st.rerun()

        with box_manage_right:
            if active_box is not None:
                st.markdown('##### CTN 구성 복제')
                clone_count = st.number_input(
                    '복제할 CTN 개수', min_value=1, value=1, step=1,
                    key=f'clone_count_{case_id}_{active_box_no}',
                )
                if st.button(
                    '현재 CTN 복제',
                    use_container_width=True,
                    key=f'clone_ctn_{case_id}_{active_box_no}',
                ):
                    try:
                        created_boxes = packing_service.clone_box(case_id, active_box_no, int(clone_count))
                    except ValueError as exc:
                        st.error(str(exc))
                    else:
                        created_text = ', '.join(f'CTN {number}' for number in created_boxes)
                        history_service.add(case_id, 'CTN 구성 복제', f'CTN {active_box_no} → {created_text}')
                        st.session_state[pending_active_key] = f'CTN {created_boxes[0]}'
                        st.success(f'{created_text}을 생성했습니다.')
                        st.rerun()

    with left_column:
        st.markdown('### 미패킹 제품 선택')
        filter_cols = st.columns([2.3, 1.4, 1.6])
        product_query = filter_cols[0].text_input('제품명 검색', key=f'packing_product_query_{case_id}')
        business_units = sorted({str(item['business_unit'] or '').strip() for item in items if str(item['business_unit'] or '').strip()})
        selected_business = filter_cols[1].selectbox('사업장', ['전체', *business_units], key=f'packing_business_{case_id}')
        lot_query = filter_cols[2].text_input('제조번호 검색', key=f'packing_lot_query_{case_id}')
        unpacked_only = st.toggle('미패킹만 표시', value=True, key=f'packing_unpacked_only_{case_id}')

        visible_items = filter_packing_items(
            items,
            query=product_query,
            business_unit=selected_business,
            lot_query=lot_query,
            unpacked_only=unpacked_only,
        )
        selection_key = f'packing_selected_ids_{case_id}'
        version_key = f'packing_grid_version_{case_id}'
        grid_version = int(st.session_state.get(version_key, 0))
        selected_state = {int(item_id) for item_id in st.session_state.get(selection_key, [])}
        grid_rows = [
            {
                '선택': int(item['id']) in selected_state,
                '_id': int(item['id']),
                '사업장': item['business_unit'] or '-',
                '실제 제품명': item['product_name'] or '-',
                '제조번호': item['lot_no'] or '-',
                '유통기한': item['expiry_date'] or '-',
                '출고수량': float(item['requested_qty'] or 0),
                '현재 CTN': f"CTN {item['box_no']}" if item['box_no'] is not None else '미패킹',
            }
            for item in visible_items
        ]
        grid_columns = [
            '선택', '_id', '사업장', '실제 제품명',
            '제조번호', '유통기한', '출고수량', '현재 CTN',
        ]
        grid_df = pd.DataFrame(grid_rows, columns=grid_columns)
        filter_signature = abs(hash((
            product_query,
            selected_business,
            lot_query,
            bool(unpacked_only),
        )))
        row_ids = [int(item['id']) for item in visible_items]
        grid_widget_key = (
            f"packing_item_grid_{case_id}_{grid_version}_{filter_signature}"
        )
        edited_grid = st.data_editor(
            grid_df,
            hide_index=True,
            use_container_width=True,
            height=min(680, max(250, 70 + len(grid_rows) * 35)),
            disabled=['_id', '사업장', '실제 제품명', '제조번호', '유통기한', '출고수량', '현재 CTN'],
            column_config={
                '선택': st.column_config.CheckboxColumn('선택', width=46),
                '_id': None,
                '사업장': st.column_config.TextColumn('사업장', width=62),
                '실제 제품명': st.column_config.TextColumn('실제 제품명', width=190),
                '제조번호': st.column_config.TextColumn('제조번호', width=88),
                '유통기한': st.column_config.TextColumn('유통기한', width=88),
                '출고수량': st.column_config.NumberColumn('출고수량', format='%.0f', width=72),
                '현재 CTN': st.column_config.TextColumn('현재 CTN', width=68),
            },
            key=grid_widget_key,
            on_change=sync_grid_checkbox_selection,
            args=(grid_widget_key, selection_key, version_key, row_ids),
        )
        selected_ids = sorted({
            int(item_id)
            for item_id in st.session_state.get(selection_key, [])
        })

        quick_cols = st.columns(3)
        same_product = quick_cols[0].button('동일제품 전체선택', use_container_width=True)
        select_visible = quick_cols[1].button('검색 결과 전체선택', use_container_width=True)
        clear_selection = quick_cols[2].button('선택 해제', use_container_width=True)

        if same_product:
            if not selected_ids:
                st.warning('기준이 될 제품을 먼저 한 행 이상 선택하세요.')
            else:
                st.session_state[selection_key] = expand_same_product_selection(visible_items, selected_ids)
                st.session_state[version_key] = int(st.session_state.get(version_key, 0)) + 1
                st.rerun()
        if select_visible:
            st.session_state[selection_key] = [int(item['id']) for item in visible_items]
            st.session_state[version_key] = int(st.session_state.get(version_key, 0)) + 1
            st.rerun()
        if clear_selection:
            st.session_state[selection_key] = []
            st.session_state[version_key] = int(st.session_state.get(version_key, 0)) + 1
            st.rerun()

        st.caption(f'{len(visible_items)}개 행 표시 · {len(selected_ids)}개 선택 · 배정 대상 CTN {active_box_no}')
        action_cols = st.columns([2, 2, 2, 1.5])
        assign_clicked = action_cols[0].button(
            '선택 제품 전량 담기', type='primary', use_container_width=True, disabled=not selected_ids
        )
        partial_clicked = action_cols[1].button(
            '선택 제품 일부 담기', use_container_width=True, disabled=len(selected_ids) != 1
        )
        repeated_clicked = action_cols[2].button(
            '동일 CTN 반복 담기', use_container_width=True, disabled=len(selected_ids) != 1
        )
        unassign_clicked = action_cols[3].button(
            'CTN에서 빼기', use_container_width=True, disabled=not selected_ids
        )

        if assign_clicked:
            packing_service.assign_items(case_id, selected_ids, active_box_no)
            history_service.add(case_id, 'CTN 패킹', f'{len(selected_ids)}개 실제 출고 행 → CTN {active_box_no}')
            st.session_state[selection_key] = []
            st.session_state[version_key] = int(st.session_state.get(version_key, 0)) + 1
            st.session_state[pending_active_key] = f'CTN {active_box_no}'
            st.success(f'{len(selected_ids)}개 행을 CTN {active_box_no}에 담았습니다.')
            st.rerun()

        if partial_clicked:
            selected_item = next(item for item in items if int(item['id']) == selected_ids[0])
            if selected_item['box_no'] is not None:
                st.error('일부 수량 담기는 미패킹 제품만 사용할 수 있습니다.')
            else:
                st.session_state['partial_pack_item_id'] = selected_ids[0]
                st.session_state['partial_pack_box_no'] = active_box_no
                st.rerun()

        if repeated_clicked:
            selected_item = next(item for item in items if int(item['id']) == selected_ids[0])
            if selected_item['box_no'] is not None:
                st.error('동일 CTN 반복 담기는 미패킹 제품만 사용할 수 있습니다.')
            else:
                st.session_state['repeat_pack_item_id'] = selected_ids[0]
                st.session_state.pop(f'repeat_pack_preview_{case_id}', None)
                st.rerun()

        if unassign_clicked:
            packed_selected_ids = [
                int(item['id']) for item in items
                if int(item['id']) in selected_ids and item['box_no'] is not None
            ]
            if not packed_selected_ids:
                st.warning('CTN에서 뺄 패킹 완료 제품을 선택하세요. 미패킹만 표시를 끄면 확인할 수 있습니다.')
            else:
                packing_service.unassign_items(case_id, packed_selected_ids)
                history_service.add(case_id, 'CTN 배정 해제', f'{len(packed_selected_ids)}개 실제 출고 행')
                st.session_state[selection_key] = []
                st.session_state[version_key] = int(st.session_state.get(version_key, 0)) + 1
                st.rerun()

    repeat_item_id = st.session_state.get('repeat_pack_item_id')
    if repeat_item_id:
        repeat_item = next((item for item in items if int(item['id']) == int(repeat_item_id)), None)
        if repeat_item is None or repeat_item['box_no'] is not None:
            st.session_state.pop('repeat_pack_item_id', None)
            st.session_state.pop(f'repeat_pack_preview_{case_id}', None)
        else:
            @dialog('동일 CTN 반복 담기', width='large')
            def repeated_assign_dialog() -> None:
                total_quantity = int(float(repeat_item['requested_qty'] or 0))
                start_box_no = packing_service.next_box_no(case_id)
                st.write(f"**{repeat_item['product_name']}**")
                st.caption(f'남은 수량 {fmt_number(total_quantity)} · 생성 시작 CTN {start_box_no}')

                quantity_per_box = st.number_input(
                    'CTN당 수량', min_value=1, max_value=max(total_quantity, 1),
                    value=min(10, max(total_quantity, 1)), step=1,
                    key=f'repeat_qty_per_box_{case_id}_{repeat_item_id}',
                )
                size_cols = st.columns(4)
                length_cm = size_cols[0].number_input(
                    '가로(cm)', min_value=0.0, step=0.1,
                    key=f'repeat_length_{case_id}_{repeat_item_id}',
                )
                width_cm = size_cols[1].number_input(
                    '세로(cm)', min_value=0.0, step=0.1,
                    key=f'repeat_width_{case_id}_{repeat_item_id}',
                )
                height_cm = size_cols[2].number_input(
                    '높이(cm)', min_value=0.0, step=0.1,
                    key=f'repeat_height_{case_id}_{repeat_item_id}',
                )
                weight_kg = size_cols[3].number_input(
                    'CTN당 GW(kg)', min_value=0.0, step=0.1,
                    key=f'repeat_weight_{case_id}_{repeat_item_id}',
                )

                preview_key = f'repeat_pack_preview_{case_id}'
                if st.button('미리보기 생성', type='primary', use_container_width=True):
                    full_count, remainder = divmod(total_quantity, int(quantity_per_box))
                    quantities = [int(quantity_per_box)] * full_count
                    if remainder:
                        quantities.append(remainder)
                    preview_rows = []
                    for offset, quantity in enumerate(quantities):
                        is_remainder = remainder > 0 and offset == len(quantities) - 1
                        preview_rows.append({
                            'CTN': f'CTN {start_box_no + offset}',
                            '수량': quantity,
                            '박스 사이즈': f'{length_cm:g} × {width_cm:g} × {height_cm:g} cm',
                            'GW': '입력 필요' if is_remainder else f'{weight_kg:g} kg',
                            '구분': '⚠ 잔여 수량 CTN' if is_remainder else '',
                        })
                    st.session_state[preview_key] = {
                        'quantity_per_box': int(quantity_per_box),
                        'length_cm': float(length_cm),
                        'width_cm': float(width_cm),
                        'height_cm': float(height_cm),
                        'weight_kg': float(weight_kg),
                        'rows': preview_rows,
                    }
                    st.rerun()

                preview = st.session_state.get(preview_key)
                if preview:
                    st.markdown(f"#### 생성 예정: 총 {len(preview['rows'])} CTN")
                    preview_df = pd.DataFrame(preview['rows'])
                    styled_preview = preview_df.style.apply(
                        lambda row: ['background-color: #fff1d6'] * len(row)
                        if row['구분'] else [''] * len(row),
                        axis=1,
                    )
                    st.dataframe(styled_preview, hide_index=True, use_container_width=True)
                    if any(row['구분'] for row in preview['rows']):
                        st.warning('마지막 행은 잔여 수량 CTN입니다. GW는 비워 두며 실제 계량 후 입력해야 합니다.')

                    confirm_col, edit_col = st.columns(2)
                    if confirm_col.button('CTN 생성 확정', type='primary', use_container_width=True):
                        try:
                            created = assign_repeated_ctns(
                                case_id,
                                int(repeat_item_id),
                                quantity_per_box=int(preview['quantity_per_box']),
                                length_cm=float(preview['length_cm']),
                                width_cm=float(preview['width_cm']),
                                height_cm=float(preview['height_cm']),
                                weight_kg=float(preview['weight_kg']),
                            )
                        except ValueError as exc:
                            st.error(str(exc))
                        else:
                            created_numbers = ', '.join(f"CTN {row['box_no']}" for row in created)
                            history_service.add(
                                case_id,
                                '동일 CTN 반복 담기',
                                f"{repeat_item['product_name']} {total_quantity}개 → {created_numbers}",
                            )
                            st.session_state.pop('repeat_pack_item_id', None)
                            st.session_state.pop(preview_key, None)
                            st.session_state[selection_key] = []
                            st.session_state[version_key] = int(st.session_state.get(version_key, 0)) + 1
                            st.session_state[pending_active_key] = f"CTN {created[0]['box_no']}"
                            st.success(f'{len(created)}개 CTN을 생성했습니다.')
                            st.rerun()
                    if edit_col.button('입력값 수정', use_container_width=True):
                        st.session_state.pop(preview_key, None)
                        st.rerun()

                if st.button('취소', use_container_width=True):
                    st.session_state.pop('repeat_pack_item_id', None)
                    st.session_state.pop(preview_key, None)
                    st.rerun()

            repeated_assign_dialog()


    partial_item_id = st.session_state.get('partial_pack_item_id')
    if partial_item_id:
        partial_item = next((item for item in items if int(item['id']) == int(partial_item_id)), None)
        if partial_item is None:
            st.session_state.pop('partial_pack_item_id', None)
            st.session_state.pop('partial_pack_box_no', None)
        else:
            @dialog('선택 제품 일부 수량 담기')
            def partial_assign_dialog() -> None:
                total_quantity = int(float(partial_item['requested_qty'] or 0))
                target_box_no = int(st.session_state.get('partial_pack_box_no', next_box_no))
                unit = partial_item['unit'] if 'unit' in partial_item.keys() else ''
                st.write(f"**{partial_item['product_name']}**")
                st.caption(f'남은 수량 {fmt_number(total_quantity)} {unit} · CTN {target_box_no}')
                quantity = st.number_input(
                    '담을 수량', min_value=1, max_value=total_quantity,
                    value=total_quantity, step=1,
                    key=f'partial_pack_qty_{case_id}_{partial_item_id}',
                )
                confirm_col, cancel_col = st.columns(2)
                if confirm_col.button('일부 수량 담기', type='primary', use_container_width=True):
                    try:
                        packing_service.assign_partial_item(
                            case_id, int(partial_item_id), target_box_no, int(quantity)
                        )
                    except ValueError as exc:
                        st.error(str(exc))
                    else:
                        history_service.add(
                            case_id, 'CTN 일부 수량 배정',
                            f"{partial_item['product_name']} {fmt_number(quantity)} → CTN {target_box_no}",
                        )
                        st.session_state.pop('partial_pack_item_id', None)
                        st.session_state.pop('partial_pack_box_no', None)
                        st.session_state[pending_active_key] = f'CTN {target_box_no}'
                        st.session_state[selection_key] = []
                        st.session_state[version_key] = int(st.session_state.get(version_key, 0)) + 1
                        st.rerun()
                if cancel_col.button('취소', use_container_width=True):
                    st.session_state.pop('partial_pack_item_id', None)
                    st.session_state.pop('partial_pack_box_no', None)
                    st.rerun()

            partial_assign_dialog()

