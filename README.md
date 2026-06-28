# NOHTUS WMS

NOHTUS WMS는 노투스팜 물류팀의 입고, 출고, 위치이동, 재고실사, 제품매칭, 로케이션맵 관리를 위한 Streamlit 기반 사내 WMS입니다.

## 현재 기준

- 안정 기준: `v4.9 RC2.82 Stable`
- 개발 방식: GitHub 브랜치 기반
- 첫 번째 버그 브랜치: `bug/inbound-map-placeholder`
- 핵심 원칙: 입고도면/로케이션맵/제품명 클릭 코어는 분리 전까지 함부로 수정하지 않습니다.

## 빠른 실행

```bat
python -m streamlit run app.py
```

또는 Windows에서:

```bat
scripts\run_wms.bat
```

## 권장 브랜치 전략

- `main`: 항상 실행 가능한 안정판
- `bug/*`: 버그 수정만
- `feature/*`: 기능 추가만
- `ui/*`: CSS/레이아웃/디자인만
- `refactor/*`: 구조 변경만
- `docs/*`: 문서만

## 작업 전 반드시 확인

1. `docs/CORE_FREEZE.md`
2. `docs/TEST_CHECKLIST.md`
3. `docs/BUG_HISTORY.md`
4. 현재 작업 브랜치 목적

## 주요 메뉴

- 로케이션맵
- 입고 등록
- 출고지시
- 저장된 출고지시
- 재고 실사
- 제품 매칭 관리
- 이력 조회
- 마감/업무일지

## 개발 주의

`__입고도면적용` 문제는 별도 버그 브랜치에서 단독 해결합니다. 이 문제를 고치면서 사진, 출고, UI, DB 로직을 같이 수정하지 않습니다.
