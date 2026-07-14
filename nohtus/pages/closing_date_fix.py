from __future__ import annotations

import re

import nohtus.pages.closing as closing_page


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
    """지정 출고일자를 유지하면서 관련 이력 유형을 폭넓게 인정한다.

    기존 조건은 거래 이력의 생성일·수량·위치까지 현재 품목과 정확히 같아야 해서
    출고일자 수정 또는 품목 수정 후 누락될 수 있었다. 출고일자는 주문의 order_date를
    기준으로 두고, 이력은 출고지시서 ID와 유효한 이력 유형만 확인한다.
    """
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


def page_closing():
    """지정·수정된 출고일자와 관련 출고/사업장 이동 이력을 기준으로 조회한다."""
    original_q = closing_page.q

    def patched_q(sql, params=()):
        return original_q(_replace_transaction_history_gate(sql), params)

    closing_page.q = patched_q
    try:
        return closing_page.page_closing()
    finally:
        closing_page.q = original_q
