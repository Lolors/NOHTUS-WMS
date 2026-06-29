# Refactoring Plan

이 브랜치는 NOHTUS WMS를 기능별 구조로 나누기 위한 리팩토링 브랜치이다.

## 목표 구조

```text
app.py
nohtus/
  __init__.py
  config.py
  db.py
  navigation.py
  services/
    products.py
    inventory.py
    outbound.py
    history.py
  pages/
    map.py
    inbound.py
    outbound.py
    move.py
    stocktake.py
    product_matching.py
    customers.py
    closing.py
  ui/
    layout.py
    formatters.py
styles.py
inbound_map.py
MASTER_MEMORY.md
docs/
  REFACTORING.md
```

## 현재 브랜치의 1차 변경

- `nohtus/` 패키지 생성
- 설정/상수 후보를 `nohtus/config.py`로 분리
- DB helper 후보를 `nohtus/db.py`로 분리
- 사이드바 메뉴 구조 후보를 `nohtus/navigation.py`로 분리
- `MASTER_MEMORY.md` 추가

## 다음 단계

1. `app.py`에서 `APP_TITLE`, `VERSION`, `DB_PATH`, `COMPANIES`, `AREA_CONFIG`, `AREA_COLOR`를 `nohtus.config` import로 교체한다.
2. `connect`, `q`, `exec_sql`를 `nohtus.db` import로 교체한다.
3. 메뉴 렌더링을 `nohtus.navigation.MENU_SECTIONS` 기준으로 바꾼다.
4. 화면 함수는 한 번에 하나씩 `nohtus/pages/`로 이동한다.
5. 업무 로직 함수는 화면 함수보다 먼저 `nohtus/services/`로 이동한다.

## 주의사항

- 입고 도면 JS Bridge는 마지막 단계까지 건드리지 않는다.
- 기능 이동 후에는 기존 함수명 wrapper를 잠시 유지해서 회귀 위험을 낮춘다.
- `main`은 항상 안정 버전으로 둔다.
