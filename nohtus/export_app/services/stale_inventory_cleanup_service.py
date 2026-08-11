from __future__ import annotations

from nohtus.db import connect as wms_connect
from nohtus.export_app import db as export_db
from nohtus.export_app.services import export_service, shipment_service


def _same_text(left: object, right: object, default: str = '') -> bool:
    return str(left or default).strip() == str(right or default).strip()


def _matching_p_row(cur, waiting_item: dict):
    waiting_inventory_id = int(waiting_item.get('waiting_inventory_id') or 0)
    if waiting_inventory_id:
        row = cur.execute(
            "SELECT id,qty FROM inventory WHERE id=? AND UPPER(TRIM(COALESCE(location,'')))='P'",
            (waiting_inventory_id,),
        ).fetchone()
        if row and int(row[1] or 0) >= int(waiting_item.get('qty') or 0):
            return row

    rows = cur.execute(
        """SELECT id,qty FROM inventory
           WHERE UPPER(TRIM(COALESCE(location,'')))='P'
             AND company=? AND product_name=?
             AND IFNULL(warehouse_name,'')=?
             AND IFNULL(lot,'-')=? AND IFNULL(exp_date,'-')=?
           ORDER BY id""",
        (
            str(waiting_item.get('company') or ''),
            str(waiting_item.get('product_name') or ''),
            str(waiting_item.get('warehouse_name') or ''),
            str(waiting_item.get('lot') or '-') or '-',
            str(waiting_item.get('exp_date') or '-') or '-',
        ),
    ).fetchall()
    candidates = [row for row in rows if int(row[1] or 0) >= int(waiting_item.get('qty') or 0)]
    return candidates[0] if len(candidates) == 1 else None


def _waiting_items_for_source(cur, order_id: int, row: dict) -> list[dict]:
    source_id = int(row.get('source_inventory_id') or 0)
    if not source_id:
        return []
    raw = cur.execute(
        """SELECT id,source_inventory_id,waiting_inventory_id,company,product_name,
                  IFNULL(warehouse_name,''),IFNULL(lot,'-'),IFNULL(exp_date,'-'),
                  source_location,qty,COALESCE(confirmed,0)
           FROM export_waiting_items
           WHERE order_id=? AND source_inventory_id=? AND COALESCE(confirmed,0)=0
           ORDER BY id""",
        (order_id, source_id),
    ).fetchall()
    keys = [
        'id','source_inventory_id','waiting_inventory_id','company','product_name',
        'warehouse_name','lot','exp_date','source_location','qty','confirmed',
    ]
    items = [dict(zip(keys, item)) for item in raw]
    return [
        item for item in items
        if _same_text(item.get('company'), row.get('business_unit'))
        and _same_text(item.get('product_name'), row.get('product_name'))
        and _same_text(item.get('lot'), row.get('lot_no'), '-')
        and _same_text(item.get('exp_date'), row.get('expiry_date'), '-')
    ] or items


def force_delete_stale_rows(*, case_id: int, order_item_id: int, shipment_ids: list[int]) -> dict:
    """강제로 지워도 안전한 '고아' 저장행만 제거한다.

    정상 P 재고가 확인되는 행은 여기서 건드리지 않는다. source_inventory_id가
    없거나, 대응하는 WMS 대기행/P 재고가 이미 사라진 행만 EXPORT 미러와 WMS의
    끊어진 대기행 기록에서 제거한다.
    """
    ids = {int(value) for value in shipment_ids if int(value) > 0}
    if not ids:
        return {'deleted': 0, 'skipped_valid': 0}

    case = export_service.get_case(case_id)
    if case is None:
        raise ValueError('수출 건을 찾을 수 없습니다.')
    export_no = str(case.get('export_no') or '').strip()

    current_rows = [
        dict(row) for row in shipment_service.list_case_items(case_id)
        if int(row.get('order_item_id') or 0) == int(order_item_id)
        and int(row.get('id') or 0) in ids
    ]
    if not current_rows:
        return {'deleted': 0, 'skipped_valid': 0}

    stale_shipment_ids: set[int] = set()
    stale_waiting_item_ids: set[int] = set()
    skipped_valid = 0

    with wms_connect() as con:
        open_orders = con.execute(
            """SELECT id FROM export_waiting_orders
               WHERE TRIM(export_no)=TRIM(?) AND status IN ('waiting','partial')
               ORDER BY id""",
            (export_no,),
        ).fetchall() if export_no else []
        if len(open_orders) > 1:
            raise ValueError('같은 수출번호의 진행 중 수출대기 건이 여러 개라 강제 삭제를 중단했습니다.')
        order_id = int(open_orders[0][0]) if open_orders else 0

        for row in current_rows:
            shipment_id = int(row['id'])
            if not row.get('source_inventory_id') or not order_id:
                stale_shipment_ids.add(shipment_id)
                continue

            waiting_items = _waiting_items_for_source(con.cursor(), order_id, row)
            if not waiting_items:
                stale_shipment_ids.add(shipment_id)
                continue

            valid_p_exists = False
            for item in waiting_items:
                if _matching_p_row(con.cursor(), item):
                    valid_p_exists = True
                    break
            if valid_p_exists:
                skipped_valid += 1
                continue

            stale_shipment_ids.add(shipment_id)
            stale_waiting_item_ids.update(int(item['id']) for item in waiting_items)

        if stale_waiting_item_ids:
            con.executemany(
                'DELETE FROM export_waiting_items WHERE id=? AND COALESCE(confirmed,0)=0',
                [(item_id,) for item_id in sorted(stale_waiting_item_ids)],
            )
            if order_id:
                remaining = con.execute(
                    """SELECT
                           SUM(CASE WHEN COALESCE(confirmed,0)=0 THEN 1 ELSE 0 END),
                           SUM(CASE WHEN COALESCE(confirmed,0)=1 THEN 1 ELSE 0 END)
                       FROM export_waiting_items WHERE order_id=?""",
                    (order_id,),
                ).fetchone()
                waiting_count = int((remaining or [0, 0])[0] or 0)
                confirmed_count = int((remaining or [0, 0])[1] or 0)
                if waiting_count and confirmed_count:
                    status = 'partial'
                elif waiting_count:
                    status = 'waiting'
                elif confirmed_count:
                    status = 'confirmed'
                else:
                    status = 'cancelled'
                con.execute(
                    "UPDATE export_waiting_orders SET status=?,updated_at=datetime('now','localtime') WHERE id=?",
                    (status, order_id),
                )
            con.commit()

    if stale_shipment_ids:
        export_db.executemany(
            'DELETE FROM shipment_items WHERE id=? AND case_id=? AND order_item_id=?',
            [(shipment_id, case_id, order_item_id) for shipment_id in sorted(stale_shipment_ids)],
        )
        export_db.execute(
            """DELETE FROM boxes
               WHERE case_id=?
                 AND NOT EXISTS(
                     SELECT 1 FROM shipment_items s
                     WHERE s.case_id=boxes.case_id AND s.box_no=boxes.box_no
                 )""",
            (case_id,),
        )
        shipment_service.sync_case_stage(case_id)

    return {'deleted': len(stale_shipment_ids), 'skipped_valid': skipped_valid}
