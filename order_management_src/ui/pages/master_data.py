"""기초정보 관리 화면의 전용 라우터."""
from __future__ import annotations

PAGES = {"거래처 관리", "제품 관리", "별칭 관리"}


def handles(page: str) -> bool:
    return page in PAGES


def render(page: str, core_app, data) -> None:
    # 기존 페이지들은 app_layers 호환 경로가 준비된 뒤에 불러와야 합니다.
    # 이 지연 import는 기초정보 라우터 자체가 발주 런타임에 결합되는 것을 막습니다.
    from ui.pages import alias_manage, catalog

    routes = {
        "거래처 관리": lambda: catalog.vendors(core_app, data),
        "제품 관리": lambda: catalog.products(core_app, data),
        "별칭 관리": lambda: alias_manage.render(core_app, data),
    }
    routes[page]()
