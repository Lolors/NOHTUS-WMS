# Roadmap

체크 상태는 2026-08-10 기준 `agent/export-program-link` 코드/테스트와 대조해 갱신했다.
UI 폭 있는 항목(Phase 2)은 코드만으로 완료 여부를 판단할 수 없어 실제 화면 확인 전까지 보류로 둔다.
세부 배경은 `docs/DEVELOPER_HANDOFF.md`를 함께 참고한다.

## Phase 1: 안정화

- [x] `__입고도면적용` 노출 문제 해결 — `styles.py`의 `apply_inbound_bridge_style()`이 버튼/입력을 완전히 숨김 처리한다.
- [x] 도면 클릭 → 입고 위치 연동 회귀 테스트 강화 — `tests/test_inbound_map_location_bridge.py`가 `_inbound_js_loc_changed`/`_apply_inbound_location_pending`(Core Freeze 함수 자체는 변경하지 않음)을 검증.
- [x] 로케이션맵 제품명 클릭 회귀 테스트 강화 — `tests/test_location_map_product_click_filters.py`(필터/집계 로직), `tests/test_location_map_patch_restore.py`(전역 위젯 patch 복원)로 커버.

## Phase 2: UI 마감

- [ ] 사이드바/본문 여백 최종 정리
- [ ] 제품 카드 디자인 정리
- [ ] 위로가기 버튼 전 페이지 적용
- [ ] placeholder 디자인 통일

## Phase 3: 기능 복원/정리

- [ ] 제품 이미지 250×250 저장 — `product_runtime.py`의 `save_product_image()`는 리사이즈 없이 원본 바이트를 그대로 저장한다.
- [ ] 모바일 촬영/앨범 업로드 — `st.camera_input` 등 카메라 캡처 UI 없음.
- [x] ERP명 검색 → 표준제품명 콤보박스 — `product_matching.py`에 ERP명/별칭 검색 후 선택하는 콤보박스 구현됨.
- [x] 출고지시 수정/취소 안정화 — `services/outbound.py`의 `cancel_outbound_order()` 등으로 구현, 규칙은 `DEVELOPER_HANDOFF.md` 4장 참고.

## Phase 4: 리팩토링

- [ ] DB 함수 분리
- [ ] 재고 서비스 분리
- [ ] 출고 서비스 분리
- [ ] 이미지 서비스 분리
- [ ] UI 컴포넌트 분리
- [ ] 로케이션맵 코어 분리

## Phase 5: 배포

- [ ] 사내 웹 배포
- [ ] 사용자 권한 — 로그인/권한 구분 코드 없음.
- [x] DB 백업 자동화 — `services/database_backup.py`의 `run_due_backups()` / `start_backup_worker()` / Google Drive 백업으로 구현됨.
- [ ] 로그 관리 — `logging` 모듈 구성 없음.
