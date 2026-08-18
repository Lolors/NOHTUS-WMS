from __future__ import annotations

from datetime import datetime

import nohtus.export_app.services.wms_link_service as link_service
import nohtus.services.export_waiting as export_waiting_service
from nohtus.db import connect, q as wms_q
from nohtus.export_app.services import export_service, shipment_service


def _editable_order_id(export_no: str) -> int | None:
    """수출번호에 연결된 현재 WMS 수출대기/확정 건 하나를 찾는다.

    완전 확정된 건도 수출대기 저장 화면에서 품목을 다시 수정할 수 있으므로
    waiting/partial뿐 아니라 confirmed도 수정 대상으로 포함한다.
    """
    df = wms_q(
        """SELECT id,status FROM export_waiting_orders
           WHERE TRIM(export_no)=TRIM(?)
             AND status IN ('waiting','partial','confirmed')
           ORDER BY CASE status WHEN 'waiting' THEN 0 WHEN 'partial' THEN 1 ELSE 2 END, id DESC""",
        (str(export_no or '').strip(),),
    )
    if df.empty:
        return None
    open_rows = df[df['status'].isin(['waiting', 'partial'])]
    if len(open_rows.index) == 1:
        return int(open_rows.iloc[0]['id'])
    if len(open_rows.index) > 1:
        raise ValueError(
            f"수출번호 {export_no}에 진행 중인 수출대기 건이 여러 개입니다. "
            "기존 건을 하나로 병합하거나 새 수출번호를 사용하세요."
        )
    if len(df.index) == 1:
        return int(df.iloc[0]['id'])
    raise ValueError(
        f"수출번호 {export_no}에 연결된 수출확정 건이 여러 개입니다. "
        "수출번호 중복을 먼저 정리하세요."
    )


def _match_date(value: object) -> str:
    return link_service._match_date(value)


def _match_value(value: object) -> str:
    return link_service._match_value(value)


def _match_text(value: object) -> str:
    return link_service._match_text(value)


def _fill_source_links(rows: list[dict], waiting_rows: list[dict]) -> None:
    """저장행의 원본 inventory id를 복구한다.

    한 WMS 재고가 여러 shipment 행으로 나뉜 경우에도 같은 source_inventory_id를
    여러 행이 공유할 수 있게 하며, WMS 대기행에서 못 찾으면 원래 재고 키로
    inventory를 직접 찾는다.
    """
    for row in rows:
        if row.get('source_inventory_id'):
            continue
        matches = [
            waiting for waiting in waiting_rows
            if _match_text(waiting.get('product_name')) == _match_text(row.get('product_name'))
            and (not _match_value(row.get('business_unit'))
                 or _match_value(waiting.get('company')) == _match_value(row.get('business_unit')))
            and _match_value(waiting.get('lot')) == _match_value(row.get('lot_no'))
            and _match_date(waiting.get('exp_date')) == _match_date(row.get('expiry_date'))
        ]
        source_ids = {int(x.get('source_inventory_id') or 0) for x in matches if x.get('source_inventory_id')}
        if len(source_ids) == 1:
            source_id = next(iter(source_ids))
            match = matches[0]
            row['source_inventory_id'] = source_id
            row['source_location'] = (
                row.get('source_location') or row.get('location')
                or match.get('source_location') or ''
            )
            continue

        company = str(row.get('business_unit') or '').strip()
        product = str(row.get('product_name') or '').strip()
        lot = str(row.get('lot_no') or '').strip()
        exp = str(row.get('expiry_date') or '').strip()
        location = str(row.get('source_location') or row.get('location') or '').strip()
        if not company or not product:
            continue
        params = [company, product]
        clauses = ["company=?", "product_name=?", "UPPER(TRIM(COALESCE(location,'')))<>'P'"]
        if lot:
            clauses.append("IFNULL(lot,'')=?")
            params.append(lot)
        if exp:
            clauses.append("IFNULL(exp_date,'')=?")
            params.append(exp)
        if location and location.upper() != 'P':
            clauses.append("location=?")
            params.append(location)
        candidates = wms_q(
            f"SELECT id,location FROM inventory WHERE {' AND '.join(clauses)} ORDER BY id DESC",
            tuple(params),
        )
        if len(candidates.index) == 1:
            row['source_inventory_id'] = int(candidates.iloc[0]['id'])
            row['source_location'] = str(candidates.iloc[0]['location'] or location)


def _rows_with_live_source_inventory(rows: list[dict]) -> list[dict]:
    """Return only canonical shipment rows that still point to real inventory."""
    source_ids = {
        int(row.get('source_inventory_id') or 0)
        for row in rows
        if int(row.get('source_inventory_id') or 0) > 0
    }
    if not source_ids:
        return []
    placeholders = ','.join('?' for _ in source_ids)
    with connect() as con:
        live_ids = {
            int(row[0])
            for row in con.execute(
                f'SELECT id FROM inventory WHERE id IN ({placeholders})',
                tuple(sorted(source_ids)),
            ).fetchall()
        }
    return [
        row for row in rows
        if int(row.get('source_inventory_id') or 0) in live_ids
    ]


def _empty_target_save(order_id: int, *, export_no: str, country: str, buyer: str, transport_method: str) -> dict:
    """마지막 저장행까지 삭제하는 경우 빈 cart 검증을 우회해 정상 원복한다."""
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    title = f"{country}-{buyer or '미지정'}-{transport_method}"
    with connect() as con:
        cur = con.cursor()
        export_waiting_service.ensure_export_waiting_tables(cur)
        row = cur.execute(
            "SELECT status FROM export_waiting_orders WHERE id=?",
            (int(order_id),),
        ).fetchone()
        if not row or str(row[0]) not in {'waiting', 'partial', 'confirmed'}:
            raise ValueError('수정할 수출대기 건을 찾을 수 없습니다.')
        status = str(row[0])
        cur.execute(
            """UPDATE export_waiting_orders
               SET export_no=?,country=?,buyer=?,transport_method=?,title=?,updated_at=?
               WHERE id=?""",
            (export_no, country, buyer, transport_method, title, now, int(order_id)),
        )
        if status in {'partial', 'confirmed'}:
            export_waiting_service._apply_confirmed_export_item_changes(
                cur, int(order_id), {}, {}, now, title, export_no
            )
        else:
            export_waiting_service._apply_export_waiting_item_changes(
                cur, int(order_id), {}, {}, now, title, export_no
            )
        con.commit()
    return {'order_id': int(order_id), 'row_count': 0, 'total_qty': 0, 'title': title}


def _patched_save_picked_inventory(*, case_id: int, order_item_id: int, kept_rows: list[dict], picked_rows: list[dict]) -> dict:
    case = export_service.get_case(case_id)
    if case is None:
        raise ValueError('수출 건을 찾을 수 없습니다.')
    export_no = str(case['export_no'] or '').strip()
    if not export_no:
        raise ValueError('이 수출 건에는 수출번호가 없습니다.')
    country = str(case['country'] or '').strip()
    if not country:
        raise ValueError('이 수출 건에는 국가가 입력되어 있지 않습니다. 먼저 국가를 입력하세요.')
    buyer = str(case.get('buyer') or '')
    transport_method = link_service.TRANSPORT_MODE_TO_METHOD.get(
        str(case['transport_mode'] or '').strip(), '미지정'
    )
    editing_order_id = _editable_order_id(export_no)

    all_kept_rows = [dict(row) for row in (kept_rows or [])]
    case_rows = [dict(row) for row in shipment_service.list_case_items(case_id)]
    current_rows = [
        row for row in case_rows
        if int(row['order_item_id'] or 0) == int(order_item_id)
    ]
    other_rows = [
        row for row in case_rows
        if int(row['order_item_id'] or 0) != int(order_item_id)
    ]
    if editing_order_id:
        waiting_rows = link_service._waiting_rows_for_order(editing_order_id)
        _fill_source_links(all_kept_rows, waiting_rows)
        _fill_source_links(other_rows, waiting_rows)

    linked_kept = [row for row in all_kept_rows if row.get('source_inventory_id')]
    linked_other = [row for row in other_rows if row.get('source_inventory_id')]
    canonical_rows = _rows_with_live_source_inventory(linked_other + linked_kept)
    cart = link_service.cart_rows_after_selected_order_edit(
        [], [], canonical_rows, list(picked_rows or [])
    )

    mirror_rows = [
        {
            '_id': row['id'],
            'business_unit': row.get('business_unit') or '',
            'location': row.get('source_location') or row.get('location') or '',
            'source_inventory_id': row.get('source_inventory_id'),
            'product_name': row.get('product_name') or '',
            'lot_no': row.get('lot_no') or '',
            'expiry_date': row.get('expiry_date') or '',
            'requested_qty': float(row.get('requested_qty') or 0),
        }
        for row in all_kept_rows
    ]
    mirror_rows += [
        {
            '_id': None,
            'business_unit': pick.get('company') or '',
            'location': pick.get('location') or '',
            'source_inventory_id': int(pick['inventory_id']),
            'product_name': pick.get('product_name') or '',
            'lot_no': pick.get('lot') or '',
            'expiry_date': pick.get('exp_date') or '',
            'requested_qty': float(pick.get('qty') or 0),
        }
        for pick in (picked_rows or []) if float(pick.get('qty') or 0) > 0
    ]
    original_rows = [
        {
            '_id': row['id'],
            'business_unit': row.get('business_unit') or '',
            'location': row.get('source_location') or row.get('location') or '',
            'source_inventory_id': row.get('source_inventory_id'),
            'product_name': row.get('product_name') or '',
            'lot_no': row.get('lot_no') or '',
            'expiry_date': row.get('expiry_date') or '',
            'requested_qty': float(row.get('requested_qty') or 0),
        }
        for row in current_rows
    ]

    total_qty = shipment_service.save_for_order(case_id, order_item_id, mirror_rows)
    try:
        if cart:
            result = export_waiting_service.save_export_waiting_order(
                cart,
                country=country,
                buyer=buyer,
                transport_method=transport_method,
                export_no=export_no,
                editing_order_id=editing_order_id,
            )
        elif editing_order_id:
            result = _empty_target_save(
                editing_order_id,
                export_no=export_no,
                country=country,
                buyer=buyer,
                transport_method=transport_method,
            )
        else:
            result = {'order_id': 0, 'row_count': 0, 'total_qty': 0, 'title': ''}
    except Exception:
        shipment_service.save_for_order(case_id, order_item_id, original_rows)
        raise

    return {
        'order_id': int(result.get('order_id') or 0),
        'total_qty': total_qty,
        'row_count': len(mirror_rows),
    }


link_service._find_open_order_id = _editable_order_id
link_service.save_picked_inventory = _patched_save_picked_inventory
