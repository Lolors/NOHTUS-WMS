# NOHTUS WMS Refactor V3.3 - Page Split

## 목적
V3.2에서 정상 동작 확인된 `app_runtime.py`를 추가로 슬림화했습니다.

## 변경 내용

### 1. 제품 매칭 관리 페이지 분리
- 기존: `nohtus/app_runtime.py` 내부 `page_product_matching()`
- 변경: `nohtus/pages/product_matching_runtime.py`

### 2. 마감 페이지 분리
- 기존: `nohtus/app_runtime.py` 내부 `page_closing()`
- 변경: `nohtus/pages/closing_runtime.py`

### 3. app_runtime.py 축소
- 약 2,147 lines → 약 1,906 lines
- main 라우팅 구조는 유지
- 기존 V3.2에서 정상 동작하던 실행 방식 유지

## 적용 방법
압축 파일을 기존 프로젝트 루트에 덮어씌웁니다.

포함 파일:
- app_slim.py
- nohtus/app_runtime.py
- nohtus/db_init.py
- nohtus/config_runtime.py
- nohtus/pages/mobile_stock.py
- nohtus/pages/search.py
- nohtus/pages/product_matching_runtime.py
- nohtus/pages/closing_runtime.py

`app_slim.py`는 필요 시 프로젝트 루트의 `app.py`로 교체해서 사용합니다.

## 확인 사항
- 문법 컴파일 확인 완료
- V3.2 기준 동작 방식 유지
- 다음 단계 후보:
  - 기준재고/엑셀 유틸 분리
  - 출고 엑셀/PDF/취소 로직 서비스 분리
  - app_runtime 내 미사용 레거시 페이지 함수 제거
