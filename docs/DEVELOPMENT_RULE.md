# Development Rule

## 기본 원칙

1. 한 브랜치에서는 한 가지 문제만 해결합니다.
2. UI, 기능, DB, 리팩토링을 섞지 않습니다.
3. main 브랜치는 항상 실행 가능한 상태로 유지합니다.
4. merge 전 `TEST_CHECKLIST.md`를 확인합니다.

## 브랜치 이름

- `bug/...` 버그 수정
- `feature/...` 기능 추가
- `ui/...` UI/CSS 수정
- `refactor/...` 구조 개선
- `docs/...` 문서 수정

## 작업 순서

1. 이슈 생성
2. 브랜치 생성
3. 수정
4. 로컬 실행
5. 테스트 체크리스트 확인
6. 커밋
7. Pull Request
8. main merge

## 금지 작업

- 여러 기능을 한 번에 수정
- 검증 없이 main에 직접 커밋
- 코어 도면/지도 코드를 UI 브랜치에서 수정
- `app.py` 전체를 덮어쓰기

## Commit 예시

```text
fix: hide inbound map placeholder button without changing map logic
ui: adjust sidebar top spacing
feat: add product image upload placeholder
refactor: split inventory transaction helpers
```
