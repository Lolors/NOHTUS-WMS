from __future__ import annotations

from nohtus.export_app import db
from nohtus.export_app.services import stage_service
from nohtus.export_app.utils.dates import now_text


def _reconcile_wms_waiting_orders(source_export_no: str, target_export_no: str) -> str | None:
    """EXPORT 건 병합은 export.db(주문/입고/CTN)만 옮기고 WMS(nohtus.db)의
    수출대기 건(export_waiting_orders)은 건드리지 않는다. 그래서 원본
    수출번호로 WMS 쪽에 별도의 수출대기 건이 남아 있으면, 그 재고 예약이
    새 수출번호(대상)와 연결되지 않은 채 고아로 남아 '수출확정 목록에서
    누락된 품목' 사고로 이어진다. 여기서 같은 수출번호의 WMS 건을 찾아
    함께 합치거나 수출번호를 맞춰준다. 실패해도 EXPORT 쪽 병합 자체는
    막지 않는다 — 호출부가 예외를 무시해도 안전하도록 설계한다."""
    source_export_no = str(source_export_no or "").strip()
    target_export_no = str(target_export_no or "").strip()
    if not source_export_no or not target_export_no or source_export_no == target_export_no:
        return None

    from nohtus.db import connect as wms_connect, q as wms_q
    from nohtus.services.export_waiting import merge_export_waiting_orders

    source_orders = wms_q(
        "SELECT id FROM export_waiting_orders WHERE TRIM(export_no)=TRIM(?) AND status='waiting'",
        (source_export_no,),
    )
    if len(source_orders.index) != 1:
        return None
    source_order_id = int(source_orders.iloc[0]["id"])

    target_orders = wms_q(
        "SELECT id FROM export_waiting_orders WHERE TRIM(export_no)=TRIM(?) AND status='waiting'",
        (target_export_no,),
    )
    if len(target_orders.index) == 1:
        target_order_id = int(target_orders.iloc[0]["id"])
        merge_export_waiting_orders(source_order_id, target_order_id)
        return f"WMS 수출대기 건도 함께 병합했습니다 ({source_export_no} → {target_export_no})."
    if target_orders.empty:
        with wms_connect() as con:
            con.execute(
                "UPDATE export_waiting_orders SET export_no=? WHERE id=?",
                (target_export_no, source_order_id),
            )
            con.commit()
        return f"WMS 수출대기 건의 수출번호를 {target_export_no}(으)로 맞췄습니다."
    return None


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

    wms_reconcile_note = None
    try:
        wms_reconcile_note = _reconcile_wms_waiting_orders(
            str(source['export_no']), str(target['export_no'])
        )
    except Exception:
        # WMS 쪽 정리는 부가 기능이다 — 실패해도 이미 완료된 EXPORT 병합은
        # 그대로 유지하고, 사용자는 필요하면 수출대기 저장 화면에서 직접
        # 두 건을 병합할 수 있다.
        wms_reconcile_note = None

    return {
        'source_export_no': str(source['export_no']),
        'target_export_no': str(target['export_no']),
        'order_count': order_count,
        'shipment_count': shipment_count,
        'box_count': box_count,
        'box_offset': box_offset,
        'wms_reconcile_note': wms_reconcile_note,
    }
