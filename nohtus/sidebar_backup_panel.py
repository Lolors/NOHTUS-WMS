"""admin 전용 사이드바 "데이터 백업" 패널."""

from __future__ import annotations

from datetime import datetime

import streamlit as st

from nohtus.services import database_backup


def render():
    with st.sidebar.expander("데이터 백업"):
        st.caption("WMS DB, 수출관리 DB, 발주관리 DB는 매시간 로컬과 Google Drive에 자동 백업되며 각각 최신 20개를 보관합니다.")
        drive_path = st.text_input(
            "Google Drive 동기화 폴더",
            value=database_backup.google_drive_root(),
            placeholder=r"G:\\내 드라이브 또는 C:\\Users\\사용자\\My Drive",
            key="google_drive_backup_root",
        )
        if st.button("Google Drive 경로 저장", use_container_width=True, key="save_google_drive_backup_root"):
            try:
                backup_dir = database_backup.set_google_drive_root(drive_path)
                st.success(f"백업 폴더 설정 완료: {backup_dir}")
            except Exception as exc:
                st.error(str(exc))
        if st.button(
            "지금 Google Drive에 백업",
            use_container_width=True,
            key="backup_wms_to_google_drive_now",
        ):
            try:
                paths = database_backup.backup_to_google_drive_now()
                st.success("Google Drive 백업 완료:  \n" + paths.replace("\n", "  \n"))
            except Exception as exc:
                st.error(str(exc))
        for error in database_backup.last_backup_result().get("errors", []):
            st.warning(error)

        st.markdown("<hr>", unsafe_allow_html=True)
        try:
            db_bytes = database_backup.current_wms_db_bytes()
            st.download_button(
                "현재 WMS의 DB파일 받기",
                data=db_bytes,
                file_name=f"nohtus_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db",
                mime="application/octet-stream",
                use_container_width=True,
                key="download_current_wms_db",
            )
        except Exception as exc:
            st.error(str(exc))
