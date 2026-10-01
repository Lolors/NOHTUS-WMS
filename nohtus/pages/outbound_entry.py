"""일반 출고지시 메뉴 진입점.

예전에는 `outbound_business.py`가 st.* 위젯을 전역으로 직접 바꿔치기했기
때문에, 이 진입점에서 앱 시작 시점의 원본 위젯을 캡처해뒀다가 매번 강제로
복구한 뒤 렌더링해야 했다. 지금은 nohtus.streamlit_patch_lock의 patch가
스레드-로컬 스택으로 격리되고(다른 세션/화면의 patch가 애초에 보이지 않음),
"수출대기 화면이 이미 patch를 걸어둔 채로 일반 출고지시를 여는" 경우는
outbound_business.page_outbound() 자신이 is_export_waiting 분기에서
true_original()로 직접 처리한다. 그래서 여기서 다시 st.* 슬롯을 건드리면
오히려 nohtus.streamlit_patch_lock이 설치해 둔 디스패처를 지워버려서
patch 자체가 먹통이 된다(2026-09-16 회귀: 재고 선택 옵션이 안 지워지고
이번 품목 출고 추천이 하나도 안 뜨던 사고).

이 진입점이 실제로 책임져야 하는 건 "화면 모드 플래그 정리"뿐이다.
"""

from __future__ import annotations

import streamlit as st

from nohtus.pages.outbound_business import page_outbound as _page_outbound


def page_outbound():
    """일반 출고지시 진입 시, 수출대기 화면 모드로 남아있던 플래그를 지운다."""
    st.session_state.pop("_outbound_screen_mode", None)
    return _page_outbound()
