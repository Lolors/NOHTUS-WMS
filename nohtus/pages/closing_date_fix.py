from __future__ import annotations

import re

import pandas as pd

import nohtus.pages.closing as closing_page
from nohtus.pages.erp_stock_compare_inventory import page_erp_stock_compare as page_erp_stock_compare_live
from nohtus.services.export_waiting import ensure_export_waiting_tables


_VALID_HISTORY_TYPES = (
    "'출고지시'",
    "'출고지시수정'",
    "'출고지시 재차감'",
    "'출고'",
    "'사업장이동'",
    "'사업장+위치이동'",
    "'사업장 이동'",
)


def _replace_transaction_history_gate(sql):
    """지정 출고일자를 유지하면서 관련 이력 유형을 폭넓게 인정한다."""
    if not isinstance(sql, str):
        return sql
    if "FROM outbound_orders o" not in sql or "WHERE o.order_date=?" not in sql:
        return sql

    valid_types = ",".join(_VALID_HISTORY_TYPES)
    replacement = f"""
                        AND EXISTS (
                            SELECT 1
                            FROM transactions t
                            WHERE t.tx_type IN ({valid_types})
                              AND COALESCE(t.memo,'') LIKE '%' || '출고지시서 #' || CAST(o.id AS TEXT) || '%'
                        )
 """
    return re.sub(
        r"\n\s+AND EXISTS \(.*?\n\s+\)\n(?=\s+ORDER BY)",
        replacement,
        sql,
        count=1,
        flags=re.DOTALL,
    )


def _is_today_outbound_query(sql):
    text = str(sql or "")
    return "FROM outbound_orders o" in text and "JOIN outbound_order_items i" in text and "WHERE o.order_date=?" in text


def _export_waiting_rows(original_q, ds):
    ensure_export_waiting_tables()
    return original_q(
        """
        SELECT o.title AS 출고지시서제목,
               -o.id AS 출고지시서ID,
               i.source_inventory_id AS 재고ID,
               i.company AS 사업장,
               i.source_location AS 로케이션,
               i.product_name AS 표준제품명,
               COALESCE(i.lot, '-') AS 제조번호,
               COALESCE(i.exp_date, '-') AS 유통기한,
               i.qty AS 출고수량
        FROM export_waiting_orders o
        JOIN export_waiting_items i ON o.id=i.order_id
        WHERE substr(COALESCE(i.moved_at, o.created_at), 1, 10)=?
          AND o.status IN ('waiting', 'confirmed')
        ORDER BY i.company, i.source_location, i.product_name, i.lot, i.exp_date, o.id, i.id
        """,
        (str(ds),),
    )


def page_closing():
    """출고일자 보정, 수출대기 원위치 체크, inventory 기준 ERP/WMS 비교를 적용한다."""
    original_q = closing_page.q
    original_erp_compare = closing_page.page_erp_stock_compare

    def patched_q(sql, params=()):
        result = original_q(_replace_transaction_history_gate(sql), params)
        if not _is_today_outbound_query(sql):
            return result
        ds = params[0] if params else ""
        export_rows = _export_waiting_rows(original_q, ds)
        if export_rows is None or export_rows.empty:
            return result
        if result is None or result.empty:
            return export_rows
        return pd.concat([result, export_rows], ignore_index=True)

    closing_page.q = patched_q
    closing_page.page_erp_stock_compare = page_erp_stock_compare_live
    try:
        return closing_page.page_closing()
    finally:
        closing_page.q = original_q
        closing_page.page_erp_stock_compare = original_erp_compare
