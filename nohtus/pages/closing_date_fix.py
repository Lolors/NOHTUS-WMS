from __future__ import annotations

import re

import nohtus.pages.closing as closing_page


def _remove_transaction_history_gate(sql):
    """오늘 출고 체크는 출고지시서의 지정 출고일자와 상태를 기준으로 조회한다.

    수정 이력의 생성일·수량·위치까지 현재 품목과 일치시키면 출고일자만 변경한
    지시서나 품목 수정 이력이 있는 지시서가 누락될 수 있으므로, 해당 EXISTS
    조건은 제거한다. 취소 여부와 order_date 조건은 원본 쿼리에 그대로 남는다.
    """
    if not isinstance(sql, str):
        return sql
    if "FROM outbound_orders o" not in sql or "WHERE o.order_date=?" not in sql:
        return sql

    return re.sub(
        r"\n\s+AND EXISTS \(.*?\n\s+\)\n(?=\s+ORDER BY)",
        "\n",
        sql,
        count=1,
        flags=re.DOTALL,
    )


def page_closing():
    """지정하거나 수정한 출고일자를 기준으로 마감의 오늘 출고 체크를 조회한다."""
    original_q = closing_page.q

    def patched_q(sql, params=()):
        return original_q(_remove_transaction_history_gate(sql), params)

    closing_page.q = patched_q
    try:
        return closing_page.page_closing()
    finally:
        closing_page.q = original_q
