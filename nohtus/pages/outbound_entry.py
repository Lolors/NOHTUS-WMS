"""일반 출고지시 메뉴 진입점.

수출대기 화면(nohtus/pages/export_waiting_compat.py)은 출고지시 렌더러를
재사용하면서 일부 Streamlit 위젯을 임시로 바꿔치기한다. 그 패치가 일반
출고지시 화면으로 새지 않도록, 앱 시작 시점의 원본 위젯을 여기 보관해뒀다가
매번 강제로 복구한 뒤 렌더링한다.
"""

from __future__ import annotations

import streamlit as st

# 다른 페이지 모듈이 import되면서 st.* 위젯을 건드리기 전에(모듈 레벨
# monkey-patch가 실제로 있다 — 예: outbound_lot_warning.py의 st.button)
# 반드시 이 캡처가 먼저 실행돼야 한다. 그래서 outbound_date_fix import보다
# 앞에 둔다.
_OUTBOUND_NATIVE_WIDGETS = {
    "text_input": st.text_input,
    "checkbox": st.checkbox,
    "data_editor": st.data_editor,
    "markdown": st.markdown,
    "caption": st.caption,
}

from nohtus.pages.outbound_date_fix import page_outbound as _page_outbound  # noqa: E402


def page_outbound():
    """일반 출고지시에서는 수출대기용 위젯 패치가 절대 새지 않게 한다."""
    previous_widgets = {name: getattr(st, name) for name in _OUTBOUND_NATIVE_WIDGETS}
    st.session_state.pop("_outbound_screen_mode", None)
    try:
        for name, widget in _OUTBOUND_NATIVE_WIDGETS.items():
            setattr(st, name, widget)
        return _page_outbound()
    finally:
        for name, widget in previous_widgets.items():
            setattr(st, name, widget)
