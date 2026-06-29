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
  dates.py
  locations.py
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
tools/
  smoke_check.py
  apply_refactor_step1.py
  apply_refactor_step2.py
  apply_refactor_step3.py
  apply_refactor_step4.py
  apply_refactor_step5.py
  apply_refactor_step6.py
  apply_refactor_step7.py
  apply_refactor_step8.py
  apply_refactor_step9.py
```

## 현재 브랜치의 변경

- `nohtus/` 패키지 생성
- 설정/상수 후보를 `nohtus/config.py`로 분리
- DB helper 후보를 `nohtus/db.py`로 분리
- 사이드바 메뉴 구조 후보를 `nohtus/navigation.py`로 분리
- 날짜 helper 후보를 `nohtus/dates.py`로 분리
- 로케이션 helper 후보를 `nohtus/locations.py`로 분리
- `MASTER_MEMORY.md` 추가
- `tools/smoke_check.py` 추가
- `tools/apply_refactor_step1.py` 추가
- `tools/apply_refactor_step2.py` 추가
- `tools/apply_refactor_step3.py` 추가
- `tools/apply_refactor_step4.py` 추가
- `tools/apply_refactor_step5.py` 추가
- `tools/apply_refactor_step6.py` 추가
- `tools/apply_refactor_step7.py` 추가
- `tools/apply_refactor_step8.py` 추가
- `tools/apply_refactor_step9.py` 추가

## 리팩토링 원칙

1. `main`은 항상 안정 버전으로 둔다.
2. `app.py`를 GitHub 커넥터로 대량 교체하지 않는다.
3. 기능 이동은 한 번에 한 화면 또는 한 서비스 단위로만 한다.
4. 이동 후 기존 함수명 wrapper를 잠시 유지해서 회귀 위험을 낮춘다.
5. 입고 도면 JS Bridge는 마지막 단계까지 건드리지 않는다.
6. 각 단계 후 `python tools/smoke_check.py`를 실행한다.

## 로컬 적용 순서

### Step 1: 날짜/로케이션 helper 적용

```bash
python tools/apply_refactor_step1.py
python tools/smoke_check.py
streamlit run app.py
```

문제가 없으면 `app.py` 변경분을 커밋한다.

### Step 2: DB helper 적용

```bash
python tools/apply_refactor_step2.py
python tools/smoke_check.py
streamlit run app.py
```

문제가 없으면 `app.py` 변경분을 커밋한다.

### Step 3: 재고 서비스 함수 분리

```bash
python tools/apply_refactor_step3.py
python tools/smoke_check.py
streamlit run app.py
```

문제가 없으면 `app.py`와 `nohtus/services/inventory.py` 변경분을 함께 커밋한다.

### Step 4: 제품 서비스 함수 분리

```bash
python tools/apply_refactor_step4.py
python tools/smoke_check.py
streamlit run app.py
```

문제가 없으면 `app.py`와 `nohtus/services/products.py` 변경분을 함께 커밋한다.

### Step 5: 이력 서비스 함수 분리

```bash
python tools/apply_refactor_step5.py
python tools/smoke_check.py
streamlit run app.py
```

옮길 대상 함수가 없으면 스크립트가 변경 없이 중단된다. 문제가 없으면 `app.py`와 `nohtus/services/history.py` 변경분을 함께 커밋한다.

### Step 6: 이력 조회 화면 분리

```bash
python tools/apply_refactor_step6.py
python tools/smoke_check.py
streamlit run app.py
```

문제가 없으면 `app.py`와 `nohtus/pages/history.py` 변경분을 함께 커밋한다.

### Step 7: 이동 등록 화면 분리

```bash
python tools/apply_refactor_step7.py
python tools/smoke_check.py
streamlit run app.py
```

문제가 없으면 `app.py`와 `nohtus/pages/move.py` 변경분을 함께 커밋한다.

### Step 8: 재고 실사 화면 분리

```bash
python tools/apply_refactor_step8.py
python tools/smoke_check.py
streamlit run app.py
```

문제가 없으면 `app.py`와 `nohtus/pages/stocktake.py` 변경분을 함께 커밋한다.

### Step 9: 로케이션맵 화면 분리

```bash
python tools/apply_refactor_step9.py
python tools/smoke_check.py
streamlit run app.py
```

문제가 없으면 `app.py`와 `nohtus/pages/location_map.py` 변경분을 함께 커밋한다.

## 다음 단계

1. 출고 등록 화면을 `nohtus/pages/outbound.py`로 이동한다.
2. 마감 로직을 서비스 모듈로 이동한다.
3. 입고 등록 화면은 마지막에 가깝게 이동한다.

## 검증 방법

```bash
python tools/smoke_check.py
streamlit run app.py
```

수동 확인 화면:

- 입고 등록
- 로케이션맵
- 제품 검색
- 이동 등록
- 재고 실사
- 이력 조회
- 마감
