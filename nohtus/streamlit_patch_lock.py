"""여러 페이지가 st.text_input/st.button 등 streamlit 전역 함수나 다른 모듈의
함수를 임시로 바꿔치기(monkey patch)했다가 렌더링이 끝나면 되돌리는 패턴을 쓴다.

streamlit은 세션(브라우저 탭)마다 별도 스레드에서 스크립트를 돌리지만,
`streamlit` 모듈 자체와 그 안의 함수 슬롯은 프로세스 전체가 공유한다. 예전에는
이 문제를 전역 RLock으로 "patch → 렌더 → restore" 구간 전체를 앱 전체에서
직렬화해서 풀었는데, 그러면 두 사용자가 이 페이지들 중 아무거나 동시에 열어도
한쪽의 DB 조회+렌더링이 끝날 때까지 다른 쪽이 완전히 멈춰버리는 문제가 있었다
(사용자가 늘수록 체감 속도가 급격히 느려짐).

이 모듈은 대신 각 (모듈, 속성이름) 쌍을 "프로세스 전체에 딱 한 번" 디스패처로
감싸두고, 실제 어떤 함수를 쓸지는 **스레드 로컬**에 스택으로 저장한다. Streamlit이
세션마다 별도 스레드에서 스크립트를 실행하므로, 이렇게 하면 세션끼리 서로의
patch를 절대 보지 못하면서도 렌더링 자체는 락 없이 완전히 병렬로 돈다. 락은
디스패처를 처음 설치하는 찰나(속성 하나당 프로세스 생애주기에 한 번)에만 잡는다.

같은 스레드 안에서 patched()가 중첩 호출되는 경우(예: 수출대기 등록 화면이
일반 출고지시 렌더러를 그대로 재사용하는 경우)는 스택이 자연스럽게 처리한다 —
안쪽 patched()가 만든 함수가 `current()`로 바깥쪽 patch를 원본처럼 참조하면
합성(compose)되고, `true_original()`로 참조하면 바깥쪽 patch를 건너뛴다.
"""

from __future__ import annotations

import threading
from contextlib import contextmanager

from streamlit.errors import StreamlitDuplicateElementKey

# (owner, attr) 디스패처 설치 자체를 보호하는 락. 프로세스 생애주기 동안 속성 하나당
# 딱 한 번만 잡히고, 렌더링 도중에는 절대 걸리지 않는다.
_INSTALL_LOCK = threading.Lock()

# (id(owner), attr) -> 한 번도 patch되지 않은 진짜 원본 함수.
_TRUE_ORIGINALS: dict[tuple[int, str], object] = {}

# 이미 디스패처를 설치한 (id(owner), attr) 집합.
_INSTALLED: set[tuple[int, str]] = set()

# 세션(=스레드)마다 독립적인 patch 스택. {(id(owner), attr): [fn, ...]}
_local = threading.local()


def _stacks() -> dict[tuple[int, str], list]:
    stacks = getattr(_local, "stacks", None)
    if stacks is None:
        stacks = {}
        _local.stacks = stacks
    return stacks


def _install(owner, attr: str) -> None:
    key = (id(owner), attr)
    if key in _INSTALLED:
        return
    with _INSTALL_LOCK:
        if key in _INSTALLED:
            return
        true_fn = getattr(owner, attr)
        _TRUE_ORIGINALS[key] = true_fn

        def _dispatcher(*args, __key=key, __true=true_fn, **kwargs):
            stack = _stacks().get(__key)
            fn = stack[-1] if stack else __true
            return fn(*args, **kwargs)

        setattr(owner, attr, _dispatcher)
        _INSTALLED.add(key)


def true_original(owner, attr: str):
    """이 속성의 patch되기 전 진짜 원본 함수. 바깥쪽에서 걸린 patch까지 건너뛰고
    싶을 때 쓴다(예: 수출대기 등록 화면이 일반 출고지시의 거래처 UI patch를
    그대로 물려받지 않으려는 경우)."""
    _install(owner, attr)
    return _TRUE_ORIGINALS[(id(owner), attr)]


def current(owner, attr: str):
    """이 스레드(=세션) 기준으로 지금 유효한 함수. 아무 patch도 없으면 원본과
    같다. 바깥쪽 patch 위에 이어붙이고(compose) 싶을 때 이 값을 fallback으로
    쓴다."""
    _install(owner, attr)
    stack = _stacks().get((id(owner), attr))
    return stack[-1] if stack else _TRUE_ORIGINALS[(id(owner), attr)]


@contextmanager
def patched(overrides: dict):
    """overrides: {(owner, attr_name): replacement_fn}

    각 항목을 이 스레드에만 보이는 patch로 등록한다. 디스패처 설치는 (owner,
    attr)당 프로세스 전체에서 한 번만 일어나고, 그 뒤로는 스레드별 스택을
    디스패처가 조회하므로 세션끼리 서로의 patch를 절대 보지 않는다. `with`
    블록 본문(렌더링) 동안은 어떤 락도 걸리지 않는다.
    """
    pushed = []
    try:
        for (owner, attr), fn in overrides.items():
            _install(owner, attr)
            key = (id(owner), attr)
            _stacks().setdefault(key, []).append(fn)
            pushed.append(key)
        yield
    finally:
        for key in reversed(pushed):
            stack = _stacks().get(key)
            if stack:
                stack.pop()


def call_or_reuse(widget_fn, *args, key, session_state, **kwargs):
    """`widget_fn(*args, key=key, **kwargs)`을 호출하되, 같은 스크립트 실행에서
    그 key로 이미 위젯이 등록돼 StreamlitDuplicateElementKey가 나면 페이지를
    죽이는 대신 session_state에 남아있는 값을 그대로 돌려준다.

    세션 간 patch 경합은 더 이상 이 상황을 유발하지 않지만, 같은 세션 안에서
    위젯이 실수로 두 번 호출되는 경로가 있을 수 있어 마지막 방어선으로 남겨둔다.
    """
    try:
        return widget_fn(*args, key=key, **kwargs)
    except StreamlitDuplicateElementKey:
        return session_state.get(key, kwargs.get("value"))
