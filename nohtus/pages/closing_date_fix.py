from __future__ import annotations

import nohtus.pages.closing as closing_page


def page_closing():
    """출고지시 생성일과 무관하게 지정된 출고일자 기준으로 마감 조회한다."""
    original_q = closing_page.q

    def patched_q(sql, params=()):
        if isinstance(sql, str) and "FROM outbound_orders o" in sql and "substr(t.created_at,1,10)=o.order_date" in sql:
            sql = sql.replace("WHERE substr(t.created_at,1,10)=o.order_date\n                              AND t.tx_type IN ('출고지시','출고지시수정','출고')", "WHERE t.tx_type IN ('출고지시','출고지시수정','출고지시 재차감','출고')")
        return original_q(sql, params)

    closing_page.q = patched_q
    try:
        return closing_page.page_closing()
    finally:
        closing_page.q = original_q
