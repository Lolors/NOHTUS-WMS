"""EXPORT 케이스(export_no)에 연결된 WMS 수출대기(export_waiting_orders/items)
조회 헬퍼. nohtus/pages/saved_export_waiting.py의 조회 쿼리와 동일한 로직을
쓰되, 조회 대상을 '이 EXPORT 건의 export_no'로 좁혀서 재사용한다. 실제 확정/
취소는 nohtus.services.export_waiting의 기존 서비스 함수를 그대로 부른다
(다른 화면에 이식하기 위해 그 함수들을 다시 만들지 않는다)."""
from __future__ import annotations

import pandas as pd

from nohtus.dates import display_date_only
from nohtus.db import connect, q as wms_q


def list_orders_for_export_no(export_no: str) -> pd.DataFrame:
    return wms_q(
        """SELECT id, export_no, country, buyer, transport_method, title, status,
                  order_date, created_at, confirmed_at, cancelled_at
           FROM export_waiting_orders
           WHERE TRIM(export_no)=TRIM(?)
           ORDER BY id""",
        (str(export_no or "").strip(),),
    )


def list_active_orders() -> pd.DataFrame:
    """수출확정 매출 등록 화면에서 처리할 진행 중 WMS 연결 건."""
    return wms_q(
        """SELECT id, export_no, country, buyer, transport_method, title, status,
                  order_date, created_at
           FROM export_waiting_orders
           WHERE status IN ('waiting','partial')
           ORDER BY created_at, id"""
    )


def order_items(order_id: int) -> pd.DataFrame:
    df = wms_q(
        """SELECT id,company AS 출고사업장,source_location AS 원래로케이션,
                  product_name AS 표준제품명,COALESCE(warehouse_name,'') AS 출고사업장ERP명,
                  lot AS LOT,exp_date AS 유통기한,qty AS 수량,
                  COALESCE(confirmed,0) AS confirmed,confirmed_company AS 확정사업장,
                  confirmed_customer_name AS 확정매출처,confirmed_at AS 확정일시
           FROM export_waiting_items WHERE order_id=?
           ORDER BY COALESCE(confirmed,0),company,product_name,lot,exp_date,source_location""",
        (int(order_id),),
    )
    if not df.empty:
        df["유통기한"] = df["유통기한"].apply(display_date_only)
        for col in ["출고사업장ERP명", "확정사업장", "확정매출처", "확정일시"]:
            df[col] = df[col].fillna("").astype(str).replace("", "-")
    return df


def customer_options(company: str, term: str) -> pd.DataFrame:
    with connect() as con:
        columns = {r[1] for r in con.execute("PRAGMA table_info(customers)").fetchall()}
    if "customer_name" not in columns:
        return pd.DataFrame(columns=["customer_code", "customer_name", "company"])
    code_col = next((c for c in ["customer_code", "erp_code", "code"] if c in columns), None)
    company_col = "company" if "company" in columns else None
    select_code = f"COALESCE({code_col},'')" if code_col else "''"
    select_company = company_col if company_col else "''"
    clauses, params = ["TRIM(COALESCE(customer_name,''))<>''"], []
    if company_col and company:
        clauses.append("company=?")
        params.append(company)
    if str(term or "").strip():
        clauses.append("customer_name LIKE ?")
        params.append(f"%{str(term).strip()}%")
    return wms_q(
        f"SELECT {select_code} AS customer_code, customer_name, {select_company} AS company "
        f"FROM customers WHERE {' AND '.join(clauses)} ORDER BY customer_name LIMIT 100",
        tuple(params),
    )
