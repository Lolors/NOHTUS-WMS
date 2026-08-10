# NOHTUS WMS 개발 인수인계

최종 갱신: 2026-08-10  
현재 개발 기준 브랜치: `agent/export-program-link`

이 문서는 새 개발자 또는 AI가 기존 업무 규칙을 깨뜨리지 않고 개발을 이어가기 위한 실무 안내서다. 먼저 이 문서를 읽고, 세부 사양은 `docs/MASTER_MEMORY.md`, `docs/PRODUCT_SPEC.md`, `docs/DB_SCHEMA.md`, `docs/development_rules.md`를 확인한다. 문서와 코드가 다르면 현재 브랜치의 코드와 테스트를 기준으로 판단하되, 차이를 문서에도 즉시 반영한다.

## 1. 시스템 목적과 불변 규칙

NOHTUS WMS는 노투스팜 물류팀의 실제 창고 재고를 관리하는 Python/Streamlit/SQLite 애플리케이션이다. ERP를 대체하지 않으며 ERP 자료와 현장 재고를 연결한다.

- 재고 식별의 핵심 키는 `사업장 + 표준제품명 + 원본명(warehouse_name) + LOT + 유통기한 + 로케이션`이다.
- 사업장은 `노투스팜`, `노투스`, `NOH`, `비자료` 네 개가 기준이다. `등록대기`는 입고 전용이다.
- ERP 제품/거래처 코드는 문자열이다. `003` 같은 선행 0을 절대 숫자 변환으로 잃지 않는다.
- `products.standard_name`은 검색·집계의 중심 마스터 값이다. 변경 시 재고, 출고, 이동, 실사, 마감, ERP 비교, 로그와 이력에 미치는 영향을 함께 확인한다.
- 제품매칭표를 다시 업로드해도 기존 `image_path` 및 사진 연결은 보존한다. 사진을 삭제하거나 초기화하지 않는다.
- `inventory`는 현재 상태, `transactions`는 변화 이력이다. 삭제보다 이력 보존을 우선한다.
- `transactions.final_stock`은 화면 조회 시 재계산한 값이 아니라 해당 거래 직후 같은 표준제품명의 전체 수량이다.

## 2. 실행과 주요 경로

Windows 운영 환경에서는 저장소 루트의 `run_wms.bat`를 실행한다. 직접 실행은 다음과 같다.

```bash
python -m streamlit run app.py
```

- DB: `data/nohtus.db` — 운영 DB를 Git에 커밋하지 않는다.
- 설정: `nohtus/config.py`
- 앱 초기화/라우팅: `nohtus/application.py`
- 화면: `nohtus/pages/`
- DB 및 업무 로직: `nohtus/services/`
- 공통 UI: `nohtus/ui/`
- 테이블 생성/마이그레이션: `nohtus/db_init.py` 및 각 레거시 호환 보강 함수

`app.py`에는 진입점만 둔다. 신규 SQL과 재고 변경 로직은 화면 파일에 추가하지 말고 서비스로 분리한다. 다만 현재는 호환용 `*_business.py`, `*_runtime.py`, `*_fix.py` 래퍼와 Streamlit monkey patch가 남아 있으므로, 참조 경로를 확인하지 않은 이름 변경이나 삭제는 금지한다.

## 3. 로케이션 의미

- `P`: 수출대기. 일반 출고에서 선택하지 않는다.
- `Q`: 유통기한 임박.
- `REC`: 매입등록대기.
- `F1`: 비자료 계열.
- 그 밖에 A1~E1, G1/G2, T1/T2, X1/X2, R1/R2, N과 특수 위치가 있다.
- 특수 위치 목록은 `nohtus/config.py`가 단일 기준이다.

입고 도면 클릭과 JS Bridge는 Core Freeze 영역이다. `inbound_map.py`, `render_inbound_quick_location_map()`, `location_picker()`, `_apply_inbound_location_pending()`, `_inbound_js_loc_changed()`는 UI 정리 목적으로 임의 변경하지 않는다.

## 4. 출고지시 핵심 흐름

관련 파일:

- 기본 화면/거래처 검색: `nohtus/pages/outbound.py`
- 현재 진입 래퍼: `nohtus/pages/outbound_business.py`, `nohtus/pages/outbound_date_fix.py`
- 저장과 재고 처리: `nohtus/services/outbound_orders.py`, `nohtus/services/outbound.py`
- 저장된 지시서: `nohtus/pages/saved_outbound*.py`

업무 규칙:

- 거래처를 검색해 사업장을 정하고, 해당 사업장의 출고 가능 재고를 선택한다.
- 요청수량이 현재고보다 많으면 저장하지 않는다.
- 수정 시 제목만 바뀌면 제목 이력만 남기고, 품목/수량 변경은 차이만 재고와 이력에 반영한다.
- 취소 시 차감한 재고를 복구한다.
- `P` 및 출고불가(`is_shippable=0`) 재고는 일반 출고 후보에서 제외한다.
- 최근 거래일은 같은 `거래처명 + 사업장` 자료만 사용한다. 이름만 같은 다른 사업장 날짜를 섞지 않는다.

2026-08-10 회귀 수정: 수출대기 화면이 Streamlit 위젯을 monkey patch한 뒤 일반 출고지시에 영향이 남아 거래처 검색창이 사라질 수 있었다. 일반 출고는 화면 진입 시점의 위젯을 사용하고, 수출대기만 원본 위젯을 사용하도록 분리했다. 관련 테스트는 `tests/test_outbound_customer_search_restore.py`다.

## 5. 수출대기/수출확정 핵심 흐름

관련 파일:

- 등록/수정 화면: `nohtus/pages/export_waiting.py`
- 저장 목록/확정 UI: `nohtus/pages/saved_export_waiting.py`
- 트랜잭션과 상태 처리: `nohtus/services/export_waiting.py`
- ERP 매출 엑셀: `nohtus/services/export_waiting_excel.py`

상태와 재고 흐름:

1. 수출대기 등록 시 선택 재고를 같은 사업장의 원래 로케이션에서 `P`로 이동한다.
2. 각 품목은 `waiting_inventory_id`로 정확한 P 재고 행을 가리킨다.
3. 확정 시 품목별 사업장·ERP 매출처를 저장하고 P 재고를 출고 처리한다.
4. 전체 확정 전에는 `waiting` 또는 `partial`, 전체 확정 후에는 `confirmed`다.
5. 출고일자는 전체 확정 흐름과 저장 규칙을 함께 확인한다.

반드시 지킬 수정 규칙:

- 확정된 주문도 주문 정보와 출고 리스트를 수정할 수 있다.
- 기존 확정 품목의 남아 있는 수량은 기존 `confirmed_company`, `confirmed_customer_*`, `confirmed_at`을 유지한다.
- 기존 3EA를 5EA로 늘리면 기존 확정 3EA는 그대로 두고 증가분 2EA만 미확정 수출대기 품목으로 추가한다.
- 기존 3EA를 1EA로 줄이면 감소분 2EA만 원래 재고로 복구하고, 남은 1EA의 확정 정보는 유지한다.
- 새 제품은 미확정 수출대기로 추가하며, 그 품목만 사업장·매출처를 새로 선택한다.
- 재고 부족이나 중간 오류가 발생하면 주문 정보, 품목, 재고, 이력을 모두 한 트랜잭션으로 롤백한다.
- ERP 매출처와 출고일자는 의도하지 않은 수정으로 초기화하지 않는다.

P 재고 연결 규칙:

- `waiting_inventory_id`가 유효하면 ID를 우선한다.
- ID가 끊겼을 때는 `사업장 + 제품명 + 원본명 + LOT + 유통기한 + 필요수량`을 모두 만족하는 P 재고 후보가 정확히 하나일 때만 자동 복구한다.
- 후보가 없거나 여러 개면 임의 연결하지 않고 사용자가 검색해 연결한다.
- 제품명이 비슷하다는 이유로 fallback 연결하지 않는다.
- 수량 부족과 제품/연결 불일치 안내를 구분한다.

거래처 검색 UI:

- 일반 출고지시에는 거래처 검색이 항상 보여야 한다.
- 수출대기 신규 등록은 국가·바이어·운송방식·수출번호 중심의 기존 제한을 유지한다.
- 수출대기 수정 화면에서는 거래처 검색·선택을 사용할 수 있다.
- 한 화면의 monkey patch가 rerun 뒤 다른 화면에 남지 않도록 `try/finally` 복원을 유지한다.

## 6. 재고실사와 ERP 비교

- ERP 총합 행과 비용 항목은 비교 대상에서 제외한다.
- ERP 코드 열은 텍스트로 유지한다.
- 비교 결과는 동일 표준제품명의 LOT·유통기한별 행을 구분한다.
- 무시 목록은 비교 수량에 즉시 반영하며, 기존 무시 항목에서는 `차이 원인`만 수정 가능하다.
- 빈 사유는 저장하지 않는다. 다른 필드는 수정하지 않으며 무시 해제 기능을 유지한다.
- 제품명 변경이나 동일 ERP명 공유가 실사 결과를 합쳐버리지 않는지 확인한다.

현재 기본 작업 사본에 재고실사 관련 별도 미커밋 변경이 존재했던 이력이 있으므로, 다른 브랜치 작업 시 `git status -sb`와 파일별 diff를 먼저 보고 절대 `git add -A`로 섞지 않는다.

## 7. 테스트와 안전한 변경 절차

최소 검증:

```bash
python -m compileall -q app.py nohtus tests
python -m unittest discover -s tests -p "test_*.py"
git diff --check
```

환경에 `pytest`가 있으면 관련 테스트만 먼저 실행하고 전체 테스트를 이어서 실행한다. Streamlit이 없는 환경에서는 서비스 단위 테스트와 AST 회귀 테스트를 우선하고, 실제 운영 환경에서 화면 진입·검색·저장·rerun을 수동 확인한다.

수출대기 변경 시 우선 실행할 테스트:

- `tests/test_confirmed_export_waiting_edit.py`
- `tests/test_export_waiting_p_link_repair.py`
- `tests/test_export_waiting_customer_search.py`
- `tests/test_outbound_customer_search_restore.py`
- `tests/test_export_waiting_merge.py`
- `tests/test_export_waiting_excel.py`
- `tests/test_inventory_history_consistency.py`

DB 변경 테스트는 운영 DB 복사본 또는 임시 SQLite DB에서 수행한다. 정상 경로뿐 아니라 재고 부족, 후보 중복, 끊어진 ID, 저장 중 예외의 전체 롤백을 확인한다.

## 8. Git 작업 규칙

- 현재 기능 개발 기준은 `agent/export-program-link`다. 작업 시작 전에 GitHub 원격 최신 SHA를 확인한다.
- 혼합 작업 사본보다 최신 원격에서 만든 깨끗한 브랜치/작업 디렉터리를 선호한다.
- 관련 파일만 명시적으로 stage하고 한 기능 단위로 커밋한다.
- 사용자는 완료된 작업을 별도 확인 없이 GitHub에 즉시 푸시하기를 원한다.
- 푸시 후 원격 브랜치 SHA와 원격 파일 내용이 검증본과 일치하는지 확인한다.
- `main` 병합은 별도 승인과 회귀 검증 없이 수행하지 않는다.

## 9. 알려진 기술부채와 다음 우선순위

- `application.py`와 여러 `*_business.py`/`*_runtime.py`/`*_fix.py`가 호환 패치와 monkey patch에 의존한다. 동작 테스트를 먼저 확보한 뒤 점진적으로 단일 구현으로 합친다.
- 일부 테이블/컬럼 마이그레이션이 페이지 또는 서비스의 `_ensure_*` 함수에 분산되어 있다. 신규 마이그레이션은 `db_init.py`로 모으되 기존 운영 DB 업그레이드 경로를 유지한다.
- `.bak_*` 파일이 다수 남아 있다. 실제 import 참조와 Git 이력을 확인하기 전 삭제하지 않는다.
- 의존성 선언 파일이 명확하지 않다. 현재 사용 모듈(Streamlit, pandas, openpyxl, Pillow, reportlab 등)을 운영 환경과 대조해 고정된 설치 파일을 마련한다.
- 핵심 화면의 실제 Streamlit 통합 테스트가 부족하다. 출고/수출대기 간 화면 전환과 monkey patch 복원을 우선 자동화한다.
- `docs/ROADMAP.md`와 일부 버전 표기는 현재 코드보다 오래되었다. 기능 완료 여부를 코드/테스트로 재검증한 뒤 갱신한다.

## 10. 새 담당자의 첫날 체크리스트

1. `agent/export-program-link` 최신본을 받고 `git status -sb`로 깨끗한지 확인한다.
2. 운영 DB를 별도 백업하고 테스트에는 복사본을 사용한다.
3. `run_wms.bat` 또는 Streamlit 명령으로 로그인 후 주요 화면을 연다.
4. 일반 출고지시 거래처 검색, 저장/수정/취소를 확인한다.
5. 수출대기 신규 등록, P 이동, 부분 확정, 확정 건 증감 수정, 추가분 재확정을 확인한다.
6. 제품매칭표 재업로드 후 사진 링크와 ERP 코드 선행 0이 보존되는지 확인한다.
7. 전체 테스트와 `git diff --check`를 통과시킨 뒤 작은 커밋으로 푸시한다.

