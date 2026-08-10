from __future__ import annotations

from datetime import date

import pandas as pd

from nohtus.export_app import db
from nohtus.export_app.services import order_service
from nohtus.export_app.utils.dates import now_text, parse_date


def text_value(value, default=''):
    if value is None or pd.isna(value):
        return default
    result = str(value).strip()
    return default if result.casefold() in {'nan', 'none', '<na>'} else result


def number_value(value, default=0.0):
    if value is None or pd.isna(value) or value == '':
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def integer_value(value, default=0):
    return int(number_value(value, default))


def date_value(value):
    parsed = parse_date(value)
    return parsed.date() if parsed else date.today()


def optional_date_value(value):
    parsed = parse_date(value)
    return parsed.date() if parsed else None


def historical_items(case_id):
    rows = db.rows('''SELECT o.id _order_id,s.id _shipment_id,
        COALESCE(NULLIF(TRIM(s.business_unit),''),NULLIF(TRIM(s.location),''),'') 출고처,
        o.product_name 제품명,COALESCE(s.lot_no,'') 제조번호,COALESCE(s.expiry_date,'') 유효기간,
        o.quantity 수량,o.unit 단위,o.purchase_price 매입가,COALESCE(s.box_no,1) "CTN 번호"
        FROM order_items o LEFT JOIN shipment_items s ON s.order_item_id=o.id AND s.case_id=o.case_id
        WHERE o.case_id=? ORDER BY o.id,s.id''', (case_id,))
    if rows:
        return pd.DataFrame([dict(row) for row in rows])
    return pd.DataFrame([{'_order_id': None, '_shipment_id': None, '출고처': '', '제품명': '',
        '제조번호': '', '유효기간': '', '수량': 0.0, '단위': 'EA', '매입가': 0.0, 'CTN 번호': 1}])


def box_items(case_id):
    rows = db.rows('''SELECT box_no "CTN 번호",length_cm "가로 (cm)",width_cm "세로 (cm)",
        height_cm "높이 (cm)",weight_kg "GW (kg)" FROM boxes WHERE case_id=? ORDER BY box_no''', (case_id,))
    return pd.DataFrame([dict(row) for row in rows]) if rows else pd.DataFrame([
        {'CTN 번호': 1, '가로 (cm)': 0.0, '세로 (cm)': 0.0, '높이 (cm)': 0.0, 'GW (kg)': 0.0}])


def save_historical(case_id, edited, boxes, basic, delivery):
    items = []
    for _, row in edited.iterrows():
        name = text_value(row.get('제품명'))
        if not name:
            continue
        items.append({
            'oid': integer_value(row.get('_order_id')),
            'sid': integer_value(row.get('_shipment_id')),
            'loc': text_value(row.get('출고처')),
            'name': name,
            'lot': text_value(row.get('제조번호')),
            'exp': text_value(row.get('유효기간')),
            'qty': number_value(row.get('수량')),
            'unit': text_value(row.get('단위'), 'EA') or 'EA',
            'price': number_value(row.get('매입가')),
            'box': integer_value(row.get('CTN 번호')),
        })
    if not items:
        raise ValueError('제품을 한 개 이상 입력하세요.')
    if any(item['box'] <= 0 for item in items):
        raise ValueError('모든 제품에 CTN 번호를 입력하세요.')

    clean_boxes = []
    for _, row in boxes.iterrows():
        box_no = integer_value(row.get('CTN 번호'))
        if box_no > 0:
            clean_boxes.append((box_no, number_value(row.get('가로 (cm)')), number_value(row.get('세로 (cm)')),
                number_value(row.get('높이 (cm)')), number_value(row.get('GW (kg)'))))
    if not clean_boxes:
        raise ValueError('CTN 정보를 한 개 이상 입력하세요.')
    if not {item['box'] for item in items}.issubset({box[0] for box in clean_boxes}):
        raise ValueError('제품에 연결한 모든 CTN 번호의 규격과 GW를 입력하세요.')

    now = now_text()
    with db.connect() as connection:
        old_orders = {int(row['id']): row for row in connection.execute(
            'SELECT id,product_name,purchase_price FROM order_items WHERE case_id=?', (case_id,))}
        old_shipments = {int(row['id']): row for row in connection.execute(
            'SELECT id FROM shipment_items WHERE case_id=?', (case_id,))}
        kept_orders = set()
        kept_shipments = set()
        for item in items:
            order_id = item['oid']
            previous = old_orders.get(order_id)
            if previous:
                connection.execute('UPDATE order_items SET product_name=?,quantity=?,unit=?,purchase_price=? WHERE id=? AND case_id=?',
                    (item['name'], item['qty'], item['unit'], item['price'], order_id, case_id))
            else:
                order_id = connection.execute(
                    'INSERT INTO order_items(case_id,product_name,quantity,unit,purchase_price,created_at) VALUES(?,?,?,?,?,?)',
                    (case_id, item['name'], item['qty'], item['unit'], item['price'], now)).lastrowid
            kept_orders.add(int(order_id))
            if not previous or number_value(previous['purchase_price']) != item['price'] or previous['product_name'] != item['name']:
                connection.execute('''INSERT INTO purchase_price_history(case_id,order_item_id,product_name,normalized_name,
                    purchase_price,quantity,unit,created_at) VALUES(?,?,?,?,?,?,?,?)''',
                    (case_id, order_id, item['name'], order_service.normalize_product_name(item['name']),
                     item['price'], item['qty'], item['unit'], now))
            shipment_id = item['sid']
            if shipment_id in old_shipments:
                connection.execute('''UPDATE shipment_items SET order_item_id=?,business_unit=?,location=?,
                    product_name=?,lot_no=?,expiry_date=?,requested_qty=?,box_no=?,updated_at=?
                    WHERE id=? AND case_id=?''',
                    (
                        order_id, item['loc'], item['loc'], item['name'], item['lot'],
                        item['exp'], item['qty'], item['box'], now, shipment_id, case_id,
                    ))
            else:
                shipment_id = connection.execute('''INSERT INTO shipment_items(case_id,order_item_id,business_unit,location,product_name,
                    lot_no,expiry_date,requested_qty,box_no,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
                    (
                        case_id, order_id, item['loc'], item['loc'], item['name'],
                        item['lot'], item['exp'], item['qty'], item['box'], now, now,
                    )).lastrowid
            kept_shipments.add(int(shipment_id))
        for shipment_id in set(old_shipments) - kept_shipments:
            connection.execute('DELETE FROM shipment_items WHERE id=?', (shipment_id,))
        for order_id in set(old_orders) - kept_orders:
            connection.execute('DELETE FROM order_items WHERE id=?', (order_id,))
        connection.execute('DELETE FROM boxes WHERE case_id=?', (case_id,))
        connection.executemany(
            'INSERT INTO boxes(case_id,box_no,length_cm,width_cm,height_cm,weight_kg,updated_at) VALUES(?,?,?,?,?,?,?)',
            [(case_id, *box, now) for box in clean_boxes],
        )
        connection.execute('''UPDATE export_cases SET country=?,buyer=?,transport_mode=?,note=?,actual_ship_date=?,domestic_method=?,
            tracking_no=?,driver_name=?,driver_phone=?,consignee_name=?,consignee_address=?,stage='국내배송',status='완료',updated_at=? WHERE id=?''',
            (*basic, *delivery, now, case_id))
