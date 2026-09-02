from __future__ import annotations

from datetime import datetime

from nohtus.db import connect as wms_connect
from nohtus.export_app import db as export_db
from nohtus.export_app.services import export_service, shipment_service
from nohtus.services.export_waiting import STAGING_LOCATIONS, _add


def _same_text(left: object, right: object, default: str = '') -> bool:
    return str(left or default).strip() == str(right or default).strip()


def _selected_rows_from_db(case_id: int, order_item_id: int, ids: set[int]) -> list[dict]:
    if not ids:
        return []
    placeholders = ','.join('?' for _ in ids)
    rows = export_db.rows(
        f'''SELECT id,case_id,order_item_id,
                   COALESCE(NULLIF(TRIM(business_unit),''), NULLIF(TRIM(location),''), '') AS business_unit,
                   location AS source_location, source_inventory_id,
                   product_name, lot_no, expiry_date, requested_qty, box_no
            FROM shipment_items
            WHERE case_id=? AND order_item_id=? AND id IN ({placeholders})
            ORDER BY id''',
        tuple([case_id, order_item_id, *sorted(ids)]),
    )
    return [dict(row) for row in rows]


def _matching_waiting_items(cur, order_id: int, row: dict) -> list[dict]:
    source_id = int(row.get('source_inventory_id') or 0)
    params: list[object] = [int(order_id)]
    source_clause = ''
    if source_id:
        source_clause = ' AND source_inventory_id=?'
        params.append(source_id)

    raw = cur.execute(
        f'''SELECT id,source_inventory_id,waiting_inventory_id,company,product_name,
                  IFNULL(warehouse_name,''),IFNULL(lot,'-'),IFNULL(exp_date,'-'),
                  source_location,qty,COALESCE(confirmed,0),IFNULL(waiting_location,'P')
           FROM export_waiting_items
           WHERE order_id=? AND COALESCE(confirmed,0)=0{source_clause}
           ORDER BY id''',
        tuple(params),
    ).fetchall()
    keys = [
        'id','source_inventory_id','waiting_inventory_id','company','product_name',
        'warehouse_name','lot','exp_date','source_location','qty','confirmed','waiting_location',
    ]
    items = [dict(zip(keys, item)) for item in raw]
    matched = [
        item for item in items
        if _same_text(item.get('company'), row.get('business_unit'))
        and _same_text(item.get('product_name'), row.get('product_name'))
        and _same_text(item.get('lot'), row.get('lot_no'), '-')
        and _same_text(item.get('exp_date'), row.get('expiry_date'), '-')
    ]
    return matched


def _matching_p_row(cur, item: dict):
    staging_location = str(item.get('waiting_location') or '').strip() or 'P'
    waiting_inventory_id = int(item.get('waiting_inventory_id') or 0)
    if waiting_inventory_id:
        row = cur.execute(
            "SELECT id,qty FROM inventory WHERE id=? AND UPPER(TRIM(COALESCE(location,'')))=UPPER(?)",
            (waiting_inventory_id, staging_location),
        ).fetchone()
        if row:
            return row

    rows = cur.execute(
        '''SELECT id,qty FROM inventory
           WHERE UPPER(TRIM(COALESCE(location,'')))=UPPER(?)
             AND company=? AND product_name=?
             AND IFNULL(warehouse_name,'')=?
             AND IFNULL(lot,'-')=? AND IFNULL(exp_date,'-')=?
           ORDER BY id''',
        (
            staging_location,
            str(item.get('company') or ''),
            str(item.get('product_name') or ''),
            str(item.get('warehouse_name') or ''),
            str(item.get('lot') or '-') or '-',
            str(item.get('exp_date') or '-') or '-',
        ),
    ).fetchall()
    return rows[0] if len(rows) == 1 else None


def _set_order_status(cur, order_id: int, now: str) -> None:
    remaining_status = cur.execute(
        '''SELECT
               SUM(CASE WHEN COALESCE(confirmed,0)=0 THEN 1 ELSE 0 END),
               SUM(CASE WHEN COALESCE(confirmed,0)=1 THEN 1 ELSE 0 END)
           FROM export_waiting_items WHERE order_id=?''',
        (int(order_id),),
    ).fetchone()
    waiting_count = int((remaining_status or [0, 0])[0] or 0)
    confirmed_count = int((remaining_status or [0, 0])[1] or 0)
    if waiting_count and confirmed_count:
        status = 'partial'
    elif waiting_count:
        status = 'waiting'
    elif confirmed_count:
        status = 'confirmed'
    else:
        status = 'cancelled'
    cur.execute(
        'UPDATE export_waiting_orders SET status=?,updated_at=? WHERE id=?',
        (status, now, int(order_id)),
    )


def _best_effort_cleanup_wms(*, export_no: str, rows: list[dict], now: str) -> None:
    """선택행에 해당하는 WMS 대기기록만 가능한 범위에서 정리한다.

    원본/P 재고가 이미 깨져 있거나 다른 WMS 데이터에 문제가 있어도 예외를
    밖으로 전파하지 않는다. 사용자가 선택한 EXPORT 저장행 삭제가 우선이다.
    """
    if not export_no or not rows:
        return

    try:
        with wms_connect() as con:
            open_orders = con.execute(
                '''SELECT id FROM export_waiting_orders
                   WHERE TRIM(export_no)=TRIM(?) AND status IN ('waiting','partial')
                   ORDER BY id''',
                (export_no,),
            ).fetchall()
            if len(open_orders) != 1:
                return
            order_id = int(open_orders[0][0])

            for row in rows:
                remaining = max(0, int(float(row.get('requested_qty') or 0)))
                for item in _matching_waiting_items(con.cursor(), order_id, row):
                    if remaining <= 0:
                        break
                    item_qty = max(0, int(item.get('qty') or 0))
                    delete_qty = min(item_qty, remaining)

                    try:
                        p_row = _matching_p_row(con.cursor(), item)
                        if p_row and delete_qty > 0:
                            current_p_qty = int(p_row[1] or 0)
                            restore_qty = min(current_p_qty, delete_qty)
                            if restore_qty > 0:
                                con.execute(
                                    'UPDATE inventory SET qty=?,updated_at=? WHERE id=?',
                                    (current_p_qty - restore_qty, now, int(p_row[0])),
                                )
                                source_location = str(item.get('source_location') or '').strip()
                                if source_location and source_location.upper() not in STAGING_LOCATIONS:
                                    _add(con.cursor(), item, source_location, restore_qty, now, 1)
                    except Exception:
                        # 재고 ID가 이미 사라진 경우는 무시하고 연결기록 정리만 계속한다.
                        pass

                    if delete_qty >= item_qty:
                        con.execute(
                            'DELETE FROM export_waiting_items WHERE id=? AND COALESCE(confirmed,0)=0',
                            (int(item['id']),),
                        )
                    else:
                        con.execute(
                            'UPDATE export_waiting_items SET qty=? WHERE id=? AND COALESCE(confirmed,0)=0',
                            (item_qty - delete_qty, int(item['id'])),
                        )
                    remaining -= delete_qty

            _set_order_status(con.cursor(), order_id, now)
            con.commit()
    except Exception:
        # 강제삭제에서는 다른 WMS 재고 오류가 선택행 삭제를 막으면 안 된다.
        return


def reconcile_orphan_waiting_items(export_no: str) -> int:
    """EXPORT 저장행에서 삭제됐지만 WMS에 남은 미확정 행을 정리한다.

    shipment_items를 수출확정 전 목록의 기준으로 삼는다. 확정된 수량은 건드리지
    않고, 원본 inventory id별로 저장 수량을 초과한 미확정 연결만 제거한다.
    P 재고가 이미 없어도 연결행은 제거해 확정 단계에서 다시 차감하지 않는다.
    """
    normalized_export_no = str(export_no or '').strip()
    if not normalized_export_no:
        return 0

    cases = export_db.rows(
        '''SELECT id FROM export_cases
           WHERE TRIM(export_no)=TRIM(?)
             AND case_type<>'historical'
             AND status<>'취소' AND stage<>'취소'
           ORDER BY id''',
        (normalized_export_no,),
    )
    if len(cases) != 1:
        return 0
    case_id = int(cases[0]['id'])
    expected_rows = export_db.rows(
        '''SELECT source_inventory_id,CAST(SUM(requested_qty) AS INTEGER) AS qty
           FROM shipment_items
           WHERE case_id=? AND source_inventory_id IS NOT NULL
           GROUP BY source_inventory_id''',
        (case_id,),
    )
    expected_total = {
        int(row['source_inventory_id']): max(0, int(row['qty'] or 0))
        for row in expected_rows
        if int(row['source_inventory_id'] or 0) > 0
    }

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    removed = 0
    with wms_connect() as con:
        orders = con.execute(
            '''SELECT id FROM export_waiting_orders
               WHERE TRIM(export_no)=TRIM(?)
                 AND status IN ('waiting','partial','confirmed')
               ORDER BY id''',
            (normalized_export_no,),
        ).fetchall()
        if len(orders) != 1:
            return 0
        order_id = int(orders[0][0])
        items = con.execute(
            '''SELECT id,source_inventory_id,waiting_inventory_id,company,product_name,
                      IFNULL(warehouse_name,''),IFNULL(lot,'-'),IFNULL(exp_date,'-'),
                      source_location,qty,COALESCE(confirmed,0),IFNULL(waiting_location,'P')
               FROM export_waiting_items
               WHERE order_id=? ORDER BY COALESCE(confirmed,0) DESC,id''',
            (order_id,),
        ).fetchall()
        keys = [
            'id','source_inventory_id','waiting_inventory_id','company','product_name',
            'warehouse_name','lot','exp_date','source_location','qty','confirmed','waiting_location',
        ]
        confirmed_by_source: dict[int, int] = {}
        waiting_items: list[dict] = []
        for raw in items:
            item = dict(zip(keys, raw))
            source_id = int(item.get('source_inventory_id') or 0)
            if source_id <= 0:
                continue
            if int(item.get('confirmed') or 0):
                confirmed_by_source[source_id] = (
                    confirmed_by_source.get(source_id, 0) + int(item.get('qty') or 0)
                )
            else:
                waiting_items.append(item)

        allowed = {
            source_id: max(0, qty - confirmed_by_source.get(source_id, 0))
            for source_id, qty in expected_total.items()
        }
        kept_by_source: dict[int, int] = {}
        for item in waiting_items:
            source_id = int(item['source_inventory_id'])
            item_qty = max(0, int(item.get('qty') or 0))
            keep_qty = min(
                item_qty,
                max(0, allowed.get(source_id, 0) - kept_by_source.get(source_id, 0)),
            )
            kept_by_source[source_id] = kept_by_source.get(source_id, 0) + keep_qty
            excess_qty = item_qty - keep_qty
            if excess_qty <= 0:
                continue

            try:
                p_row = _matching_p_row(con.cursor(), item)
                if p_row:
                    restore_qty = min(int(p_row[1] or 0), excess_qty)
                    if restore_qty > 0:
                        con.execute(
                            'UPDATE inventory SET qty=?,updated_at=? WHERE id=?',
                            (int(p_row[1] or 0) - restore_qty, now, int(p_row[0])),
                        )
                        source_location = str(item.get('source_location') or '').strip()
                        if source_location and source_location.upper() not in STAGING_LOCATIONS:
                            _add(con.cursor(), item, source_location, restore_qty, now, 1)
            except Exception:
                # 실제 재고가 이미 삭제/이동된 경우에도 고아 연결 제거는 계속한다.
                pass

            if keep_qty:
                con.execute(
                    'UPDATE export_waiting_items SET qty=? WHERE id=? AND COALESCE(confirmed,0)=0',
                    (keep_qty, int(item['id'])),
                )
            else:
                con.execute(
                    'DELETE FROM export_waiting_items WHERE id=? AND COALESCE(confirmed,0)=0',
                    (int(item['id']),),
                )
            removed += excess_qty

        if removed:
            _set_order_status(con.cursor(), order_id, now)
            con.commit()
    return removed


def force_delete_stale_rows(*, case_id: int, order_item_id: int, shipment_ids: list[int]) -> dict:
    """사용자가 체크한 저장재고 행을 다른 재고 상태와 무관하게 삭제한다."""
    ids = {int(value) for value in shipment_ids if int(value) > 0}
    if not ids:
        return {'deleted': 0, 'skipped_valid': 0}

    case = export_service.get_case(case_id)
    if case is None:
        raise ValueError('수출 건을 찾을 수 없습니다.')

    selected_rows = _selected_rows_from_db(case_id, order_item_id, ids)
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # WMS 복구/정리는 best-effort로만 수행한다. 어떤 오류도 선택행 삭제를 막지 않는다.
    _best_effort_cleanup_wms(
        export_no=str(case.get('export_no') or '').strip(),
        rows=selected_rows,
        now=now,
    )

    # 화면에서 사용자가 체크한 shipment ID 자체를 직접 삭제한다.
    export_db.executemany(
        'DELETE FROM shipment_items WHERE id=? AND case_id=? AND order_item_id=?',
        [(shipment_id, case_id, order_item_id) for shipment_id in sorted(ids)],
    )
    export_db.execute(
        '''DELETE FROM boxes
           WHERE case_id=?
             AND NOT EXISTS(
                 SELECT 1 FROM shipment_items s
                 WHERE s.case_id=boxes.case_id AND s.box_no=boxes.box_no
             )''',
        (case_id,),
    )
    shipment_service.sync_case_stage(case_id)

    return {'deleted': len(ids), 'skipped_valid': 0}
