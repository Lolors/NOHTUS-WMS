# UI Guide

## 기본 톤

- 밝은 배경
- 연한 회색 라인
- 둥근 카드
- 파스텔 블루/그레이
- 과한 hover 효과 금지

## 주요 색상

| 용도 | 색상 |
|---|---|
| 본문 글자 | `#111827` |
| 보조 글자 | `#64748B` |
| 연한 글자 | `#94A3B8` |
| 점선 테두리 | `#D6DEE9` |
| 카드 배경 | `#FFFFFF` |
| 연한 배경 | `#F8FAFC` |
| 경계선 | `#E5E7EB` |

## 제품 이미지 영역

### 제품검색 카드

- 크기: 250×250
- 이미지 없을 때: `photo_placeholder.svg`
- 테두리: `#D6DEE9`

### 로케이션맵 상세

- 표시 크기: 150×150
- 이미지는 250×250 저장본을 축소 표시

## 링크 스타일

파란색 링크/기본 밑줄은 사용하지 않습니다.

추천:

```css
.detail-product-name {
    color:#111827;
    text-decoration:none;
    border-bottom:1px dashed #CBD5E1;
    cursor:pointer;
    font-weight:700;
}
.detail-product-name:hover {
    color:#111827;
    text-decoration:none;
    border-bottom-color:#64748B;
}
```

## 위로가기 버튼

- 흰색 원형
- 연회색 테두리
- 은은한 그림자
- hover 시 색상 변화 없음
