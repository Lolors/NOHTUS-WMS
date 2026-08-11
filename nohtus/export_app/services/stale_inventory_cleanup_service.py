from __future__ import annotations

from datetime import datetime

from nohtus.db import connect as wms_connect
from nohtus.export_app import db as export_db
from nohtus.export_app.services import export_service, shipment_service
from nohtus.services.export_waiting import _add


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
                  source_location,qty,COALESCE(confirmed,0)
           FROM export_waiting_items
           WHERE order_id=? AND COALESCE(confirmed,0)=0{source_clause}
           ORDER BY id''',
        tuple(params),
    ).fetchall()
    keys = [
        'id','source_inventory_id','waiting_inventory_id','company','product_name',
        'warehouse_name','lot','exp_date','source_location','qty','confirmed',
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
    waiting_inventory_id = int(item.get('waiting_inventory_id') or 0)
    if waiting_inventory_id:
        row = cur.execute(
            "SELECT id,qty FROM inventory WHERE id=? AND UPPER(TRIM(COALESCE(location,'')))='P'",
            (waiting_inventory_id,),
        ).fetchone()
        if row:
            return row

    rows = cur.execute(
        '''SELECT id,qty FROM inventory
           WHERE UPPER(TRIM(COALESCE(location,'')))='P'
             AND company=? AND product_name=?
             AND IFNULL(warehouse_name,'')=?
             AND IFNULL(lot,'-')=? AND IFNULL(exp_date,'-')=?
           ORDER BY id''',
        (
            str(item.get('company') or ''),
            str(item.get('product_name') or ''),
            str(item.get('warehouse_name') or ''),
            str(item.get('lot') or '-') or '-',
            str(item.get('exp_date') or '-') or '-',
        ),
    ).fetchall()
    return rows[0] if len(rows) == 1 else None


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
                                if source_location and source_location.upper() != 'P':
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

            remaining_status = con.execute(
                '''SELECT
                       SUM(CASE WHEN COALESCE(confirmed,0)=0 THEN 1 ELSE 0 END),
                       SUM(CASE WHEN COALESCE(confirmed,0)=1 THEN 1 ELSE 0 END)
                   FROM export_waiting_items WHERE order_id=?''',
                (order_id,),
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
            con.execute(
                'UPDATE export_waiting_orders SET status=?,updated_at=? WHERE id=?',
                (status, now, order_id),
            )
            con.commit()
    except Exception:
        # 강제삭제에서는 다른 WMS 재고 오류가 선택행 삭제를 막으면 안 된다.
        return


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
