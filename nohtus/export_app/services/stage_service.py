from __future__ import annotations

from nohtus.export_app import db
from nohtus.export_app.utils.dates import now_text


MANAGED_STAGES = {
    '주문 접수',
    '출고 대기',
    '입고 진행',
    '패킹 대기',
    '패킹 진행',
    '패킹 완료',
}


def sync_case_stage(case_id: int, now: str | None = None) -> str:
    """주문품목별 입고 완료 여부와 미패킹 수량을 기준으로 단계를 계산합니다."""
    case = db.row(
        'SELECT case_type, status, stage FROM export_cases WHERE id=?',
        (case_id,),
    )
    if case is None:
        return ''

    current_stage = str(case['stage'] or '').strip()
    if case['case_type'] == 'historical' or case['status'] == '취소':
        return current_stage
    if current_stage and current_stage not in MANAGED_STAGES:
        return current_stage

    intake = db.row(
        '''SELECT
               COUNT(*) AS order_count,
               SUM(
                   CASE
                       WHEN COALESCE(received.received_qty, 0) + 0.000001 >= COALESCE(o.quantity, 0)
                            AND COALESCE(o.quantity, 0) > 0
                       THEN 1
                       ELSE 0
                   END
               ) AS completed_order_count,
               SUM(
                   CASE
                       WHEN COALESCE(received.received_qty, 0) + 0.000001 < COALESCE(o.quantity, 0)
                       THEN 1
                       ELSE 0
                   END
               ) AS incomplete_order_count
           FROM order_items o
           LEFT JOIN (
               SELECT order_item_id, SUM(COALESCE(requested_qty, 0)) AS received_qty
               FROM shipment_items
               WHERE case_id=?
               GROUP BY order_item_id
           ) received ON received.order_item_id=o.id
           WHERE o.case_id=?''',
        (case_id, case_id),
    )

    order_count = int(intake['order_count'] or 0) if intake else 0
    completed_order_count = int(intake['completed_order_count'] or 0) if intake else 0
    incomplete_order_count = int(intake['incomplete_order_count'] or 0) if intake else 0

    if order_count == 0 or completed_order_count == 0:
        stage = '주문 접수'
    elif incomplete_order_count > 0:
        stage = '패킹 대기'
    else:
        packing = db.row(
            '''SELECT COALESCE(
                       SUM(CASE WHEN s.box_no IS NULL THEN s.requested_qty ELSE 0 END),
                       0
                   ) AS remaining_qty
               FROM shipment_items s
               JOIN order_items o
                 ON o.id=s.order_item_id
                AND o.case_id=s.case_id
               WHERE s.case_id=?''',
            (case_id,),
        )
        remaining_qty = float(packing['remaining_qty'] or 0) if packing else 0.0
        stage = '패킹 완료' if remaining_qty <= 0.000001 else '패킹 대기'

    timestamp = now or now_text()
    db.execute(
        'UPDATE export_cases SET stage=?, updated_at=? WHERE id=?',
        (stage, timestamp, case_id),
    )
    return stage


def sync_active_case_stages() -> None:
    rows = db.rows(
        '''SELECT id FROM export_cases
           WHERE status<>'취소'
             AND case_type<>'historical'
             AND stage IN ('주문 접수','출고 대기','입고 진행','패킹 대기','패킹 진행','패킹 완료')'''
    )
    timestamp = now_text()
    for row in rows:
        sync_case_stage(int(row['id']), timestamp)
