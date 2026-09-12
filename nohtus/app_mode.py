"""WMS ↔ 발주관리 상단 모드 전환.

노투스 WMS와 발주관리는 같은 Streamlit 앱 안에서 사이드바 맨 위의 슬라이드
스위치로 전환한다(로그인 세션은 공유). 이 모듈은 그 스위치 UI와 현재
모드 상태만 책임진다 — 실제 발주관리 화면 렌더링은
nohtus.order_management_bridge.render_order_management()가 한다.
"""

from __future__ import annotations

import streamlit as st

from nohtus.config import APP_TITLE

_APP_MODE_KEY = "_top_app_mode"


def _render_app_mode_toggle() -> str:
    """WMS ↔ 발주관리 전환용 상단 슬라이드 스위치. 항상 사이드바 맨 위에 고정으로 그린다."""
    mode = st.session_state.get(_APP_MODE_KEY, "wms")
    is_order_management = mode == "order_management"

    st.sidebar.markdown(
        """
        <style>
        div[class*="st-key-app_mode_toggle_row"] {
            background: rgba(148, 163, 184, 0.16);
            border: 1px solid rgba(148, 163, 184, 0.4);
            border-radius: 999px;
            padding: 8px 14px;
            margin: 4px 0 0;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            width: fit-content;
        }
        div[class*="st-key-app_mode_toggle_row"] [data-testid="stLayoutWrapper"] {
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            width: fit-content;
            height: auto !important;
        }
        div[class*="st-key-app_mode_toggle_row"] [data-testid="stHorizontalBlock"] {
            width: fit-content;
            display: flex !important;
            flex-direction: row !important;
            flex-wrap: nowrap !important;
            align-items: center !important;
        }
        div[class*="st-key-app_mode_toggle_row"] [data-testid="stVerticalBlock"] {
            gap: 0;
        }
        div[class*="st-key-app_mode_toggle_row"] [data-testid="stElementContainer"],
        div[class*="st-key-app_mode_toggle_row"] .element-container {
            margin: 0 !important;
            display: flex !important;
            align-items: center !important;
            align-self: center !important;
            height: auto !important;
        }
        div[class*="st-key-app_mode_toggle_row"] [data-testid="stColumn"] {
            display: flex !important;
            align-items: center !important;
            align-self: center !important;
            width: auto !important;
            flex: 0 0 auto !important;
            height: auto !important;
        }
        div[class*="st-key-app_mode_toggle_row"] [data-testid="stVerticalBlock"] {
            align-self: center !important;
        }
        div[class*="st-key-app_mode_toggle_row"] [data-testid="stMarkdown"],
        div[class*="st-key-app_mode_toggle_row"] [data-testid="stMarkdown"] > div {
            display: flex !important;
            align-items: center !important;
            align-self: center !important;
            height: auto !important;
        }
        div[class*="st-key-app_mode_toggle_row"] [data-testid="stMarkdownContainer"] {
            width: 100%;
            display: flex !important;
            align-items: center !important;
            align-self: center !important;
        }
        div[class*="st-key-app_mode_toggle_row"] [data-testid="stMarkdownContainer"] p {
            align-self: center !important;
            transform: translateY(-7px);
        }
        div[class*="st-key-app_mode_toggle_row"] [data-testid="stMarkdownContainer"] p {
            margin: 0;
            line-height: 1.1;
            font-size: 0.92rem;
            font-weight: 800;
            white-space: nowrap;
        }
        div[class*="st-key-app_mode_toggle_row"] [data-testid="stWidgetLabel"] {
            display: none !important;
            height: 0 !important;
            min-height: 0 !important;
            margin: 0 !important;
            padding: 0 !important;
        }
        div[class*="st-key-app_mode_toggle_row"] [data-testid="stCheckbox"] {
            display: flex !important;
            align-items: center !important;
            height: auto !important;
        }
        div[class*="st-key-app_mode_toggle_row"] label[data-baseweb="checkbox"] {
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            transform: translateX(7px) scale(1.6);
            transform-origin: center;
            margin: 0 !important;
        }
        div[class*="st-key-app_mode_toggle_row"] label[data-baseweb="checkbox"] > div:first-child {
            margin: 0 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    with st.sidebar.container(key="app_mode_toggle_row"):
        wms_col, switch_col, om_col = st.columns([1.1, 0.9, 1.3], vertical_alignment="center")
        wms_col.markdown(
            f"<p style='text-align:right;color:{'#0f172a' if not is_order_management else '#94a3b8'}'>WMS</p>",
            unsafe_allow_html=True,
        )
        with switch_col:
            new_value = st.toggle(
                "app_mode_switch",
                value=is_order_management,
                key="app_mode_switch",
                label_visibility="collapsed",
            )
        om_col.markdown(
            f"<p style='text-align:left;color:{'#0f172a' if is_order_management else '#94a3b8'}'>발주관리</p>",
            unsafe_allow_html=True,
        )

    new_mode = "order_management" if new_value else "wms"
    if new_mode != mode:
        st.session_state[_APP_MODE_KEY] = new_mode
        st.rerun()
    return new_mode


def render_mode_section(role: str) -> str:
    """사이드바 맨 위에 모드 전환 스위치(또는 고정 WMS 타이틀)를 그리고 현재 모드를 반환한다."""
    if role.strip().lower() in {"user", "admin"}:
        st.sidebar.markdown(
            """
            <style>
            div[class*="st-key-app_mode_wrap"] [data-testid="stVerticalBlockBorderWrapper"],
            div[class*="st-key-app_mode_wrap"] [data-testid="stVerticalBlock"] {
                gap: 0.25rem !important;
            }
            div[class*="st-key-app_mode_wrap"] [data-testid="stMarkdownContainer"] h1 {
                margin: 0 !important;
                padding: 0 !important;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )
        with st.sidebar.container(key="app_mode_wrap"):
            app_mode = _render_app_mode_toggle()
            st.markdown(f"# {'발주관리' if app_mode == 'order_management' else APP_TITLE}")
        return app_mode

    st.session_state[_APP_MODE_KEY] = "wms"
    st.sidebar.markdown(f"# {APP_TITLE}")
    return "wms"
