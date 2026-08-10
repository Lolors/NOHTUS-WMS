from __future__ import annotations

from html import escape

import streamlit as st

from nohtus.export_app.services import overview_service


def render() -> None:
    st.title('대시보드')
    st.caption('확인이 필요한 내용을 메모로 관리합니다.')

    st.markdown(
        '''
        <style>
        div[data-testid="stVerticalBlock"] div[data-testid="stVerticalBlock"]:has(.todo-section-anchor) {
            width: 40vw;
            max-width: 40vw;
        }
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
            div[data-testid="stVerticalBlock"] div[data-testid="stVerticalBlock"]:has(.todo-section-anchor) {
                width: 100%;
                max-width: 100%;
            }
        }
        </style>
        ''',
        unsafe_allow_html=True,
    )

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
