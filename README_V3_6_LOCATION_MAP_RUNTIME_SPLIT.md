# NOHTUS WMS Refactor V3.6 - Location Map Runtime Split

## 목적
V3.5에서 정상 동작 확인된 구조를 기준으로 `app_runtime.py`에 남아 있던 로케이션맵 상세/검색 렌더링 함수를 별도 모듈로 분리했습니다.

## 변경 내용

### 신규 파일
- `nohtus/pages/location_map_runtime.py`

### 이동한 함수
- `has_stock_map()`
- `loc_has_stock()`
- `set_loc()`
- `get_loc()`
- `_loc_group_from_df()`
- `location_zone_name()`
- `level_label()`
- `format_history_rows()`
- `render_product_detail()`
- `render_detail()`
- `page_map_search_results()`
- `_map_search_changed()`

### 유지 방식
`app_runtime.py`에서는 위 함수들을 import해서 기존 이름을 그대로 유지합니다.
따라서 다른 모듈이 기존 경로를 참조하더라도 동작 영향이 적도록 처리했습니다.

## 결과
- `app_runtime.py` 약 1,021줄 → 약 700줄
- 로케이션맵 상세/제품검색 UI 로직이 `pages/location_map_runtime.py`로 분리됨

## 확인
- Python 문법 컴파일 확인 완료
  - `nohtus/app_runtime.py`
  - `nohtus/pages/location_map_runtime.py`

## 다음 단계 후보
- 저장된 출고지시 화면 보조 함수 분리
- 입고 위치 연동 보조 함수 분리
- 남은 `app_runtime.py`를 500줄 이하로 축소
