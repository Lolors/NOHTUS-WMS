from __future__ import annotations

import os
from pathlib import Path

import streamlit as st

from nohtus.export_app import db
from nohtus.export_app.services import export_service, folder_service, history_service, folder_sync_service


RECENT_FOLDER_DAYS = 14
QUARTER_FOLDER_DAYS = 90


def browse_folder() -> str:
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        selected = filedialog.askdirectory(title='내 폴더 선택')
        root.destroy()
        return selected or ''
    except Exception as exc:
        st.warning(f'폴더 선택 창을 열 수 없습니다. 경로를 직접 입력하세요. ({exc})')
        return ''


def check_folder_path(path_text: str) -> tuple[bool, str]:
    path_text = path_text.strip()
    if not path_text:
        return False, '내 폴더 위치를 입력하거나 선택하세요.'
    path = Path(path_text).expanduser()
    if os.name == 'nt' and path.drive:
        drive_root = Path(f'{path.drive}\\')
        if not drive_root.exists():
            return False, f'{path.drive} 드라이브를 찾을 수 없습니다. USB가 연결되어 있는지 확인하세요.'
    ok, message = folder_service.test_storage_root(path_text)
    if not ok:
        return False, f'선택한 폴더에 저장할 수 없습니다.\n\n원인: {message}'
    return True, message


def _case_reference_date(case):
    return folder_sync_service.reference_date(case)


def render() -> None:
    st.title('내 폴더')
    st.caption('수출 문서 폴더와 자동 백업용 USB를 설정하고 수출 폴더를 동기화합니다.')

    current_root = db.get_setting('shared_root').strip()
    if 'folder_path_input' not in st.session_state:
        st.session_state['folder_path_input'] = current_root
    if 'pending_folder_path' in st.session_state:
        st.session_state['folder_path_input'] = st.session_state.pop('pending_folder_path')

    st.info(
        '폴더 구조는 국가 / 연도 / 월 / 수출건 폴더로 생성됩니다. '
        '실제 출고일이 입력된 건만 폴더명 앞에 MMDD 날짜가 붙습니다. '
        '수출진행내역.xlsx는 수출건 본폴더에 저장되고, 사용자 파일은 동기화해도 삭제하지 않습니다.'
    )

    management_col, example_col = st.columns(2, gap='large')

    with management_col:
        st.markdown('#### 수출 폴더 관리')
        st.caption(
            f'기본 갱신은 최근 {RECENT_FOLDER_DAYS}일 내 등록·수정·출고된 건을 처리합니다. '
            '선택 범위에서 새로 생성되거나 변경된 수출 건만 모으며, 변경 없는 건은 건너뜁니다. 해당 폴더를 '
            '현재 구조로 맞추고, 수출진행내역.xlsx를 현재 DB의 주문·출고·CTN 정보로 완전히 새로 생성합니다. '
            '사진·CI·Shipping Mark·기타 파일은 유지하며, 국가/연도/월 구조 그대로 하나의 갱신폴더에 복사합니다.'
        )
        scope_recent, scope_quarter, scope_all = (
            f'최근 {RECENT_FOLDER_DAYS}일',
            '최근 3개월',
            '전체 (취소 제외 모든 수출 건)',
        )
        sync_scope = st.radio(
            '갱신 범위',
            [scope_recent, scope_quarter, scope_all],
            horizontal=True,
            key='folder_sync_scope',
        )
        needs_confirm = sync_scope != scope_recent
        folder_confirm = True
        if needs_confirm:
            folder_confirm = st.checkbox(
                f'{sync_scope} 범위의 신규·변경된 수출 폴더와 엑셀을 갱신하는 것에 동의합니다.',
                key='folder_sync_confirm',
            )
        sync_button_label = {
            scope_recent: f'최근 {RECENT_FOLDER_DAYS}일 폴더 및 엑셀 갱신',
            scope_quarter: '최근 3개월 신규·변경 폴더 및 엑셀 갱신',
            scope_all: '전체 범위 신규·변경 폴더 및 엑셀 갱신',
        }[sync_scope]

        if st.button(
            sync_button_label,
            type='primary',
            use_container_width=True,
            disabled=needs_confirm and not folder_confirm,
        ):
            folder_service.hide_existing_internal_items()
            all_cases = export_service.list_cases(include_cancelled=False)
            days = None if sync_scope == scope_all else (RECENT_FOLDER_DAYS if sync_scope == scope_recent else QUARTER_FOLDER_DAYS)
            target_cases = folder_sync_service.select_cases(all_cases, days)
            progress = st.progress(0, text='폴더와 엑셀을 재생성하고 하나의 갱신폴더에 모으고 있습니다.')
            result = folder_sync_service.rebuild_batch(
                target_cases,
                progress=lambda index, total: progress.progress(index / total, text=f'{index}/{total} 처리 중'),
            )
            progress.empty()
            rebuilt, gathered = len(result['rebuilt']), len(result['gathered'])
            if rebuilt:
                history_service.add_history(None, sync_button_label,
                    f"{rebuilt}건 재생성 / {gathered}건 모음 완료 / {len(result['failures'])}건 재생성 실패 / {len(result['copy_failures'])}건 복사 실패")
                st.success(f"엑셀 {rebuilt}건 재생성 · 갱신폴더에 {gathered}건 모음 완료 · 변경 없음 {len(result['skipped'])}건 제외")
            elif result['skipped'] and not result['failures']:
                st.info(f"{len(result['skipped'])}건 모두 변경이 없어 갱신폴더를 만들지 않았습니다.")
            elif not result['failures']:
                st.info('선택한 범위에서 갱신할 수출 건이 없습니다.')
            if result['root'] is not None:
                st.info('이번 갱신폴더 위치입니다. 복사 완료된 건을 국가 / 연도 / 월별로 확인하세요.')
                st.code(str(result['root']))
                if result['gathered']:
                    with st.expander('갱신폴더에 포함된 수출 건', expanded=True):
                        for export_no, relative in result['gathered']:
                            st.text(f'{export_no} · {relative}')
            if result['copy_failures']:
                st.warning('원래 위치는 갱신했지만 갱신폴더로 복사하지 못한 건이 있습니다.\n\n' + '\n'.join(result['copy_failures']))
            if result['failures']:
                st.error('일부 폴더 또는 엑셀을 처리하지 못했습니다.\n\n' + '\n'.join(result['failures']))
            if result['drive_corruption']:
                st.error('저장장치 파일시스템 손상(WinError 1392)을 감지해 중단했습니다. 정상 저장 위치를 선택한 뒤 다시 실행하세요.')

    with example_col:
        st.markdown('#### 자동 생성 예시')
        st.code(
            '''필리핀
       └─ 2026
          └─ 07월
             ├─ [AIR] 리쥬네르 인젝터, 모니터 전원 케이블
             └─ 0730_[노투스필리핀 SEA] 벨룩시 듀이스킨, 벨룩시 리턴20 외 30품목
                ├─ 수출진행내역.xlsx
                ├─ .export_case.json
                ├─ 01_출고제품사진
                ├─ 02_CI
                ├─ 03_Shipping Mark
                └─ 04_기타'''
        )

    st.divider()

    folder_col, current_col = st.columns(2, gap='large')

    with folder_col:
        st.markdown('#### 내 폴더 위치')
        folder_text = st.text_input(
            '내 폴더 위치',
            key='folder_path_input',
            placeholder=r'예: E:\ 또는 \\NAS\공유경로',
            label_visibility='collapsed',
        )

        if st.button('폴더 찾아보기', use_container_width=True):
            selected = browse_folder()
            if selected:
                st.session_state['pending_folder_path'] = selected
                st.rerun()

        path_button_1, path_button_2 = st.columns(2)
        if path_button_1.button('경로 검사', use_container_width=True):
            ok, message = check_folder_path(folder_text)
            if ok:
                st.success(f'읽기·쓰기 확인 완료\n\n{message}')
            else:
                st.error(message)

        if path_button_2.button('설정 저장', type='primary', use_container_width=True):
            ok, message = check_folder_path(folder_text)
            if ok:
                saved_path = str(Path(folder_text).expanduser())
                db.set_setting('shared_root', saved_path)
                st.success(f'내 폴더 위치를 저장했습니다.\n\n{message}')
            else:
                st.error(message)

        if st.button('기본 uploads 사용', use_container_width=True):
            db.set_setting('shared_root', '')
            st.session_state['pending_folder_path'] = ''
            st.rerun()

    with current_col:
        st.markdown('#### 현재 저장 위치')
        saved_root = db.get_setting('shared_root').strip()
        st.code(saved_root or str(folder_service.storage_root().resolve()))
        if saved_root:
            # Rendering this page must not create/delete a probe file on a slow
            # network/USB folder.  The explicit "경로 검사" button performs the
            # full write test when the user asks for it.
            current_path = folder_service.storage_root()
            try:
                saved_exists = current_path.exists()
            except OSError:
                saved_exists = False
            if saved_exists:
                st.success('현재 내 폴더에 정상적으로 연결되어 있습니다.')
            else:
                st.warning(f'현재 내 폴더 경로를 찾을 수 없습니다: {current_path}')
        else:
            st.info('별도 경로가 없어 기본 uploads 폴더를 사용합니다.')
