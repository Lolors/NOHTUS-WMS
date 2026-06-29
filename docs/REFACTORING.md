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
  refactor.py
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
- `tools/refactor.py` 추가
- `tools/apply_refactor_step1.py` ~ `tools/apply_refactor_step9.py` 추가

## 리팩토링 원칙

1. `main`은 항상 안정 버전으로 둔다.
2. `app.py`를 GitHub 커넥터로 대량 교체하지 않는다.
3. 기능 이동은 한 번에 한 화면 또는 한 서비스 단위로만 한다.
4. 이동 후 기존 함수명 wrapper를 잠시 유지해서 회귀 위험을 낮춘다.
5. 입고 도면 JS Bridge는 마지막 단계까지 건드리지 않는다.
6. 각 단계 후 `python tools/smoke_check.py`를 실행한다.

## 공통 리팩토링 엔진 사용법

Step별 스크립트를 계속 만들지 않아도 아래 명령으로 페이지/서비스 함수를 이동할 수 있다.

### 페이지 함수 이동

```bash
python tools/refactor.py move-page page_outbound outbound
python tools/refactor.py move-page page_closing closing
python tools/refactor.py move-page page_product_matching product_matching
python tools/refactor.py move-page page_customers customers
```

형식:

```bash
python tools/refactor.py move-page <app.py의 함수명> <nohtus/pages에 만들 파일명>
```

예:

- `page_outbound` → `nohtus/pages/outbound.py`
- `page_closing` → `nohtus/pages/closing.py`

### 서비스 함수 이동

```bash
python tools/refactor.py move-service closing compare_erp_stock today_outbound_check
python tools/refactor.py move-service outbound create_outbound_order save_outbound_order
```

형식:

```bash
python tools/refactor.py move-service <nohtus/services에 만들 파일명> <함수명1> <함수명2> ...
```

엔진은 자동으로 다음 작업을 수행한다.

- 백업 생성
- 함수 추출
- 새 모듈 생성 또는 기존 모듈에 추가
- `app.py` import 추가
- Python compile 검사
- `tools/smoke_check.py` 실행
- 실패 시 백업에서 자동 복구

## 기존 Step별 로컬 적용 순서

### Step 1: 날짜/로케이션 helper 적용

```bash
python tools/apply_refactor_step1.py
python tools/smoke_check.py
streamlit run app.py
```

### Step 2: DB helper 적용

```bash
python tools/apply_refactor_step2.py
python tools/smoke_check.py
streamlit run app.py
```

### Step 3: 재고 서비스 함수 분리

```bash
python tools/apply_refactor_step3.py
python tools/smoke_check.py
streamlit run app.py
```

### Step 4: 제품 서비스 함수 분리

```bash
python tools/apply_refactor_step4.py
python tools/smoke_check.py
streamlit run app.py
```

### Step 5: 이력 서비스 함수 분리

```bash
python tools/apply_refactor_step5.py
python tools/smoke_check.py
streamlit run app.py
```

### Step 6: 이력 조회 화면 분리

```bash
python tools/apply_refactor_step6.py
python tools/smoke_check.py
streamlit run app.py
```

### Step 7: 이동 등록 화면 분리

```bash
python tools/apply_refactor_step7.py
python tools/smoke_check.py
streamlit run app.py
```

### Step 8: 재고 실사 화면 분리

```bash
python tools/apply_refactor_step8.py
python tools/smoke_check.py
streamlit run app.py
```

### Step 9: 로케이션맵 화면 분리

```bash
python tools/apply_refactor_step9.py
python tools/smoke_check.py
streamlit run app.py
```

## 다음 단계

1. 공통 엔진으로 출고 등록 화면을 `nohtus/pages/outbound.py`로 이동한다.
2. 공통 엔진으로 제품매칭/거래처/마감 화면을 이동한다.
3. 마감/출고 관련 서비스 함수를 `nohtus/services/`로 이동한다.
4. 입고 등록 화면은 마지막에 가깝게 이동한다.

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
