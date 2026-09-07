# 개발 진행 메모

## 2026-07-08 시작 기준

### 해결된 판단

- Playwright 실행 테스트에서 `OK` 출력 확인.
- PDF/PNG 미생성 문제는 앱 실행 위치와 확인 위치 혼동 가능성이 컸음.
- 앱 루트 폴더에서 실행해야 `BASE / output / pdf` 기준으로 저장됨.

### 다음 작업 우선순위

1. PDF/PNG 생성 성공 시 저장 경로와 다운로드 버튼을 더 명확하게 표시.
2. 거래처 관리 필드 정리
   - 거래처명
   - 담당자
   - 납품처 주소
   - 연락처
3. 제품 관리 필드 정리
   - 제품코드
   - 정식제품명
   - 규격
   - 단위
4. 별칭 관리 개선
   - 연결제품 검색 가능
   - 일부일치 검색
5. 앱 구조 분리
   - `modules/preview.py`
   - `modules/pdf_export.py`
   - `modules/customer.py`
   - `modules/product.py`
   - `modules/alias.py`
