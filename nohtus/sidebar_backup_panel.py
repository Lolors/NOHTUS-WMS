"""admin 전용 사이드바 "데이터 백업" 패널."""

from __future__ import annotations

from datetime import datetime

import streamlit as st

from nohtus.services import database_backup


def render():
    st.markdown("""<style>
    section[data-testid="stSidebar"] [data-testid="stExpander"]:has(.st-key-google_drive_backup_root) summary {
        background:#174b70!important;color:#fff!important;border-radius:8px;
    }
    section[data-testid="stSidebar"] [data-testid="stExpander"]:has(.st-key-google_drive_backup_root) summary:hover,
    section[data-testid="stSidebar"] [data-testid="stExpander"]:has(.st-key-google_drive_backup_root) summary:focus {
        background:#205d85!important;
    }
    section[data-testid="stSidebar"] .st-key-google_drive_backup_root input {
        background:#fff!important;color:#183153!important;-webkit-text-fill-color:#183153!important;caret-color:#183153;
    }
    section[data-testid="stSidebar"] .st-key-google_drive_backup_root input::placeholder {
        color:#64748b!important;-webkit-text-fill-color:#64748b!important;
    }
    section[data-testid="stSidebar"] .st-key-download_current_wms_db button {
        background:#174b70!important;border:1px solid #648ba6!important;color:#fff!important;
    }
    section[data-testid="stSidebar"] .st-key-download_current_wms_db button:hover {
        background:#205d85!important;
    }
    </style>""", unsafe_allow_html=True)
    with st.sidebar.expander("데이터 백업"):
        st.caption("DB 3개는 로컬에 최신 20개를 보관합니다. Google Drive에는 DB·첨부파일·맵 설정은 매시간, 제품사진은 별도 파일로 24시간마다 백업하고, 최근 24시간의 시간별 백업과 최근 30일의 일별 백업을 보관합니다. PC와 Drive가 실행 중이어야 동기화됩니다.")
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
                st.success("Google Drive 폴더에 백업 생성 완료(업로드는 Drive에서 확인):  \n" + paths.replace("\n", "  \n"))
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
