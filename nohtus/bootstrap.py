"""앱 시작 시 한 번 해야 하는 초기화 + 모바일 접속 감지/리다이렉트.

main()이 페이지를 그리기 전에 순서대로:
1. configure_page() — 탭 제목/아이콘/레이아웃
2. init_services() — DB 초기화, 백업 워커, 스타일, 모바일 플래그 동기화
3. resolve_mobile_view() — 모바일이면 새 모바일 앱으로 리다이렉트(가능한 경우)
   하고, 안 되면 최소한 모바일용 로그인 화면 CSS라도 적용한다.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from styles import apply_style
from nohtus.config import APP_TITLE
from nohtus.db_init import init_db
from nohtus.device import is_mobile, mobile_app_url, redirect_to_mobile_app, sync_mobile_flag
from nohtus.export_app_bridge import init_export_app
from nohtus.services import database_backup

_FAVICON_PATH = Path(__file__).resolve().parent.parent / "mobile_app" / "icons" / "icon-512.png"


def configure_page():
    st.set_page_config(
        page_title=APP_TITLE,
        layout="wide",
        page_icon=str(_FAVICON_PATH) if _FAVICON_PATH.is_file() else None,
    )


def init_services():
    init_db()
    init_export_app()
    # 실제 백업 파일 복사(및 Google Drive 폴더 I/O)는 별도 스레드에서만 한다.
    # 예전에는 여기서 매 rerun마다 동기적으로 run_due_backups()를 불렀는데,
    # Dropbox로 동기화되는 폴더에서 이 파일 존재 확인/복사 자체가 느려서
    # 클릭할 때마다 화면이 그만큼 느려지는 원인이었다.
    database_backup.start_backup_worker()
    apply_style()
    sync_mobile_flag()


def _inject_mobile_login_css():
    st.markdown(
        """
        <style>
        @media (max-width: 768px) {
            div[data-testid="stForm"],
            div[data-testid="stForm"] > div,
            div[data-testid="stForm"] form {
                border: 0 !important;
                border-radius: 0 !important;
                background: transparent !important;
                box-shadow: none !important;
                padding: 0 !important;
                margin: 0 !important;
            }
            .login-account { display: none !important; }
            .login-title {
                margin-top: .35rem !important;
                margin-bottom: 1rem !important;
                font-size: 1.65rem !important;
            }
            div[data-testid="stTextInput"] { margin-bottom: .15rem !important; }
            div[data-testid="stFormSubmitButton"] { margin-top: .2rem !important; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def resolve_mobile_view() -> bool:
    """모바일 접속이면 True. 새 모바일 앱 주소가 설정돼 있으면 그리로
    리다이렉트하고 돌아오지 않는다(redirect_to_mobile_app이 st.stop()을 부른다)."""
    force_mobile = str(st.query_params.get("mobile", "")).strip().lower() in {"1", "true", "yes", "on"}
    skip_mobile_redirect = str(st.query_params.get("skip_mobile_redirect", "")).strip() == "1"
    mobile_view = is_mobile() or force_mobile

    if mobile_view and not skip_mobile_redirect:
        new_mobile_app_url = mobile_app_url()
        if new_mobile_app_url:
            redirect_to_mobile_app(new_mobile_app_url)

    if mobile_view:
        _inject_mobile_login_css()

    return mobile_view
