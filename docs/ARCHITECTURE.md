# Architecture

## 현재 구조

```text
Browser
  ↓
Streamlit app.py
  ↓
SQLite data/nohtus.db
  ↓
Local files / product_images
```

현재는 대부분의 기능이 `app.py` 하나에 들어 있습니다.

## 목표 구조(RC3 이후)

```text
NOHTUS-WMS/
├── app.py
├── core/
│   ├── constants.py
│   └── db.py
├── services/
│   ├── inventory.py
│   ├── transactions.py
│   ├── matching.py
│   ├── images.py
│   └── outbound.py
├── pages/
│   ├── inbound.py
│   ├── location_map.py
│   ├── product_search.py
│   ├── outbound.py
│   ├── stocktake.py
│   └── history.py
├── ui/
│   ├── css.py
│   ├── components.py
│   └── sidebar.py
└── assets/
```

## 레이어 구분

### UI Layer

- Streamlit 화면 구성
- CSS
- 카드/버튼/표시

### Service Layer

- 재고 입출고
- 출고지시
- 제품매칭
- 이미지 처리

### DB Layer

- SQLite 연결
- SQL 실행
- 스키마 관리

## 리팩토링 원칙

1. 기능 변경 없이 파일만 분리합니다.
2. 파일 분리 후 테스트합니다.
3. 이후 기능 개선을 진행합니다.
4. 코어 도면/지도 코드는 가장 마지막에 분리합니다.
