from __future__ import annotations

from html import escape

import pandas as pd
import streamlit as st

from nohtus.export_app.components.dashboard_timeline import render_order_timeline
from nohtus.export_app.services import export_service, overview_service
from nohtus.export_app.services.dashboard_view_service import (
    recent_order_cases,
    recent_order_period_label,
    stage_bar_colors,
    stage_label,
    stage_style as _stage_style,
    timeline_date,
    timeline_period,
)


def render() -> None:
    st.title('대시보드')
    st.caption('최근 1개월 주문의 등록일부터 출고일까지 걸린 기간과 확인사항을 한 화면에서 관리합니다.')

    st.markdown(
        '''
        <style>
        div[data-testid="stVerticalBlock"] div[data-testid="stVerticalBlock"]:has(.export-table-anchor) {
            width: 60vw;
            max-width: 60vw;
        }
        div[data-testid="stVerticalBlock"] div[data-testid="stVerticalBlock"]:has(.todo-section-anchor) {
            width: 40vw;
            max-width: 40vw;
        }
        .export-table-anchor,
        .todo-section-anchor,
        .sticky-note-anchor {
            height: 0;
            margin: 0;
            padding: 0;
            overflow: hidden;
        }
        div[data-testid="stVerticalBlock"] div[data-testid="stVerticalBlock"]:has(.sticky-note-anchor) {
            min-height: 160px;
            padding: 1rem 1rem 0.7rem;
            border: 1px solid rgba(133, 105, 20, 0.24);
            border-radius: 4px 15px 5px 13px;
            background: linear-gradient(145deg, #fff7ad 0%, #ffef82 100%);
            box-shadow: 0 6px 16px rgba(81, 63, 7, 0.10);
            transform: rotate(-0.25deg);
        }
        div[data-testid="stVerticalBlock"] div[data-testid="stVerticalBlock"]:has(.sticky-note-anchor) p,
        div[data-testid="stVerticalBlock"] div[data-testid="stVerticalBlock"]:has(.sticky-note-anchor) label {
            color: #4d410c;
        }
        @media (max-width: 900px) {
            div[data-testid="stVerticalBlock"] div[data-testid="stVerticalBlock"]:has(.export-table-anchor),
            div[data-testid="stVerticalBlock"] div[data-testid="stVerticalBlock"]:has(.todo-section-anchor) {
                width: 100%;
                max-width: 100%;
            }
        }
        </style>
        ''',
        unsafe_allow_html=True,
    )

    cases = recent_order_cases(
        export_service.list_cases(),
        month_count=1,
    )
    cases = sorted(
        cases,
        key=lambda case: (
            timeline_date(case),
            str(case['country'] or '').casefold(),
            str(case['buyer'] or '').casefold(),
            str(case['export_no'] or '').casefold(),
        ),
        reverse=True,
    )

    order_items_by_case: dict[int, list[dict]] = {}
    for item in export_service.get_order_items_for_cases(case['id'] for case in cases):
        order_items_by_case.setdefault(int(item['case_id']), []).append(item)

    product_summary_by_case: dict[int, str] = {}
    product_detail_by_case: dict[int, str] = {}
    for case in cases:
        case_id = int(case['id'])
        items = order_items_by_case.get(case_id, [])
        names = [
            str(item['product_name'] or '').strip()
            for item in items
            if str(item['product_name'] or '').strip()
        ]
        visible_names = names[:2]
        summary = ', '.join(visible_names) or '-'
        if len(names) > 2:
            summary += f' + 그 외 {len(names) - 2}품목'
        product_summary_by_case[case_id] = summary
        product_detail_by_case[case_id] = '\n'.join(
            (
                f"{str(item['product_name'] or '').strip()} · "
                f"{float(item['quantity'] or 0):g}{str(item['unit'] or '').strip()}"
            )
            for item in items
            if str(item['product_name'] or '').strip()
        ) or '주문목록 없음'

    st.markdown(f'### 최근 1개월 주문 건 ({recent_order_period_label(month_count=1)})')
    if not cases:
        st.info('최근 1개월 동안 등록된 주문 건이 없습니다.')
    else:
        timeline_rows = []
        for case in cases:
            raw_stage = str(case['stage'] or '').strip() or '단계 미입력'
            country = str(case['country'] or '').strip() or '국가 미입력'
            buyer = str(case['buyer'] or '').strip() or '바이어 미입력'
            transport = str(case['transport_mode'] or '').strip() or '운송방식 미입력'
            product_summary = product_summary_by_case.get(int(case['id']), '-')
            bar_background, bar_text, bar_accent = stage_bar_colors(raw_stage)
            start_date, end_date = timeline_period(case)
            timeline_rows.append({
                'case_id': int(case['id']),
                'start_date': start_date,
                'end_date': end_date,
                'export_no': str(case['export_no'] or '').strip() or '수출번호 미입력',
                'party': f'{country} · {buyer}',
                'bar_label': f'{country} - {buyer} - {transport}',
                'stage': stage_label(raw_stage),
                'product_summary': product_summary,
                'products': product_detail_by_case.get(int(case['id']), '주문목록 없음'),
                'bar_background': bar_background,
                'bar_text': bar_text,
                'bar_accent': bar_accent,
            })
        selected_timeline_case_id = render_order_timeline(timeline_rows)
        if selected_timeline_case_id is not None:
            st.session_state['actual_packing_case_id'] = selected_timeline_case_id
            st.session_state['page'] = '수출대기 입고'
            st.rerun()

        with st.expander('주문 표로 보기', expanded=True):
            st.caption('아래 표에서 주문을 클릭하면 해당 수출 건의 수출대기 입고 화면으로 이동합니다.')
            table_rows = []
            for index, case in enumerate(cases, start=1):
                raw_stage = str(case['stage'] or '').strip() or '단계 미입력'
                table_rows.append(
                    {
                        '_case_id': int(case['id']),
                        '구분': index,
                        '국가': str(case['country'] or '').strip() or '국가 미입력',
                        '바이어': str(case['buyer'] or '').strip() or '바이어 미입력',
                        '운송방식': str(case['transport_mode'] or '').strip() or '운송방식 미입력',
                        '수출번호': str(case['export_no'] or '').strip() or '수출번호 미입력',
                        '현재 단계': stage_label(raw_stage),
                        '주문제품': product_summary_by_case.get(int(case['id']), '-'),
                    }
                )

            table_df = pd.DataFrame(table_rows)
            styled_table = table_df.style.map(_stage_style, subset=['현재 단계'])
            with st.container():
                st.markdown('<div class="export-table-anchor"></div>', unsafe_allow_html=True)
                table_event = st.dataframe(
                    styled_table,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        '_case_id': None,
                        '구분': st.column_config.NumberColumn(width='small'),
                        '국가': st.column_config.TextColumn(width='small'),
                        '바이어': st.column_config.TextColumn(width='medium'),
                        '운송방식': st.column_config.TextColumn(width='small'),
                        '수출번호': st.column_config.TextColumn(width='medium'),
                        '현재 단계': st.column_config.TextColumn(width='small'),
                        '주문제품': st.column_config.TextColumn(width='large'),
                    },
                    on_select='rerun',
                    selection_mode='single-row',
                    key='dashboard_order_table',
                )
            selected_rows = table_event.selection.rows
            if selected_rows:
                selected_case_id = int(table_df.iloc[selected_rows[0]]['_case_id'])
                st.session_state['actual_packing_case_id'] = selected_case_id
                st.session_state['page'] = '수출대기 입고'
                st.rerun()

    st.divider()
    with st.container():
        st.markdown('<div class="todo-section-anchor"></div>', unsafe_allow_html=True)
        st.markdown('### 내가 체크할 일')
        st.caption('확인할 내용을 포스트잇처럼 추가하고, 끝난 일은 체크하거나 삭제할 수 있습니다.')

        with st.form('overview_add_task_form', clear_on_submit=True):
            add_cols = st.columns([5, 1])
            task_text = add_cols[0].text_input(
                '새 메모',
                placeholder='예: 일본 바이어 패킹리스트 최종 확인',
                label_visibility='collapsed',
            )
            add_task = add_cols[1].form_submit_button('메모 추가', type='primary', use_container_width=True)

        if add_task:
            try:
                overview_service.add_task(task_text)
            except ValueError as exc:
                st.warning(str(exc))
            else:
                st.rerun()

        tasks = overview_service.list_tasks()
        if not tasks:
            st.info('아직 등록한 메모가 없습니다.')
        else:
            note_columns = st.columns(2)
            for index, task in enumerate(tasks):
                column = note_columns[index % 2]
                with column:
                    with st.container():
                        st.markdown('<div class="sticky-note-anchor"></div>', unsafe_allow_html=True)
                        done = st.checkbox(
                            '확인 완료',
                            value=bool(task['done']),
                            key=f"overview_task_done_{task['id']}",
                        )
                        text_style = 'text-decoration: line-through; opacity: 0.58;' if done else ''
                        st.markdown(
                            f'<div style="font-size:1.02rem;font-weight:700;line-height:1.55;{text_style}">'
                            f'{escape(task["text"])}</div>',
                            unsafe_allow_html=True,
                        )
                        if done != bool(task['done']):
                            overview_service.set_done(task['id'], done)
                            st.rerun()
                        if st.button(
                            '삭제',
                            key=f"overview_task_delete_{task['id']}",
                            use_container_width=True,
                        ):
                            overview_service.delete_task(task['id'])
                            st.rerun()
