from __future__ import annotations

import streamlit as st

from nohtus.export_app import db
from nohtus.export_app.utils.dates import now_text


PACKING_STAGE_NAMES = {
    '주문 접수',
    '출고 대기',
    '입고 진행',
    '패킹 대기',
    '패킹 진행',
    '패킹 완료',
}


def _reopen_delivered_case(case_id: int, now: str) -> None:
    case = db.row(
        'SELECT stage, status, case_type FROM export_cases WHERE id=?',
        (case_id,),
    )
    if (
        case
        and case['case_type'] != 'historical'
        and str(case['stage'] or '').strip() == '국내배송'
    ):
        db.execute(
            "UPDATE export_cases SET stage='패킹 대기',status='진행중',updated_at=? WHERE id=?",
            (now, case_id),
        )


def sync_case_stage(case_id: int, now: str | None = None) -> str:
    """Recalculate the intake/packing stage from every order item's progress."""
    case = db.row(
        'SELECT case_type, status, stage FROM export_cases WHERE id=?',
        (case_id,),
    )
    if case is None:
        return ''

    current_stage = str(case['stage'] or '')
    if case['case_type'] == 'historical' or case['status'] == '취소':
        return current_stage
    if current_stage and current_stage not in PACKING_STAGE_NAMES:
        return current_stage

    intake = db.row(
        '''SELECT
               COUNT(*) AS order_count,
               COALESCE(SUM(COALESCE(received.received_qty, 0)), 0) AS total_received_qty,
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
    total_received_qty = float(intake['total_received_qty'] or 0) if intake else 0.0
    incomplete_order_count = int(intake['incomplete_order_count'] or 0) if intake else 0

    if order_count == 0 or total_received_qty <= 0:
        stage = '출고 대기'
    elif incomplete_order_count > 0:
        stage = '입고 진행'
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
        stage = '패킹 완료' if remaining_qty <= 0 else '패킹 대기'

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


def list_for_case(case_id: int):
    return db.rows(
        '''SELECT id, case_id, order_item_id, business_unit, product_name,
                  lot_no, expiry_date, requested_qty, box_no, created_at, updated_at
           FROM shipment_items WHERE case_id=? ORDER BY id''',
        (case_id,),
    )


@db.backup_batch
def cleanup_invalid_links(case_id: int) -> int:
    invalid_rows = db.rows(
        '''SELECT s.id
           FROM shipment_items s
           LEFT JOIN order_items o
             ON o.id=s.order_item_id
            AND o.case_id=s.case_id
           WHERE s.case_id=?
             AND s.order_item_id IS NOT NULL
             AND o.id IS NULL''',
        (case_id,),
    )
    if not invalid_rows:
        return 0
    ids = [int(row['id']) for row in invalid_rows]
    db.executemany('DELETE FROM shipment_items WHERE id=?', [(shipment_id,) for shipment_id in ids])
    db.execute(
        '''DELETE FROM boxes
           WHERE case_id=?
             AND NOT EXISTS(
                 SELECT 1 FROM shipment_items s
                 WHERE s.case_id=boxes.case_id AND s.box_no=boxes.box_no
             )''',
        (case_id,),
    )
    sync_case_stage(case_id)
    return len(ids)


@st.cache_data(show_spinner=False, persist='disk', max_entries=256)
def _cached_case_items(
    case_id: int,
    cache_token: tuple[int, int, int, int],
) -> list[dict]:
    rows = db.rows(
        '''SELECT s.id, s.case_id, s.order_item_id,
                  COALESCE(
                      NULLIF(TRIM(s.business_unit), ''),
                      NULLIF(TRIM(s.location), ''),
                      ''
                  ) AS business_unit,
                  s.location AS source_location, s.source_inventory_id,
                  s.product_name, s.lot_no, s.expiry_date,
                  s.requested_qty, s.box_no, o.unit
           FROM shipment_items s
           JOIN order_items o
             ON o.id=s.order_item_id
            AND o.case_id=s.case_id
           WHERE s.case_id=?
           ORDER BY o.id,
                    CASE WHEN s.box_no IS NULL THEN 0 ELSE 1 END,
                    s.box_no,
                    s.id''',
        (case_id,),
    )
    return [dict(row) for row in rows]


def list_case_items(case_id: int):
    """Canonical read-only shipment rows used by intake, packing, and documents."""
    return _cached_case_items(int(case_id), db.read_cache_token())


def list_actual(case_id: int):
    return list_case_items(case_id)


def get_lot_expiry_dataframe(case_id: int):
    import pandas as pd

    rows = list_case_items(case_id)
    return pd.DataFrame([
        {
            '_id': row['id'],
            '제품명': row['product_name'],
            '출고수량': row['requested_qty'],
            'CTN번호': row['box_no'],
            '제조번호': row['lot_no'],
            '유통기한': row['expiry_date'],
        }
        for row in rows
    ])


@db.backup_batch
def update_lot_expiry(case_id: int, edited) -> int:
    now = now_text()
    updated = 0
    valid_ids = {int(row['id']) for row in list_case_items(case_id)}
    for _, row in edited.iterrows():
        raw_id = row.get('_id')
        if raw_id in (None, '', 0):
            continue
        shipment_id = int(raw_id)
        if shipment_id not in valid_ids:
            continue
        db.execute(
            '''UPDATE shipment_items
               SET lot_no=?, expiry_date=?, updated_at=?
               WHERE id=? AND case_id=?''',
            (
                str(row.get('제조번호', '') or '').strip(),
                str(row.get('유통기한', '') or '').strip(),
                now,
                shipment_id,
                case_id,
            ),
        )
        updated += 1
    if updated:
        db.execute('UPDATE export_cases SET updated_at=? WHERE id=?', (now, case_id))
    return updated


def list_linked(case_id: int, order_item_id: int):
    return [
        row
        for row in list_case_items(case_id)
        if int(row['order_item_id']) == int(order_item_id)
    ]


def packing_impact_for_order(case_id: int, order_item_id: int) -> dict[str, int]:
    result = db.row(
        '''SELECT
               SUM(CASE WHEN box_no IS NOT NULL THEN 1 ELSE 0 END) AS packed_row_count,
               COUNT(DISTINCT box_no) AS affected_box_count
           FROM shipment_items
           WHERE case_id=? AND order_item_id=?''',
        (case_id, order_item_id),
    )
    return {
        'packed_row_count': int(result['packed_row_count'] or 0) if result else 0,
        'affected_box_count': int(result['affected_box_count'] or 0) if result else 0,
    }


def count_unlinked(case_id: int) -> int:
    result = db.row(
        'SELECT COUNT(*) AS count FROM shipment_items WHERE case_id=? AND order_item_id IS NULL',
        (case_id,),
    )
    return int(result['count'] or 0) if result else 0


def list_unlinked(case_id: int):
    return db.rows(
        '''SELECT id, business_unit, product_name, lot_no, expiry_date,
                  requested_qty, box_no
           FROM shipment_items
           WHERE case_id=? AND order_item_id IS NULL
           ORDER BY id''',
        (case_id,),
    )


@db.backup_batch
def delete_unlinked(case_id: int) -> None:
    db.execute('DELETE FROM shipment_items WHERE case_id=? AND order_item_id IS NULL', (case_id,))
    db.execute(
        '''DELETE FROM boxes
           WHERE case_id=?
             AND NOT EXISTS(
                 SELECT 1 FROM shipment_items s
                 WHERE s.case_id=boxes.case_id AND s.box_no=boxes.box_no
             )''',
        (case_id,),
    )
    sync_case_stage(case_id)


@db.backup_batch
def save_for_order(case_id: int, order_item_id: int, rows: list[dict]) -> float:
    cleanup_invalid_links(case_id)
    order = db.row('SELECT id FROM order_items WHERE id=? AND case_id=?', (order_item_id, case_id))
    if order is None:
        raise ValueError('현재 수출 건의 주문품목을 찾을 수 없습니다.')

    existing_rows = db.rows(
        '''SELECT id, requested_qty, box_no
           FROM shipment_items
           WHERE case_id=? AND order_item_id=?
           ORDER BY id''',
        (case_id, order_item_id),
    )
    existing_by_id = {int(row['id']): row for row in existing_rows}
    retained_ids: set[int] = set()
    new_values = []
    now = now_text()
    total = 0.0
    packing_structure_changed = False

    for item in rows:
        product_name = str(item.get('product_name', '') or '').strip()
        quantity = float(item.get('requested_qty', 0) or 0)
        if not product_name:
            raise ValueError('입력된 행에는 실제 제품명이 필요합니다.')

        raw_id = item.get('_id')
        shipment_id = None
        if raw_id not in (None, '', 0):
            try:
                candidate_id = int(raw_id)
            except (TypeError, ValueError):
                candidate_id = 0
            if candidate_id in existing_by_id:
                shipment_id = candidate_id

        total += quantity
        raw_source_inventory_id = item.get('source_inventory_id')
        source_inventory_id = int(raw_source_inventory_id) if raw_source_inventory_id else None
        fields = (
            str(item.get('business_unit', '') or '').strip(),
            str(item.get('location', '') or '').strip(),
            source_inventory_id,
            product_name,
            str(item.get('lot_no', '') or '').strip(),
            str(item.get('expiry_date', '') or '').strip(),
            quantity,
        )

        if shipment_id is not None:
            retained_ids.add(shipment_id)
            previous = existing_by_id[shipment_id]
            if abs(float(previous['requested_qty'] or 0) - quantity) > 0.000001:
                packing_structure_changed = True
            db.execute(
                '''UPDATE shipment_items
                   SET business_unit=?, location=?, source_inventory_id=?, product_name=?,
                       lot_no=?, expiry_date=?, requested_qty=?, updated_at=?
                   WHERE id=? AND case_id=? AND order_item_id=?''',
                (*fields, now, shipment_id, case_id, order_item_id),
            )
        else:
            packing_structure_changed = True
            new_values.append((
                case_id,
                order_item_id,
                fields[0],
                fields[1],
                fields[2],
                fields[3],
                fields[4],
                fields[5],
                fields[6],
                None,
                now,
                now,
            ))

    deleted_ids = [shipment_id for shipment_id in existing_by_id if shipment_id not in retained_ids]
    if deleted_ids:
        packing_structure_changed = True
        db.executemany(
            'DELETE FROM shipment_items WHERE id=? AND case_id=? AND order_item_id=?',
            [(shipment_id, case_id, order_item_id) for shipment_id in deleted_ids],
        )

    if new_values:
        db.executemany(
            '''INSERT INTO shipment_items(
                   case_id, order_item_id, business_unit, location, source_inventory_id,
                   product_name, lot_no, expiry_date, requested_qty, box_no, created_at, updated_at
               ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
            new_values,
        )

    if packing_structure_changed:
        _reopen_delivered_case(case_id, now)
    db.execute(
        '''DELETE FROM boxes
           WHERE case_id=?
             AND NOT EXISTS(
                 SELECT 1 FROM shipment_items s
                 WHERE s.case_id=boxes.case_id AND s.box_no=boxes.box_no
             )''',
        (case_id,),
    )
    sync_case_stage(case_id, now)
    return total

def total_linked_quantity(case_id: int) -> float:
    return sum(float(row['requested_qty'] or 0) for row in list_case_items(case_id))


@db.backup_batch
def sync_historical(case_id: int) -> None:
    case = db.row('SELECT case_type FROM export_cases WHERE id=?', (case_id,))
    if not case or case['case_type'] != 'historical':
        return
    now = now_text()
    orders = db.rows(
        'SELECT id, product_name, quantity FROM order_items WHERE case_id=? ORDER BY id',
        (case_id,),
    )
    order_ids = {int(order['id']) for order in orders}
    for order in orders:
        shipment = db.row(
            'SELECT id FROM shipment_items WHERE case_id=? AND order_item_id=? ORDER BY id LIMIT 1',
            (case_id, order['id']),
        )
        if shipment:
            db.execute(
                'UPDATE shipment_items SET product_name=?,requested_qty=?,updated_at=? WHERE id=?',
                (order['product_name'], order['quantity'], now, shipment['id']),
            )
            db.execute(
                'DELETE FROM shipment_items WHERE case_id=? AND order_item_id=? AND id<>?',
                (case_id, order['id'], shipment['id']),
            )
        else:
            db.execute(
                '''INSERT INTO shipment_items(
                       case_id,order_item_id,business_unit,location,product_name,
                       lot_no,expiry_date,requested_qty,box_no,created_at,updated_at
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
                (case_id, order['id'], '', '', order['product_name'], '', '',
                 order['quantity'], None, now, now),
            )
    for shipment in db.rows(
        'SELECT id, order_item_id FROM shipment_items WHERE case_id=? AND order_item_id IS NOT NULL',
        (case_id,),
    ):
        if int(shipment['order_item_id']) not in order_ids:
            db.execute('DELETE FROM shipment_items WHERE id=?', (shipment['id'],))