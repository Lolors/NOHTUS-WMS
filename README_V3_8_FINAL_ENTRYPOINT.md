# NOHTUS WMS Refactor V3.8 - Final Entrypoint

## 목적

V3.7에서 app_runtime.py가 93줄까지 줄어든 뒤, 임시 이름처럼 보이던 `app_runtime.py`를 정식 엔트리포인트인 `nohtus/application.py`로 승격했습니다.

## 변경 파일

- `app.py`
  - 최종 Streamlit 실행 파일입니다.
  - `from nohtus.application import main` 후 `main()`만 실행합니다.

- `app_slim.py`
  - 기존 적용 흐름과 호환되도록 같은 내용을 유지했습니다.
  - 필요하면 프로젝트 루트의 app.py로 덮어써도 됩니다.

- `nohtus/application.py`
  - 기존 `nohtus/app_runtime.py`의 역할을 넘겨받은 정식 앱 엔트리포인트입니다.
  - Streamlit page config, DB 초기화, 스타일 적용, 사이드바 라우팅만 담당합니다.

- `nohtus/app_runtime.py`
  - 호환용 wrapper로 축소했습니다.
  - 혹시 남아 있는 오래된 import가 있어도 바로 깨지지 않게 `application.main`을 다시 내보냅니다.

## 적용 방법

1. zip 압축을 현재 프로젝트 루트에 덮어씁니다.
2. 기존처럼 실행합니다.

```bash
streamlit run app.py
```

## 최종 구조

```text
app.py
  -> nohtus/application.py
      -> navigation.py
      -> pages/
      -> services/
      -> db_init.py
```

## 메모

이 버전부터 `app_runtime.py`는 정식 파일이 아니라 호환용 파일입니다. 다음 큰 버전에서 내부 import가 완전히 정리되면 삭제해도 됩니다.
