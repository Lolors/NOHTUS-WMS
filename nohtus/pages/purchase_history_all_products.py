from __future__ import annotations

import nohtus.pages.purchase_history as purchase_page
from nohtus.db import q


def _standard_name_with_fallback(erp_product_name, match_map):
    """매칭표에 없는 과거 제품도 원본 제품명을 검색/표시용 이름으로 보존한다."""
    name = purchase_page._clean_text(erp_product_name)
    matched = match_map.get(name, match_map.get(name.replace(" ", ""), ""))
    return matched or name


def _all_purchase_product_options():
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


def _query_all_purchase_rows(item_no, product_name, start_date, end_date):
    """표준명 매칭 여부와 관계없이 선택한 과거 제품명을 조회한다."""
    erp_names = purchase_page._erp_names_for_standard(product_name)
    names = []
    for name in [product_name, *erp_names]:
        value = purchase_page._clean_text(name)
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


def page_purchase_history():
    original_standard_name_for = purchase_page._standard_name_for
    original_product_options = purchase_page._product_options
    original_query_purchase_rows = purchase_page._query_purchase_rows

    purchase_page._standard_name_for = _standard_name_with_fallback
    purchase_page._product_options = _all_purchase_product_options
    purchase_page._query_purchase_rows = _query_all_purchase_rows
    try:
        return purchase_page.page_purchase_history()
    finally:
        purchase_page._standard_name_for = original_standard_name_for
        purchase_page._product_options = original_product_options
        purchase_page._query_purchase_rows = original_query_purchase_rows
