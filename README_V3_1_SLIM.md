# NOHTUS WMS Refactor V3.1 app.py 슬림화

## 변경 내용

- 기존 `app.py`의 실행/잔여 로직을 `nohtus/app_runtime.py`로 이동했습니다.
- 새 `app.py`는 `nohtus.app_runtime.main()`만 호출하는 진입점 역할을 합니다.
- `app_runtime.py`가 `nohtus/` 내부로 이동하면서 `Path(__file__).parent` 기준 경로가 바뀌는 문제를 막기 위해 `PROJECT_ROOT = Path(__file__).resolve().parents[1]` 기준으로 보정했습니다.

## 적용 방법

1. 기존 프로젝트에서 현재 `app.py`를 백업합니다.
2. 이 패키지의 `app_slim.py`를 프로젝트 루트의 `app.py`로 교체합니다.
3. `nohtus/app_runtime.py`를 프로젝트의 `nohtus/` 폴더에 추가합니다.
4. 실행 후 문제가 없으면 다음 단계에서 `app_runtime.py` 내부 함수를 services/pages/utils로 추가 분리합니다.

## 이번 단계의 의도

이번 버전은 완전한 최종 분리가 아니라, 기능 동작을 최대한 보존하면서 `app.py`를 먼저 얇게 만드는 안전한 중간 단계입니다.
