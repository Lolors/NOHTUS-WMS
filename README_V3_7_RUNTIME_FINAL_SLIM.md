# NOHTUS WMS Refactor V3.7 - Runtime Final Slim

## 기준
- V3.6 정상 실행 확인 이후 진행
- 이번 단계도 기능 변경 없이 app_runtime.py 슬림화 중심

## 변경 내용

### 1) app_runtime.py 대폭 축소
- 기존 약 700줄 → 약 93줄
- 이제 app_runtime.py는 거의 실행 라우터 역할만 담당
- 앱 초기화, 스타일 적용, 사이드바 메뉴 분기만 유지

### 2) 저장된 출고지시 보조 함수 분리
신규 파일:
- nohtus/pages/saved_outbound_runtime.py

이관 내용:
- render_saved_orders
- 출고지시 취소 확인 모달/인라인 카드
- 취소 실행 후 session_state 정리
- 기존 저장된 출고지시 레거시 화면 함수

주의:
- 현재 main에서는 기존 refactored 페이지인 nohtus.pages.saved_outbound.page_saved_outbound를 계속 사용
- 이번 파일은 레거시 보조 함수 보존/분리 목적

### 3) 입고 위치 연동 보조 함수 분리
신규 파일:
- nohtus/services/inbound_bridge_runtime.py

이관 내용:
- _inbound_js_loc_changed
- _apply_inbound_location_pending
- 기존 입고 레거시 화면 함수는 _legacy_page_inbound_removed 이름으로 보존

주의:
- 현재 main에서는 기존 refactored 페이지인 nohtus.pages.inbound.page_inbound를 계속 사용
- 입고 핵심 기능은 건드리지 않음

## 결과
- app.py: slim 실행 파일 유지
- nohtus/app_runtime.py: 약 93줄
- runtime 파일이 사실상 라우터 수준까지 정리됨

## 적용 방법
1. 기존 V3.6 프로젝트에 압축 파일 내용 덮어쓰기
2. app_slim.py는 필요 시 루트의 app.py로 사용
3. Streamlit 실행

## 다음 단계 제안
- V3.8에서는 app_runtime.py의 상수들을 config_runtime.py 또는 config.py로 이동
- 최종적으로 app_runtime.py는 30~50줄 수준까지 축소 가능
