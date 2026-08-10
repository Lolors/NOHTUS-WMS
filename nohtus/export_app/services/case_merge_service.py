from __future__ import annotations

from nohtus.export_app import db
from nohtus.export_app.services import stage_service
from nohtus.export_app.utils.dates import now_text


def merge_case_into(source_case_id: int, target_case_id: int) -> dict:
    """Move order, intake, and CTN data into another case and cancel the source case."""
    if source_case_id == target_case_id:
        raise ValueError('원본과 대상 수출 건은 서로 달라야 합니다.')

    now = now_text()
    with db.connect() as connection:
        source = connection.execute(
            'SELECT id, export_no, status, stage, case_type FROM export_cases WHERE id=?',
            (source_case_id,),
        ).fetchone()
        target = connection.execute(
            'SELECT id, export_no, status, stage, case_type FROM export_cases WHERE id=?',
            (target_case_id,),
        ).fetchone()
        if source is None or target is None:
            raise ValueError('원본 또는 대상 수출 건을 찾을 수 없습니다.')
        if source['status'] == '취소' or source['stage'] == '취소':
            raise ValueError('이미 취소된 수출 건은 이관할 수 없습니다.')
        if target['status'] == '취소' or target['stage'] == '취소':
            raise ValueError('취소된 수출 건으로는 이관할 수 없습니다.')
        if source['case_type'] != target['case_type']:
            raise ValueError('현재 수출 건과 과거 수출 건은 서로 병합할 수 없습니다.')

        counts = connection.execute(
            '''SELECT
                   (SELECT COUNT(*) FROM order_items WHERE case_id=?) AS order_count,
                   (SELECT COUNT(*) FROM shipment_items WHERE case_id=?) AS shipment_count,
                   (SELECT COUNT(*) FROM boxes WHERE case_id=?) AS box_count''',
            (source_case_id, source_case_id, source_case_id),
        ).fetchone()
        order_count = int(counts['order_count'] or 0)
        shipment_count = int(counts['shipment_count'] or 0)
        box_count = int(counts['box_count'] or 0)
        if order_count == 0:
            raise ValueError('이관할 주문목록이 없습니다.')

        target_max_box = connection.execute(
            'SELECT COALESCE(MAX(box_no), 0) AS max_box FROM boxes WHERE case_id=?',
            (target_case_id,),
        ).fetchone()
        box_offset = int(target_max_box['max_box'] or 0) if box_count else 0

        connection.execute(
            'UPDATE order_items SET case_id=? WHERE case_id=?',
            (target_case_id, source_case_id),
        )
        connection.execute(
            '''UPDATE shipment_items
               SET case_id=?,
                   box_no=CASE WHEN box_no IS NULL THEN NULL ELSE box_no+? END,
                   updated_at=?
               WHERE case_id=?''',
            (target_case_id, box_offset, now, source_case_id),
        )
        connection.execute(
            '''UPDATE boxes
               SET case_id=?, box_no=box_no+?, updated_at=?
               WHERE case_id=?''',
            (target_case_id, box_offset, now, source_case_id),
        )
        connection.execute(
            'UPDATE purchase_price_history SET case_id=? WHERE case_id=?',
            (target_case_id, source_case_id),
        )
        connection.execute(
            '''UPDATE export_cases
               SET previous_stage=stage, stage='취소', status='취소',
                   cancel_reason=?, cancelled_at=?, updated_at=?
               WHERE id=?''',
            (f"{target['export_no']}로 주문 이관", now, now, source_case_id),
        )
        connection.execute(
            'UPDATE export_cases SET updated_at=? WHERE id=?',
            (now, target_case_id),
        )
        detail = (
            f"{source['export_no']} → {target['export_no']} · "
            f'주문 {order_count}행 · 입고 {shipment_count}행 · CTN {box_count}개'
        )
        connection.execute(
            'INSERT INTO history(case_id, action, detail, created_at) VALUES (?,?,?,?)',
            (source_case_id, '주문 이관 후 취소', detail, now),
        )
        connection.execute(
            'INSERT INTO history(case_id, action, detail, created_at) VALUES (?,?,?,?)',
            (target_case_id, '다른 주문 병합', detail, now),
        )

    stage_service.sync_case_stage(target_case_id, now)
    return {
        'source_export_no': str(source['export_no']),
        'target_export_no': str(target['export_no']),
        'order_count': order_count,
        'shipment_count': shipment_count,
        'box_count': box_count,
        'box_offset': box_offset,
    }
