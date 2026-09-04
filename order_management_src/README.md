# 메디풀 발주관리 1.4.0

Streamlit 기반 발주관리 앱입니다.

현재 코드 구조와 계층별 책임은 [ARCHITECTURE.md](ARCHITECTURE.md)를 참고하세요.

## 현재 기준

- 회사명: 주식회사 노투스팜
- 대표: 노진국
- 발주서 미리보기: HTML 기반
- 발주 품목 필드: 제품코드 / 제품명 / 규격 / 단위 / 수량
- 단가 / 금액 / 총금액 기능 제거
- 거래처관리 / 제품관리 / 별칭관리 개발 중

## 주요 기능

- 발주서 작성
- 거래처 CSV 관리
- 제품 CSV 관리
- 별칭 CSV 관리
- 발주서 HTML 미리보기
- Excel 다운로드
- PDF / PNG 캡쳐 기반 다운로드
- 발주서와 연결 거래명세서를 한 번에 바로잡는 통합 수정

## 설치

```bat
install_once.bat
```

수동 설치가 필요하면 아래 명령을 실행합니다.

```bat
python -m pip install -r requirements.txt
python -m playwright install chromium
```

## 실행

```bat
run_app.bat
```

또는

```bat
python -m streamlit run app.py
```

## PDF / PNG 다운로드 메모

PDF / PNG는 Playwright로 미리보기 HTML을 캡쳐해서 생성합니다.
앱을 실행하는 Python 환경과 Playwright를 설치한 Python 환경이 같아야 합니다.

확인 명령:

```bat
python -c "from playwright.sync_api import sync_playwright; p=sync_playwright().start(); b=p.chromium.launch(headless=True); print('OK'); b.close(); p.stop()"
```

## 개발 원칙

1. `main`은 항상 실행 가능한 상태로 유지합니다.
2. 기능 수정은 브랜치에서 진행합니다.
3. 큰 구조 변경 전에는 원인 분석과 현재 동작 확인을 먼저 합니다.
4. 실제 개인정보, 거래처 민감정보, 비밀번호, API 키는 커밋하지 않습니다.

## 추천 브랜치

- `feature/pdf-png-download`
- `feature/customer-management`
- `feature/product-management`
- `feature/alias-search`
