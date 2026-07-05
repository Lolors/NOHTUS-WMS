# NOHTUS WMS Refactor V3.5 - Service/Util Split

## 적용 기준
- V3.4 정상 동작 확인 후 적용
- 기존 구조 유지: app_slim.py -> nohtus.app_runtime.main()

## 이번 변경
- app_runtime.py에 남아 있던 제품/입고 보조 함수 분리
  - nohtus/services/product_runtime.py
- 기준재고 업로드/보완 엑셀 보조 함수 분리
  - nohtus/services/baseline_runtime.py
- ERP 데이터 업로드 화면 및 엑셀 컬럼 정리 유틸 분리
  - nohtus/pages/erp_upload_runtime.py

## 결과
- nohtus/app_runtime.py 약 1,487줄 -> 약 1,021줄
- app_runtime.py는 아직 일부 화면 렌더링 함수가 남아 있지만, 서비스성 함수는 추가로 많이 제거됨

## 적용 방법
1. 압축을 프로젝트 루트에 덮어쓰기
2. 현재처럼 app.py는 V3.1에서 만든 슬림 진입점 유지
3. 실행 확인

## 다음 후보
- 로케이션맵 상세/검색 렌더링 분리
- 저장된 출고지시 런타임 화면 완전 제거 여부 확인
- 입고 구버전 page_inbound 제거 또는 별도 legacy 모듈 이동
