from __future__ import annotations

from datetime import datetime

from nohtus.db import connect as wms_connect
from nohtus.export_app import db as export_db
from nohtus.export_app.services import export_service, shipment_service
from nohtus.services.export_waiting import _add


def _same_text(left: object, right: object, default: str = '') -> bool:
    return str(left or default).strip() == str(right or default).strip()


def _matching_p_row(cur, waiting_item: dict):
    waiting_inventory_id = int(waiting_item.get('waiting_inventory_id') or 0)
    if waiting_inventory_id:
        row = cur.execute(
            "SELECT id,qty FROM inventory WHERE id=? AND UPPER(TRIM(COALESCE(location,'')))='P'",
            (waiting_inventory_id,),
        ).fetchone()
        if row:
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
    return rows[0] if len(rows) == 1 else None


def _waiting_items_for_source(cur, order_id: int, row: dict) -> list[dict]:
    source_id = int(row.get('source_inventory_id') or 0)
    if source_id:
        raw = cur.execute(
            """SELECT id,source_inventory_id,waiting_inventory_id,company,product_name,
                      IFNULL(warehouse_name,''),IFNULL(lot,'-'),IFNULL(exp_date,'-'),
                      source_location,qty,COALESCE(confirmed,0)
               FROM export_waiting_items
               WHERE order_id=? AND source_inventory_id=? AND COALESCE(confirmed,0)=0
               ORDER BY id""",
            (order_id, source_id),
        ).fetchall()
    else:
        raw = cur.execute(
            """SELECT id,source_inventory_id,waiting_inventory_id,company,product_name,
                      IFNULL(warehouse_name,''),IFNULL(lot,'-'),IFNULL(exp_date,'-'),
                      source_location,qty,COALESCE(confirmed,0)
               FROM export_waiting_items
               WHERE order_id=? AND COALESCE(confirmed,0)=0
                 AND company=? AND product_name=?
                 AND IFNULL(lot,'-')=? AND IFNULL(exp_date,'-')=?
               ORDER BY id""",
            (
                order_id,
                str(row.get('business_unit') or ''),
                str(row.get('product_name') or ''),
                str(row.get('lot_no') or '-') or '-',
                str(row.get('expiry_date') or '-') or '-',
            ),
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
    return matched or items


def _restore_selected_waiting_inventory(cur, item: dict, delete_qty: int, now: str) -> None:
    """선택 삭제분의 P 재고가 남아 있으면 원래 로케이션으로 되돌린다.

    이미 P 재고가 사라졌으면 오류를 내지 않고 연결기록만 정리할 수 있게 둔다.
    """
    if delete_qty <= 0:
        return
    p_row = _matching_p_row(cur, item)
    if not p_row:
        return
    current_qty = int(p_row[1] or 0)
    restore_qty = min(current_qty, delete_qty)
    if restore_qty <= 0:
        return
    cur.execute(
        "UPDATE inventory SET qty=?,updated_at=? WHERE id=?",
        (current_qty - restore_qty, now, int(p_row[0])),
    )
    source_location = str(item.get('source_location') or '').strip()
    if source_location and source_location.upper() != 'P':
        _add(cur, item, source_location, restore_qty, now, 1)


def _selected_rows_from_db(case_id: int, order_item_id: int, ids: set[int]) -> list[dict]:
    if not ids:
        return []
    placeholders = ','.join('?' for _ in ids)
    rows = export_db.rows(
        f"""SELECT id,case_id,order_item_id,
                   COALESCE(NULLIF(TRIM(business_unit),''), NULLIF(TRIM(location),''), '') AS business_unit,
                   location AS source_location, source_inventory_id,
                   product_name, lot_no, expiry_date, requested_qty, box_no
            FROM shipment_items
            WHERE case_id=? AND order_item_id=? AND id IN ({placeholders})
            ORDER BY id""",
        tuple([case_id, order_item_id, *sorted(ids)]),
    )
    return [dict(row) for row in rows]


def force_delete_stale_rows(*, case_id: int, order_item_id: int, shipment_ids: list[int]) -> dict:
    """사용자가 선택한 저장재고 행만 독립적으로 삭제한다.

    다른 저장재고의 원본 ID가 깨져 있어도 선택행 삭제를 막지 않는다. 선택행에
    대응되는 정상 P 재고가 있으면 원래 source_location으로 복구하고, P 재고가
    이미 사라졌다면 그 오류는 무시한 채 끊어진 WMS 연결기록과 EXPORT 미러행만
    정리한다. 확정된 수출품목은 건드리지 않는다.
    """
    ids = {int(value) for value in shipment_ids if int(value) > 0}
    if not ids:
        return {'deleted': 0, 'skipped_valid': 0}

    case = export_service.get_case(case_id)
    if case is None:
        raise ValueError('수출 건을 찾을 수 없습니다.')
    export_no = str(case.get('export_no') or '').strip()

    # 캐시된 list_case_items가 아니라 DB에서 사용자가 선택한 shipment id를 직접 찾는다.
    current_rows = _selected_rows_from_db(case_id, order_item_id, ids)
    if not current_rows:
        return {'deleted': 0, 'skipped_valid': 0}

    delete_shipment_ids = {int(row['id']) for row in current_rows}
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    with wms_connect() as con:
        open_orders = con.execute(
            """SELECT id FROM export_waiting_orders
               WHERE TRIM(export_no)=TRIM(?) AND status IN ('waiting','partial')
               ORDER BY id""",
            (export_no,),
        ).fetchall() if export_no else []
        if len(open_orders) > 1:
            raise ValueError('같은 수출번호의 진행 중 수출대기 건이 여러 개라 선택 삭제를 중단했습니다.')
        order_id = int(open_orders[0][0]) if open_orders else 0

        if order_id:
            for row in current_rows:
                remaining_to_delete = max(0, int(float(row.get('requested_qty') or 0)))
                waiting_items = _waiting_items_for_source(con.cursor(), order_id, row)
                for item in waiting_items:
                    if remaining_to_delete <= 0:
                        break
                    item_qty = max(0, int(item.get('qty') or 0))
                    delete_qty = min(item_qty, remaining_to_delete)
                    _restore_selected_waiting_inventory(con.cursor(), item, delete_qty, now)
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
                    remaining_to_delete -= delete_qty

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
                "UPDATE export_waiting_orders SET status=?,updated_at=? WHERE id=?",
                (status, now, order_id),
            )
        con.commit()

    export_db.executemany(
        'DELETE FROM shipment_items WHERE id=? AND case_id=? AND order_item_id=?',
        [(shipment_id, case_id, order_item_id) for shipment_id in sorted(delete_shipment_ids)],
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

    return {'deleted': len(delete_shipment_ids), 'skipped_valid': 0}
