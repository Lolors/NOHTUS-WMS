# NOHTUS WMS Refactor V3.2 - app_runtime 1차 분리

V3.1이 정상 동작한 것을 기준으로, app_runtime.py 내부 잔여 코드를 추가 분리했습니다.

## 변경 사항

- `init_db()`를 `nohtus/db_init.py`로 이동
- 모바일 재고찾기 관련 함수와 페이지를 `nohtus/pages/mobile_stock.py`로 이동
- 단순 제품 검색 페이지를 `nohtus/pages/search.py`로 이동
- 공통 런타임 상수 일부를 `nohtus/config_runtime.py`로 분리
- `app_runtime.py`는 기존 라우팅과 아직 남은 레거시 함수 중심으로 축소

## 적용 방법

1. 압축을 프로젝트 루트에 덮어씁니다.
2. `app_slim.py`를 기존처럼 루트 `app.py`로 사용합니다.
3. 실행 후 확인할 메뉴:
   - 재고 찾기
   - 제품 검색
   - 입고 등록
   - 출고지시
   - 저장된 출고지시
   - 마감

## 주의

이번 단계는 안전 분리 단계입니다. 큰 페이지인 마감/제품매칭/출고 관련 유틸은 다음 단계에서 별도 파일로 분리하는 것이 좋습니다.
