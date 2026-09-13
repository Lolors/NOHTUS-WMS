"""일반 출고지시 메뉴 진입점.

`outbound_business.py` 등 다른 출고 관련 화면이 렌더링 중 일부 Streamlit
위젯을 임시로 바꿔치기한다. 그 패치가 일반 출고지시 화면으로 새지 않도록,
앱 시작 시점의 원본 위젯을 여기 보관해뒀다가 매번 강제로 복구한 뒤
렌더링한다.

`outbound_business.py`는 이 캡처된 네이티브 위젯 일부(_BASE_TEXT_INPUT 등)를
자기 모듈이 처음 import된 시점에 한 번만 저장해두고 "수출대기 재사용 렌더링"
모드에서 그걸 원본으로 간주한다. 그 시점에 이미 다른 패치가 걸려있었다면
영구히 잘못된 값을 들고 있게 되므로, 일반 출고지시 화면이 열릴 때마다
여기서 진짜 네이티브 위젯으로 다시 맞춰준다.
"""

from __future__ import annotations

import streamlit as st

# 다른 페이지 모듈이 import되면서 st.* 위젯을 건드리기 전에(모듈 레벨
# monkey-patch가 실제로 있다 — 예: outbound_lot_warning.py의 st.button)
# 반드시 이 캡처가 먼저 실행돼야 한다. 그래서 outbound_business import보다
# 앞에 둔다.
_OUTBOUND_NATIVE_WIDGETS = {
    "text_input": st.text_input,
    "checkbox": st.checkbox,
    "data_editor": st.data_editor,
    "markdown": st.markdown,
    "caption": st.caption,
}

from nohtus.pages import outbound_business  # noqa: E402
from nohtus.pages.outbound_business import page_outbound as _page_outbound  # noqa: E402

_OUTBOUND_BUSINESS_BASE_ATTRS = {
    "_BASE_TEXT_INPUT": "text_input",
    "_BASE_CHECKBOX": "checkbox",
    "_BASE_DATA_EDITOR": "data_editor",
    "_BASE_MARKDOWN": "markdown",
    "_BASE_CAPTION": "caption",
}


def page_outbound():
    """일반 출고지시에서는 수출대기용 위젯 패치가 절대 새지 않게 한다."""
    previous_widgets = {name: getattr(st, name) for name in _OUTBOUND_NATIVE_WIDGETS}
    previous_base_attrs = {
        attr: getattr(outbound_business, attr) for attr in _OUTBOUND_BUSINESS_BASE_ATTRS
    }
    st.session_state.pop("_outbound_screen_mode", None)
    try:
        for name, widget in _OUTBOUND_NATIVE_WIDGETS.items():
            setattr(st, name, widget)
        for attr, widget_name in _OUTBOUND_BUSINESS_BASE_ATTRS.items():
            setattr(outbound_business, attr, _OUTBOUND_NATIVE_WIDGETS[widget_name])
        return _page_outbound()
    finally:
        for name, widget in previous_widgets.items():
            setattr(st, name, widget)
        for attr, widget in previous_base_attrs.items():
            setattr(outbound_business, attr, widget)
