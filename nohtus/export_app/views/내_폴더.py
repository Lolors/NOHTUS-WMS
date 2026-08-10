from __future__ import annotations

import os
from pathlib import Path

import streamlit as st

from nohtus.export_app import db
from nohtus.export_app.services import export_service, folder_service, history_service


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
            '취소되지 않은 모든 수출 건의 폴더를 현재 구조로 맞추고, '
            '수출진행내역.xlsx를 현재 DB의 주문·출고·CTN 정보로 완전히 새로 생성합니다. '
            '사진·CI·Shipping Mark·기타 파일은 유지합니다.'
        )
        folder_confirm = st.checkbox(
            '기존 수출 폴더를 현재 구조로 이동·이름 변경하고 엑셀을 재생성하는 것에 동의합니다.',
            key='folder_sync_confirm',
        )

        if st.button(
            '수출 폴더 및 엑셀 전체 재생성',
            type='primary',
            disabled=not folder_confirm,
            use_container_width=True,
        ):
            folder_service.hide_existing_internal_items()
            all_cases = export_service.list_cases(include_cancelled=False)
            successes: list[str] = []
            failures: list[str] = []
            drive_corruption_detected = False
            progress = st.progress(0, text='수출 폴더와 엑셀을 새로 생성하고 있습니다.')
            total = max(len(all_cases), 1)
            for index, case in enumerate(all_cases, start=1):
                try:
                    folder = folder_service.sync_case_folder(
                        int(case['id']),
                        force_workbook=True,
                    )
                    successes.append(f"{case['export_no']} → {folder}")
                except Exception as exc:
                    failures.append(f"{case['export_no']}: {exc}")
                    if getattr(exc, 'winerror', None) == 1392:
                        drive_corruption_detected = True
                        break
                progress.progress(index / total, text=f'{index}/{len(all_cases)} 처리 중')
            progress.empty()
            if successes:
                history_service.add_history(
                    None,
                    '수출 폴더 및 엑셀 전체 재생성',
                    f'유효 수출 {len(successes)}건 완료 / {len(failures)}건 실패 / 취소 건 제외',
                )
                st.success(
                    f'취소 건을 제외한 {len(successes)}건의 폴더를 동기화하고 '
                    '수출진행내역.xlsx를 새로 생성했습니다.'
                )
            elif not failures:
                st.info('재생성할 유효한 수출 건이 없습니다.')
            if drive_corruption_detected:
                st.error(
                    '저장장치 파일시스템 손상(WinError 1392)을 감지해 추가 쓰기 작업을 중단했습니다. '
                    '정상 드라이브로 저장 위치를 변경한 뒤 다시 실행하세요.'
                )
            if failures:
                st.error('일부 폴더 또는 엑셀을 처리하지 못했습니다.\n\n' + '\n'.join(f'- {item}' for item in failures))

    with example_col:
        st.markdown('#### 자동 생성 예시')
        st.code(
            '''수출관리
    └─ 필리핀
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
            placeholder=r'예: E:\수출관리 또는 \\NAS\수출관리',
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
            saved_ok, saved_message = check_folder_path(str(folder_service.storage_root()))
            if saved_ok:
                st.success('현재 내 폴더에 정상적으로 연결되어 있습니다.')
            else:
                st.warning(saved_message)
        else:
            st.info('별도 경로가 없어 기본 uploads 폴더를 사용합니다.')