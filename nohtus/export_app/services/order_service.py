from __future__ import annotations

import re
import math
from difflib import SequenceMatcher

import streamlit as st

from nohtus.export_app import db
from nohtus.export_app.utils.dates import now_text


def normalize_product_name(value: str) -> str:
    text = str(value or '').casefold()
    replacements = {
        '퍼센트': '%',
        '프로': '%',
        '앰플': 'am',
        'ampoule': 'am',
        'amp': 'am',
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return re.sub(r'[^0-9a-z가-힣%]+', '', text)


@st.cache_data(show_spinner=False, persist='disk', max_entries=64)
def _editable_cases_query(cache_token: tuple[int, int, int, int]) -> list[dict]:
    rows = db.rows(
        '''WITH product_summary AS (
               SELECT case_id, GROUP_CONCAT(product_name, ', ') AS product_names
               FROM order_items
               GROUP BY case_id
           )
           SELECT c.id, c.export_no, c.buyer, c.country, c.transport_mode, c.stage,
                  c.status, c.note, c.actual_ship_date, c.case_type, c.created_at,
                  COALESCE(p.product_names, '') AS product_names
           FROM export_cases c
           LEFT JOIN product_summary p ON p.case_id=c.id
           WHERE c.stage<>'취소'
           ORDER BY COALESCE(NULLIF(c.actual_ship_date,''), c.created_at) DESC'''
    )
    return [dict(row) for row in rows]


def clear_editable_cases_cache() -> None:
    _editable_cases_query.clear()
    _cached_orders_for_case.clear()


def list_editable_cases() -> list[dict]:
    return _editable_cases_query(db.read_cache_token())


@st.cache_data(show_spinner=False, persist='disk', max_entries=256)
def _cached_orders_for_case(
    case_id: int,
    cache_token: tuple[int, int, int, int],
) -> list[dict]:
    rows = db.rows(
        '''SELECT id, product_name,
                  quantity AS document_quantity,
                  quantity * CASE
                    WHEN COALESCE(ea_per_document_unit, 0) > 0 THEN ea_per_document_unit
                    ELSE 1
                  END AS quantity,
                  'EA' AS unit,
                  COALESCE(NULLIF(TRIM(document_unit), ''), NULLIF(TRIM(unit), ''), 'EA') AS document_unit,
                  CASE
                    WHEN COALESCE(ea_per_document_unit, 0) > 0 THEN ea_per_document_unit
                    ELSE 1
                  END AS ea_per_document_unit,
                  purchase_price, created_at
           FROM order_items
           WHERE case_id=?
           ORDER BY id''',
        (case_id,),
    )
    return [dict(row) for row in rows]


def list_for_case(case_id: int):
    return _cached_orders_for_case(int(case_id), db.read_cache_token())


def get_order_items_dataframe(case_id: int):
    import pandas as pd

    rows = list_for_case(case_id)
    return pd.DataFrame([
        {
            '_id': row['id'],
            '제품명': row['product_name'],
            '수량': row['document_quantity'],
            '단위': row['document_unit'],
            '1단위당 EA': row['ea_per_document_unit'],
            '매입가': row['purchase_price'],
        }
        for row in rows
    ])


def _append_price_history(
    case_id: int,
    order_item_id: int,
    product_name: str,
    purchase_price: float,
    quantity: float,
    unit: str,
    *,
    created_at: str | None = None,
) -> None:
    db.execute(
        '''INSERT INTO purchase_price_history(
               case_id,order_item_id,product_name,normalized_name,purchase_price,quantity,unit,created_at
           ) VALUES (?,?,?,?,?,?,?,?)''',
        (
            case_id,
            order_item_id,
            product_name,
            normalize_product_name(product_name),
            purchase_price,
            quantity,
            unit,
            created_at or now_text(),
        ),
    )


def create_order_items(
    case_id: int,
    items: list[tuple[str, float, str, float]],
    *,
    historical: bool = False,
) -> None:
    now = now_text()
    for product_name, quantity, unit, purchase_price in items:
        order_id = db.execute(
            '''INSERT INTO order_items(case_id,product_name,quantity,unit,purchase_price,created_at)
               VALUES (?,?,?,?,?,?)''',
            (case_id, product_name, quantity, unit, purchase_price, now),
        )
        _append_price_history(case_id, order_id, product_name, purchase_price, quantity, unit, created_at=now)
        if historical:
            db.execute(
                '''INSERT INTO shipment_items(
                       case_id,order_item_id,business_unit,location,product_name,
                       lot_no,expiry_date,requested_qty,box_no,created_at,updated_at
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
                (case_id, order_id, '', '', product_name, '', '', quantity, None, now, now),
            )


def create_historical_case_details(
    case_id: int,
    items: list[tuple[str, str, str, str, str, float, float, int]],
    boxes: list[tuple[int, float, float, float, float]],
    *,
    method: str,
    actual_ship_date: str,
    tracking_no: str = '',
    driver_name: str = '',
    driver_phone: str = '',
    consignee_name: str = '',
    consignee_address: str = '',
) -> None:
    now = now_text()
    for ship_from, product_name, unit, lot_no, expiry_date, quantity, purchase_price, box_no in items:
        order_id = db.execute(
            '''INSERT INTO order_items(case_id,product_name,quantity,unit,purchase_price,created_at)
               VALUES (?,?,?,?,?,?)''',
            (case_id, product_name, quantity, unit, purchase_price, now),
        )
        _append_price_history(case_id, order_id, product_name, purchase_price, quantity, unit, created_at=now)
        db.execute(
            '''INSERT INTO shipment_items(
                   case_id,order_item_id,business_unit,location,product_name,
                   lot_no,expiry_date,requested_qty,box_no,created_at,updated_at
               ) VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
            (
                case_id, order_id, ship_from, ship_from, product_name,
                lot_no, expiry_date, quantity, box_no, now, now,
            ),
        )

    for box_no, length, width, height, weight in boxes:
        db.execute(
            '''INSERT OR REPLACE INTO boxes(
                   id,case_id,box_no,length_cm,width_cm,height_cm,weight_kg,updated_at
               ) VALUES (
                   (SELECT id FROM boxes WHERE case_id=? AND box_no=?),?,?,?,?,?,?,?
               )''',
            (case_id, box_no, case_id, box_no, length, width, height, weight, now),
        )

    db.execute(
        '''UPDATE export_cases
           SET domestic_method=?,tracking_no=?,driver_name=?,driver_phone=?,
               consignee_name=?,consignee_address=?,actual_ship_date=?,
               stage='국내배송',status='완료',updated_at=?
           WHERE id=?''',
        (
            method,
            tracking_no.strip(),
            driver_name.strip(),
            driver_phone.strip(),
            consignee_name.strip(),
            consignee_address.strip(),
            actual_ship_date,
            now,
            case_id,
        ),
    )


def find_similar_purchase_prices(product_name: str, limit: int = 8):
    normalized = normalize_product_name(product_name)
    if not normalized:
        return []

    candidates = db.rows(
        '''SELECT h.id,h.product_name,h.purchase_price,h.quantity,h.unit,h.created_at,
                  c.export_no,c.buyer,c.country
           FROM purchase_price_history h
           JOIN export_cases c ON c.id=h.case_id
           WHERE h.purchase_price>0
           ORDER BY h.created_at DESC
           LIMIT 300'''
    )
    scored = []
    for row in candidates:
        candidate_name = normalize_product_name(row['product_name'])
        if not candidate_name:
            continue
        if candidate_name == normalized:
            score = 1.0
        elif candidate_name in normalized or normalized in candidate_name:
            score = 0.92
        else:
            score = SequenceMatcher(None, normalized, candidate_name).ratio()
        if score < 0.48:
            continue
        item = dict(row)
        item['similarity'] = score
        scored.append(item)

    scored.sort(key=lambda item: (item['similarity'], item['created_at']), reverse=True)
    return scored[:limit]


def list_cost_cases():
    return db.rows(
        '''SELECT c.id,c.export_no,c.country,c.buyer,c.stage,c.status,c.created_at,c.actual_ship_date,
                  COUNT(o.id) AS item_count,
                  COALESCE(SUM(o.quantity * o.purchase_price),0) AS total_purchase_cost
           FROM export_cases c
           LEFT JOIN order_items o ON o.case_id=c.id
           WHERE c.stage<>'취소'
           GROUP BY c.id,c.export_no,c.country,c.buyer,c.stage,c.status,c.created_at,c.actual_ship_date
           ORDER BY COALESCE(NULLIF(c.actual_ship_date,''),c.created_at) DESC'''
    )


def get_cost_items_dataframe(case_id: int):
    import pandas as pd

    rows = db.rows(
        '''SELECT id AS _id,product_name AS 제품명,quantity AS 수량,unit AS 단위,
                  purchase_price AS 매입가,
                  quantity * purchase_price AS 매입금액
           FROM order_items
           WHERE case_id=?
           ORDER BY id''',
        (case_id,),
    )
    return pd.DataFrame([dict(row) for row in rows])


def sync_historical_shipments(case_id: int) -> None:
    case = db.row('SELECT case_type FROM export_cases WHERE id=?', (case_id,))
    if not case or case['case_type'] != 'historical':
        return

    now = now_text()
    orders = db.rows(
        'SELECT id, product_name, quantity FROM order_items WHERE case_id=? ORDER BY id',
        (case_id,),
    )
    order_ids = {int(row['id']) for row in orders}

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
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
                (case_id, order['id'], '', '', order['product_name'], '', '', order['quantity'], None, now, now),
            )

    linked = db.rows(
        'SELECT id, order_item_id FROM shipment_items WHERE case_id=? AND order_item_id IS NOT NULL',
        (case_id,),
    )
    for shipment in linked:
        if int(shipment['order_item_id']) not in order_ids:
            db.execute('DELETE FROM shipment_items WHERE id=?', (shipment['id'],))


def _clean_optional_row_id(raw_id) -> int | None:
    """Return a stable DB id for existing rows; new data-editor rows have NaN/NA ids."""
    if raw_id is None or raw_id == '':
        return None
    try:
        import pandas as pd
        if pd.isna(raw_id):
            return None
    except (TypeError, ValueError):
        return None
    try:
        numeric_id = int(raw_id)
    except (TypeError, ValueError, OverflowError):
        return None
    return numeric_id if numeric_id > 0 else None


def save_order_items(case_id: int, edited) -> None:
    now = now_text()
    with db.connect() as conn:
        existing_rows = conn.execute(
            '''SELECT o.id, o.product_name, o.quantity, o.unit, o.purchase_price
               FROM order_items o
               WHERE o.case_id=?
               ORDER BY o.id''',
            (case_id,),
        ).fetchall()
        existing = {int(row['id']): row for row in existing_rows}
        seen_ids: set[int] = set()

        for _, row in edited.iterrows():
            order_id = _clean_optional_row_id(row.get('_id'))
            product_name = str(row.get('제품명', '') or '').strip()
            quantity = float(row.get('수량', 0) or 0)
            unit = str(row.get('단위', 'EA') or 'EA').strip() or 'EA'
            purchase_price = float(row.get('매입가', 0) or 0)
            ea_per_document_unit = float(row.get('1단위당 EA', 1) or 1)
            if not math.isfinite(ea_per_document_unit) or ea_per_document_unit <= 0:
                raise ValueError('1단위당 EA는 0보다 커야 합니다.')

            if not product_name:
                continue

            if order_id and order_id in existing:
                previous = existing[order_id]
                seen_ids.add(order_id)
                conn.execute(
                    '''UPDATE order_items
                       SET product_name=?,quantity=?,unit=?,purchase_price=?,
                           document_unit=?,ea_per_document_unit=?
                       WHERE id=? AND case_id=?''',
                    (
                        product_name, quantity, unit, purchase_price,
                        unit, ea_per_document_unit, order_id, case_id,
                    ),
                )
                if (
                    float(previous['purchase_price'] or 0) != purchase_price
                    or str(previous['product_name']) != product_name
                ):
                    conn.execute(
                        '''INSERT INTO purchase_price_history(
                               case_id,order_item_id,product_name,normalized_name,purchase_price,quantity,unit,created_at
                           ) VALUES (?,?,?,?,?,?,?,?)''',
                        (
                            case_id,
                            order_id,
                            product_name,
                            normalize_product_name(product_name),
                            purchase_price,
                            quantity,
                            unit,
                            now,
                        ),
                    )
            else:
                cursor = conn.execute(
                    '''INSERT INTO order_items(
                           case_id,product_name,quantity,unit,purchase_price,
                           document_unit,ea_per_document_unit,created_at
                       ) VALUES (?,?,?,?,?,?,?,?)''',
                    (
                        case_id, product_name, quantity, unit, purchase_price,
                        unit, ea_per_document_unit, now,
                    ),
                )
                order_id = int(cursor.lastrowid)
                seen_ids.add(order_id)
                conn.execute(
                    '''INSERT INTO purchase_price_history(
                           case_id,order_item_id,product_name,normalized_name,purchase_price,quantity,unit,created_at
                       ) VALUES (?,?,?,?,?,?,?,?)''',
                    (
                        case_id,
                        order_id,
                        product_name,
                        normalize_product_name(product_name),
                        purchase_price,
                        quantity,
                        unit,
                        now,
                    ),
                )

        removed_ids = [order_id for order_id in existing if order_id not in seen_ids]
        for order_id in removed_ids:
            conn.execute('DELETE FROM order_items WHERE id=? AND case_id=?', (order_id, case_id))

        conn.execute('UPDATE export_cases SET updated_at=? WHERE id=?', (now, case_id))

    db.backup_to_usb()
    clear_editable_cases_cache()
