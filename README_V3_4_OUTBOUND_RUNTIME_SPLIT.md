# NOHTUS WMS Refactor V3.4 - Outbound Runtime Split

## 목적
V3.3에서 정상 동작 확인된 구조를 기준으로 `nohtus/app_runtime.py`에 남아 있던 출고 관련 유틸/서비스 함수를 `nohtus/services/outbound_runtime.py`로 분리했습니다.

## 변경 파일
- `nohtus/app_runtime.py`
  - 출고 엑셀/PDF 생성, 출고 취소/부분취소, 피킹 정렬, 거래 로그 함수 등을 import 방식으로 변경
  - 라인 수 약 1,906줄 → 약 1,487줄
- `nohtus/services/outbound_runtime.py`
  - 신규 파일
  - 출고 관련 런타임 유틸 함수 보관
- `app_slim.py`
  - 기존 V3.3과 동일한 얇은 진입점 유지

## 분리된 주요 함수
- `outbound_excel_bytes()`
- `outbound_pdf_bytes()`
- `outbound_erp_note_for_row()`
- `sort_outbound_rows_for_picking()`
- `product_total_stock()`
- `insert_transaction_log()`
- `create_outbound_instruction()`
- `load_outbound_order()`
- `build_outbound_order_title()`
- `cancel_outbound_order()`
- `restore_inventory_from_log()`
- `cancel_saved_order()`
- `partial_cancel_outbound_order()`
- `outbound_inventory()`
- `recommend_picks()`
- `first_nonblank()`
- `product_mapping_name_for()`
- `product_compare_name_for()`

## 적용 방법
1. 압축 파일을 프로젝트 루트에 덮어씁니다.
2. `app_slim.py`를 사용하는 구조라면 기존처럼 루트의 `app.py`로 교체합니다.
3. Streamlit 실행 후 아래 메뉴를 확인합니다.
   - 출고지시
   - 저장된 출고지시
   - 마감
   - 입고 등록
   - 로케이션 맵

## 주의
이번 버전은 구조 분리 위주입니다. 화면 동작 변경은 의도하지 않았습니다.
