"""여러 페이지가 st.text_input/st.button 등 streamlit 전역 함수를 임시로
바꿔치기(monkey patch)했다가 렌더링이 끝나면 되돌리는 패턴을 쓴다.

streamlit은 세션(브라우저 탭)마다 별도 스레드에서 스크립트를 돌리지만,
`streamlit` 모듈 자체와 그 안의 함수 슬롯은 프로세스 전체가 공유한다.
그래서 두 사용자가 이런 페이지를 동시에 열면, 한쪽이 되돌린 원본 함수가
사실은 다른 쪽이 방금 걸어둔 패치본이거나, 한쪽의 finally 복원이 다른 쪽이
아직 패치 상태를 쓰는 도중에 끼어드는 경합이 생길 수 있다. 이 경합은
같은 위젯 key가 한 번의 스크립트 실행에서 두 번 만들어지는 것처럼 보이는
StreamlitDuplicateElementKey 같은 오류로 나타난다.

이 락으로 "patch → 렌더 → restore" 구간을 앱 전체에서 직렬화해 경합을
막는다. RLock을 쓰는 이유: 일부 페이지(예: 수출대기 등록)가 다른 패치
페이지(출고지시)를 같은 스레드 안에서 그대로 호출하므로, 같은 스레드가
락을 다시 잡아도 막히지 않아야 한다.
"""

from __future__ import annotations

import threading

STREAMLIT_PATCH_LOCK = threading.RLock()
