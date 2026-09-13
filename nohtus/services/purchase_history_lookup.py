"""제품마스터 표준명이 없어도 과거 매입 이력을 조회하기 위한 순수 조회 헬퍼 (streamlit 미의존).

nohtus.pages.purchase_history(streamlit 의존)의 _clean_text/_erp_names_for_standard는
함수 본문 안에서만 지역 import해 이 모듈 자체는 streamlit을 끌어오지 않는다.
"""

from __future__ import annotations

from nohtus.db import q


def all_purchase_product_options():
    """현재 제품마스터와 과거 매입 DB의 모든 제품명을 합쳐 검색 후보를 만든다."""
    df = q(
        """
        SELECT product_name
        FROM (
            SELECT TRIM(COALESCE(standard_name, '')) AS product_name
            FROM products

            UNION

            SELECT TRIM(
                CASE
                    WHEN TRIM(COALESCE(standard_product_name, '')) <> ''
                    THEN standard_product_name
                    ELSE erp_product_name
                END
            ) AS product_name
            FROM purchase_history
        )
        WHERE product_name <> ''
        ORDER BY product_name
        """
    )
    if df.empty:
        return []
    return [str(value) for value in df["product_name"].dropna().tolist()]


def query_all_purchase_rows(item_no, product_name, start_date, end_date):
    """표준명 매칭 여부와 관계없이 선택한 과거 제품명을 조회한다."""
    from nohtus.pages.purchase_history import _clean_text, _erp_names_for_standard

    erp_names = _erp_names_for_standard(product_name)
    names = []
    for name in [product_name, *erp_names]:
        value = _clean_text(name)
        if value and value not in names:
            names.append(value)

    placeholders = ",".join(["?"] * len(names))
    params = list(names)
    params.extend([start_date, end_date])

    df = q(
        f"""
        SELECT
            business_name,
            purchase_date,
            supplier_name,
            specification,
            quantity,
            unit_price,
            note
        FROM purchase_history
        WHERE (
            standard_product_name IN ({placeholders})
            OR erp_product_name IN ({placeholders})
        )
          AND purchase_date BETWEEN ? AND ?
        ORDER BY purchase_date DESC, business_name, supplier_name
        """,
        tuple(names + params),
    )

    if df.empty:
        return df

    df.insert(0, "표준제품명", product_name)
    df.insert(0, "품목", item_no)
    return df
