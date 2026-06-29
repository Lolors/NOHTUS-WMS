# Database Schema

DB 파일: `data/nohtus.db`

## products

제품매칭표 역할.

| 컬럼 | 설명 |
|---|---|
| id | 내부 ID |
| product_code | 노투스팜 ERP 제품코드 |
| standard_name | 표준제품명 |
| warehouse_name | 과거/보조 명칭 |
| aliases | 별칭 |
| erp_nohtuspharm_name | 노투스팜 ERP명 |
| erp_nohtus_name | 노투스 ERP명 |
| erp_noh_name | NOH ERP명 |
| erp_noh_code | NOH ERP 제품코드 |
| bidata_name | 비자료명 |
| substitute_note | 대체/메모 |
| image_path | 제품 이미지 경로 |

## inventory

현재 재고.

| 컬럼 | 설명 |
|---|---|
| id | 내부 ID |
| company | 사업장 |
| product_name | 표준제품명 |
| warehouse_name | 원본/ERP명 |
| lot | LOT/제조번호 |
| exp_date | 유통기한 |
| location | 로케이션 |
| qty | 수량 |
| updated_at | 수정일시 |

## transactions

이력 조회.

| 컬럼 | 설명 |
|---|---|
| id | 내부 ID |
| created_at | 발생일시 |
| tx_type | 입고/이동/출고/조정 등 |
| product_name | 표준제품명 |
| warehouse_name | 원본명 |
| lot | LOT/제조번호 |
| exp_date | 유통기한 |
| from_company | 출발 사업장 |
| from_location | 출발 위치 |
| to_company | 도착 사업장 |
| to_location | 도착 위치 |
| qty | 수량 변화 |
| memo | 메모 |
| final_stock | 거래 직후 표준제품명 전체 총재고 |

## outbound_orders

저장된 출고지시서 헤더.

## outbound_order_items

저장된 출고지시서 품목.

## customers

거래처 관리.

## product_match_conflict_approvals

동일 ERP명 공유 허용 기록.
