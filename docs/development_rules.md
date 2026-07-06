# NOHTUS WMS 개발 규칙

이 문서는 NOHTUS WMS의 구조가 다시 app.py 중심으로 무너지지 않도록 지키는 기준이다.

## 1. 기본 구조

```text
app.py
    Streamlit 실행 진입점만 담당

nohtus/application.py
    앱 초기화, 사이드바 라우팅, 페이지 호출만 담당

nohtus/pages/
    화면 렌더링만 담당

nohtus/services/
    DB 조회/저장, 비즈니스 로직, 엑셀/PDF 생성 담당

nohtus/ui/
    Streamlit 공통 UI 컴포넌트 담당

nohtus/config.py
    앱 제목, 버전, 경로, 사업장, 로케이션 설정 담당

nohtus/db.py
    DB 연결, 공통 SQL 실행 함수 담당

nohtus/db_init.py
    DB 테이블 생성과 마이그레이션 담당
```

## 2. app.py 규칙

`app.py`에는 아래 코드 수준만 허용한다.

```python
from nohtus.application import main

if __name__ == "__main__":
    main()
```

금지:

- 함수 추가 금지
- Streamlit 화면 코드 추가 금지
- DB 코드 추가 금지
- 설정값 직접 선언 금지

## 3. application.py 규칙

`application.py`는 라우터다.

허용:

- `st.set_page_config()`
- `init_db()`
- `apply_style()`
- `render_sidebar()`
- 메뉴별 page 함수 호출

금지:

- 페이지 내부 UI 구현
- SQL 직접 실행
- 엑셀/PDF 생성
- 제품/재고 처리 로직

## 4. pages 규칙

`pages/`는 화면만 담당한다.

허용:

- `st.title`, `st.button`, `st.dataframe` 등 화면 렌더링
- 입력값 수집
- service 함수 호출
- 화면 상태용 `st.session_state` 처리

금지:

- 복잡한 SQL 직접 작성
- `sqlite3` 직접 import
- DB 테이블 생성/수정
- 엑셀/PDF 생성 로직 직접 작성
- 재고 수량 변경 로직 직접 작성

예외:

- 아직 리팩토링 중인 레거시 페이지는 임시 허용하되, 새 기능에는 적용하지 않는다.

## 5. services 규칙

`services/`는 비즈니스 로직과 데이터 처리를 담당한다.

허용:

- DB 조회/저장
- 재고 입고/출고/이동/조정
- 제품 매칭
- 엑셀/PDF 생성
- 데이터 정규화

금지:

- 화면 레이아웃 구현
- `st.title`, `st.button` 중심의 페이지 렌더링
- 사이드바 메뉴 처리

예외:

- 기존에 Streamlit 화면이 섞여 있는 서비스는 점진적으로 분리한다.

## 6. ui 규칙

`ui/`는 여러 페이지에서 재사용하는 Streamlit 컴포넌트를 둔다.

예:

- 로케이션 선택기
- 공통 카드
- 공통 테이블 스타일
- 공통 안내 박스

## 7. config 규칙

공통 상수는 `config.py`에 둔다.

예:

- `APP_TITLE`
- `VERSION`
- `PROJECT_ROOT`
- `DB_PATH`
- `COMPANIES`
- `AREA_CONFIG`
- `AREA_COLOR`

금지:

- 같은 상수를 `application.py`, `pages`, `services`에 중복 선언하지 않는다.

## 8. DB 규칙

DB 연결은 `nohtus.db.connect()`를 사용한다.

테이블 생성/마이그레이션은 `db_init.py`에서만 한다.

금지:

- 페이지 파일에서 `sqlite3` 직접 import
- 페이지 파일에서 `ALTER TABLE` 직접 실행
- 로컬 DB 파일을 Git에 커밋

## 9. 파일명 규칙

새 파일에는 `runtime`, `temp`, `new`, `final`, `fix` 같은 임시 이름을 쓰지 않는다.

좋은 예:

```text
services/outbound.py
services/baseline.py
services/product.py
pages/closing.py
pages/product_matching.py
```

나쁜 예:

```text
outbound_runtime.py
product_runtime.py
closing_final.py
app_new.py
```

이미 존재하는 호환 wrapper는 한 버전 정도 유지한 뒤, 참조가 완전히 사라지면 삭제한다.

## 10. 브랜치 규칙

- `main`: 안정 배포 기준
- `refactor/project-structure`: 구조 개선 작업 기준
- `quality/*`: 코드 품질 정리
- `feature/*`: 기능 추가
- `fix/*`: 버그 수정

## 11. 작업 전 체크

기능 수정 전 확인:

1. 어떤 page에서 호출되는가?
2. service로 뺄 수 있는가?
3. config에 이미 있는 상수를 중복 선언하지 않았는가?
4. DB 변경이 있으면 `db_init.py`에 반영했는가?
5. app.py 또는 application.py가 비대해지지 않는가?

## 12. 작업 후 체크

수정 후 최소 확인 메뉴:

- 로케이션 맵
- 입고 등록
- 출고지시
- 저장된 출고지시
- 마감
- 제품 매칭 관리
- 거래처 관리
- 이력 조회

## 13. 핵심 원칙

기능이 늘어나도 구조는 단순해야 한다.

화면은 pages, 로직은 services, 공통 UI는 ui, 설정은 config, 실행은 application에 둔다.
