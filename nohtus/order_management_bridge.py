"""발주관리(order-management) 앱을 WMS 프로세스 안에서 함께 띄우기 위한 연결부.

발주관리는 원래 독립 저장소(order_management_src/)로, 내부적으로
core_app/services/ui 같은 이름 없는(bare) import를 쓴다. 그 코드를 고치는
대신, 이 폴더를 sys.path에 넣어서 원래 쓰던 import가 그대로 동작하게 한다
(발주관리 자체의 app_layers/ 로딩 방식과 같은 요령이다).
"""
from __future__ import annotations

import sys
from pathlib import Path

_SRC_DIR = Path(__file__).resolve().parent.parent / "order_management_src"


def _ensure_on_path() -> None:
    src = str(_SRC_DIR)
    if src not in sys.path:
        sys.path.insert(0, src)


def render_order_management() -> None:
    """발주관리 화면 전체(사이드바 포함)를 현재 페이지에 그린다."""
    _ensure_on_path()
    from services.bootstrap import run

    run(_SRC_DIR)
