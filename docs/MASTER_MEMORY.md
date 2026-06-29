# MASTER_MEMORY.md

# NOHTUS WMS Master Memory

> 이 문서는 NOHTUS WMS 프로젝트의 핵심 설계 문서이다.
>
> 새로운 개발을 시작하거나 AI가 프로젝트를 이어받을 때 반드시 가장 먼저 읽어야 하는 문서이다.

---

# 프로젝트 정보

프로젝트명

* NOHTUS WMS

목적

* 회사 내부 물류창고(WMS) 운영
* ERP를 보조하는 독립적인 창고관리 시스템
* 입고 / 출고 / 이동 / 재고관리 / 실사 / 제품매칭 / 이력관리

사용 기술

* Python
* Streamlit
* SQLite

향후 계획

* React
* FastAPI
* SQLite 유지
* 모바일 지원
* PDA 지원
* QR/Barcode 지원

---

# 개발 원칙

가장 중요한 원칙

기존 기능을 수정하지 않는다.

새로운 기능은 기존 기능을 유지한 상태에서 추가한다.

기존 UI를 변경하더라도 기능은 절대 깨지면 안 된다.

모든 수정은 실행 테스트 후 적용한다.

---

# 핵심(Core) 기능

아래 기능은 프로젝트의 핵심이다.

수정 시 매우 신중해야 한다.

### 입고 등록

* 도면 클릭
* JS Bridge
* 위치 자동 선택
* ERP명 검색
* 최초 제품 등록

핵심 함수

* render_inbound_quick_location_map()
* location_picker()
* _apply_inbound_location_pending()
* _inbound_js_loc_changed()

---

### 출고

* 사업장 재고 표시
* 로케이션 선택
* 출고 저장

---

### 이동 등록

* 제품 선택
* LOT 선택
* 출발 재고
* 도착 위치
* 이동 저장

---

### 재고 조회

* 제품 검색
* ERP명 검색
* 사업장별 조회
* 위치 상세

---

### 재고 실사

* 재고조정
* 기준재고 업로드
* 실사용 엑셀 다운로드

---

# UI 원칙

사이드바

* 폭 : 14vw
* 최소 : 240px
* 남색 테마 유지
* 메뉴 좌측 정렬

메뉴

* 깔끔한 업무용 UI
* 과도한 장식 사용 금지

버튼

* 가능한 동일한 높이 유지

---

# 로케이션 규칙

구역

A

B

C

D

E

F

G1

G2

REC

Q

P

X

비자료

각 위치는

블록

라인

번호

로 구성된다.

예

A1-03

A2-06

REC

---

# 사업장

* 노투스팜
* 노투스
* NOH
* 비자료

사업장 이동 가능

제품 이동 가능

비자료 전환 가능

---

# DB

주요 테이블

inventory

transactions

products

product_mapping

customers

stock_baseline

기본 원칙

inventory는 현재 재고

transactions는 모든 이력

삭제보다 이력 보존을 우선

---

# Git 운영

main

안정 버전

feature/*

새 기능 개발

fix/*

버그 수정

main은 항상 실행 가능한 상태를 유지한다.

---

# 문서 구조

최소 문서만 유지한다.

README.md

MASTER_MEMORY.md

PRODUCT_SPEC.md

DB_SCHEMA.md

CHANGELOG.md

ROADMAP.md

그 외 문서는 가능하면 위 문서에 통합한다.

---

# 향후 개발 계획

v5

React

FastAPI

권한관리

사진관리

모바일

QR

Barcode

대시보드

통계

실시간 재고

---

# 절대 잊으면 안 되는 사항

ERP는 보조 시스템이다.

실제 운영은 WMS 중심으로 이루어진다.

사용자는 물류 담당자이다.

UI는 단순하고 빠르게 사용 가능해야 한다.

기능 추가보다 안정성을 우선한다.

새로운 기능 때문에 기존 기능이 깨지는 것은 허용하지 않는다.

항상 "현장에서 실제 사용하는 사람"의 입장에서 개발한다.

---

# AI 작업 규칙

AI는 기존 기능을 먼저 이해한 후 수정한다.

레이아웃 수정 시 기능을 변경하지 않는다.

코드를 전달하기 전 반드시 실행 가능한 상태인지 확인한다.

사용자가 요청하면 수정된 완성 파일(app.py, styles.py 등)을 제공한다.

부분 코드만 전달하는 방식은 지양한다.

이 문서는 프로젝트의 기준 문서이며, 새로운 개발을 시작하기 전에 항상 최신 상태로 유지한다.
