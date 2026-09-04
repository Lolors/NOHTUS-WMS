"""Streamlit UI entrypoint."""
from pathlib import Path

import streamlit as st

from config import APP_TITLE
from services.bootstrap import run


APP_ICON = "📦"


def main() -> None:
    """기존 핵심 앱의 페이지 설정을 유지하면서 탭 제목과 아이콘을 통일합니다."""
    original_set_page_config = st.set_page_config

    def set_versioned_page_config(*args, **kwargs):
        kwargs["page_title"] = APP_TITLE
        kwargs["page_icon"] = APP_ICON
        return original_set_page_config(*args, **kwargs)

    st.set_page_config = set_versioned_page_config
    try:
        run(Path(__file__).resolve().parents[1])
    finally:
        st.set_page_config = original_set_page_config
