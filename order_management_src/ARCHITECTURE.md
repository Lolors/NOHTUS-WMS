# 애플리케이션 구조

## 실행 흐름

```text
app.py
  -> ui/application.py
    -> services/bootstrap.py
      -> services/master_data_service.py
      -> services/order_service.py
      -> services/purchase_service.py
      -> ui/pages/router.py
        -> ui/pages/*
```

## 계층별 책임

- `ui`: Streamlit 화면, 탐색, 사용자 입력과 출력
- `services/master_data_service.py`: 거래처·제품·별칭 기초정보
- `services/order_service.py`: 발주 작성·임시저장·발주서
- `services/purchase_service.py`: 입고·거래명세서·월별 매입
- `services/correction_service.py`: 발주서와 연결 명세서의 트랜잭션 통합 수정
- `services/bootstrap.py`: 위 서비스를 조립하고 기존 UI에 연결
- `repositories`: SQLite 데이터 읽기와 쓰기
- `infrastructure`: 데이터베이스 연결과 트랜잭션
- `templates`: 발주서 출력 템플릿
- `app_layers`: 이전 버전과의 호환 계층. 새 기능은 이곳에 추가하지 않는다.
- `core_app.py`: 이전 UI와 출력 기능. 화면별로 분리한 뒤 단계적으로 제거한다.

## 변경 원칙

1. 화면은 SQL이나 CSV 파일을 직접 다루지 않는다.
2. 여러 저장소를 함께 사용하는 동작은 `services`에 둔다.
3. 단일 데이터 종류의 영속화는 `repositories`에 둔다.
4. 새 기능에서 `sys.path`, `sys.modules`, 런타임 함수 교체를 추가하지 않는다.
5. 운영 데이터 이전은 반복 실행해도 안전한 마이그레이션으로 작성한다.
6. 기초정보 서비스는 발주·매입 데이터를 저장하지 않는다.

## 단계적 정리 순서

1. `bootstrap.py`에 남은 UI 호환 코드를 각 `ui` 모듈로 이동
2. `app_layers`의 발주·입고 규칙을 `services`로 이동
3. `core_app.py`의 출력 기능을 `exports` 패키지로 이동
4. 호환 계층 제거 후 명시적인 의존성 전달 방식으로 통일
