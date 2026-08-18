"""EXPORT 화면에서 WMS의 실재고를 직접 골라 연결하기 위한 조회 헬퍼.

nohtus/pages/move.py의 캐스케이딩 selectbox 패턴(제품 검색 → 유통기한 →
LOT → 실재고 행)을 그대로 따르되, UI 없이 조회 함수만 분리했다.
outbound.py/export_waiting.py의 monkey-patch 피커는 문자열 리터럴과
내부 호출 순서에 강하게 얽혀 있어 재사용하지 않는다(NOHTUS-WMS 개발
인수인계 문서 기준으로도 다른 화면에 임의 이식하지 않는 게 원칙).
"""
from __future__ import annotations

import pandas as pd

from nohtus.db import q as wms_q
from nohtus.services.products import product_options


def search_products(term: str = "") -> pd.DataFrame:
    return product_options(term, exclude_materials=True)


def expiry_options(product_name: str) -> list[str]:
    df = wms_q(
        "SELECT DISTINCT exp_date FROM inventory WHERE product_name=? AND qty>0 ORDER BY exp_date",
        (product_name,),
    )
    return df["exp_date"].tolist()


def lot_options(product_name: str, exp_date: str) -> list[str]:
    df = wms_q(
        "SELECT DISTINCT lot FROM inventory WHERE product_name=? AND exp_date=? AND qty>0 ORDER BY lot",
        (product_name, exp_date),
    )
    return df["lot"].tolist()


def resolve_stock_rows(product_name: str, lot: str, exp_date: str) -> pd.DataFrame:
    """company/location별로 갈린 실재고 행. 보통 1행이지만 여러 사업장/로케이션에
    나뉘어 있을 수 있어 여러 행일 수 있다."""
    return wms_q(
        """SELECT id, company, location, qty, warehouse_name
           FROM inventory
           WHERE product_name=? AND lot=? AND exp_date=? AND qty>0
           ORDER BY company, location""",
        (product_name, lot, exp_date),
    )


def product_stock_rows(product_name: str) -> pd.DataFrame:
    """선택한 제품의 일반 재고와 P의 미예약 잔량을 반환한다."""
    return wms_q(
        """SELECT inventory.id,inventory.company,inventory.location,inventory.product_name,
                  inventory.lot,inventory.exp_date,
                  CASE WHEN UPPER(TRIM(inventory.location))='P'
                       THEN COALESCE(inventory.qty,0)-COALESCE((
                           SELECT SUM(COALESCE(i.qty,0)) FROM export_waiting_items i
                           JOIN export_waiting_orders o ON o.id=i.order_id
                           WHERE i.waiting_inventory_id=inventory.id AND COALESCE(i.confirmed,0)=0
                             AND o.status IN ('waiting','partial','confirmed')
                       ),0) ELSE COALESCE(inventory.qty,0) END AS qty,
                  inventory.warehouse_name
           FROM inventory
           WHERE inventory.product_name=? AND COALESCE(inventory.qty,0)>0
             AND NOT EXISTS (
                 SELECT 1
                 FROM products
                 WHERE TRIM(COALESCE(standard_name, '')) = TRIM(COALESCE(inventory.product_name, ''))
                   AND LOWER(TRIM(CAST(COALESCE(is_material, 0) AS TEXT)))
                       IN ('1', 'true', 'yes', 'y', 'o', 'v', '체크', '부자재')
             )
             AND (UPPER(TRIM(inventory.location))<>'P' OR COALESCE(inventory.qty,0)>
                  COALESCE((SELECT SUM(COALESCE(i.qty,0)) FROM export_waiting_items i
                            JOIN export_waiting_orders o ON o.id=i.order_id
                            WHERE i.waiting_inventory_id=inventory.id AND COALESCE(i.confirmed,0)=0
                              AND o.status IN ('waiting','partial','confirmed')),0))
           ORDER BY inventory.company,inventory.exp_date,inventory.lot,inventory.location""",
        (product_name,),
    )


def reserved_product_stock_rows(product_name: str, export_no: str) -> pd.DataFrame:
    """현재 수출건에 이미 예약된 P 재고를 EXPORT 저장행 재연결 후보로 반환한다.

    다른 수출건의 P 재고는 절대 포함하지 않고, 수출대기 연결행과
    실제 P 재고 ID가 모두 유효한 행만 노출한다.
    """
    export_no = str(export_no or "").strip()
    if not export_no:
        return pd.DataFrame(columns=[
            "id", "company", "location", "product_name", "lot", "exp_date", "qty", "warehouse_name",
        ])
    return wms_q(
        """SELECT i.source_inventory_id AS id,
                  i.company,
                  i.source_location AS location,
                  i.product_name,
                  i.lot,
                  i.exp_date,
                  MIN(COALESCE(i.qty,0), COALESCE(p.qty,0)) AS qty,
                  i.warehouse_name
           FROM export_waiting_items i
           JOIN export_waiting_orders o ON o.id=i.order_id
           JOIN inventory p ON p.id=i.waiting_inventory_id AND UPPER(TRIM(p.location))='P'
           WHERE TRIM(o.export_no)=TRIM(?)
             AND o.status IN ('waiting','partial')
             AND COALESCE(i.confirmed,0)=0
             AND i.product_name=?
             AND COALESCE(i.qty,0)>0
             AND COALESCE(p.qty,0)>0
           ORDER BY i.company, i.exp_date, i.lot, i.source_location""",
        (export_no, product_name),
    )
