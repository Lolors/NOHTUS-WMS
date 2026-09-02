from __future__ import annotations

from nohtus.export_app import db
from nohtus.export_app.services import packing_service, shipment_service


BUSINESS_ORDER = {
    '노투스팜': 0,
    '노투스': 1,
    'NOH': 2,
    '비자료': 3,
}


def _text(value: object) -> str:
    return str(value or '').strip()


def _business_sort_key(value: object) -> tuple[int, str]:
    text = _text(value)
    return BUSINESS_ORDER.get(text, 99), text.casefold()


def _aggregate_actual(rows) -> list[dict]:
    grouped: dict[tuple[str, str, str, str, str], dict] = {}
    for row in rows:
        business = _text(row['business_unit'])
        product = _text(row['product_name'])
        lot = _text(row['lot_no'])
        expiry = _text(row['expiry_date'])
        unit = _text(row['unit'])
        key = (business, product, lot, expiry, unit)
        if key not in grouped:
            grouped[key] = {
                'business_unit': business,
                'product_name': product,
                'lot_no': lot,
                'expiry_date': expiry,
                'unit': unit,
                'requested_qty': 0.0,
            }
        grouped[key]['requested_qty'] += float(row['requested_qty'] or 0)

    return sorted(
        grouped.values(),
        key=lambda row: (
            _text(row['product_name']).casefold(),
            _business_sort_key(row['business_unit']),
            _text(row['lot_no']).casefold(),
            _text(row['expiry_date']),
            _text(row['unit']).casefold(),
        ),
    )


def _build_shipment_product_rows(order_rows, actual_rows) -> list[dict]:
    """Use received details and fill each order's outstanding quantity from the order.

    실제 저장된 재고(actual_rows)의 requested_qty는 항상 EA 단위지만, 주문의
    단위(order['unit'])는 BOX 등 문서 단위일 수 있다. 이 둘을 그대로 섞으면
    "80EA"가 "80BOX"로 잘못 표시된다. ea_per_document_unit으로 EA를 문서
    단위로 환산한 뒤에만 주문 수량과 비교·합산한다."""
    actual_by_order: dict[int, list] = {}
    for row in actual_rows:
        order_item_id = row['order_item_id']
        if order_item_id is None:
            continue
        actual_by_order.setdefault(int(order_item_id), []).append(row)

    combined: list[dict] = []
    for order in order_rows:
        try:
            ea_per_unit = float(order['ea_per_document_unit'] or 1)
        except (KeyError, IndexError, TypeError, ValueError):
            ea_per_unit = 1.0
        if ea_per_unit <= 0:
            ea_per_unit = 1.0

        linked_actual = actual_by_order.get(int(order['id']), [])
        received_quantity = 0.0
        for row in linked_actual:
            quantity = float(row['requested_qty'] or 0)
            if quantity <= 0:
                continue
            converted = dict(row)
            converted['requested_qty'] = quantity / ea_per_unit
            combined.append(converted)
            received_quantity += quantity / ea_per_unit

        outstanding_quantity = max(float(order['quantity'] or 0) - received_quantity, 0.0)
        if outstanding_quantity > 0.000001:
            combined.append({
                'business_unit': '',
                'product_name': _text(order['product_name']),
                'lot_no': '',
                'expiry_date': '',
                'unit': _text(order['unit']),
                'requested_qty': outstanding_quantity,
            })

    return _aggregate_actual(combined)


def get_shipment_product_list_data(case_id: int) -> list[dict]:
    """Return a complete planned-shipment list using the freshest available data."""
    order_rows = db.rows(
        '''SELECT id, product_name, quantity, unit,
                  CASE
                      WHEN COALESCE(ea_per_document_unit, 0) > 0 THEN ea_per_document_unit
                      ELSE 1
                  END AS ea_per_document_unit
           FROM order_items
           WHERE case_id=?
           ORDER BY id''',
        (case_id,),
    )
    actual_rows = shipment_service.list_case_items(case_id)
    return _build_shipment_product_rows(order_rows, actual_rows)


def _aggregate_packed(rows, boxes_by_no: dict[int, object]) -> list[dict]:
    grouped: dict[tuple[int, str, str, str, str, str], dict] = {}
    for row in rows:
        if row['box_no'] is None:
            continue

        box_no = int(row['box_no'])
        business = _text(row['business_unit'])
        product = _text(row['product_name'])
        lot = _text(row['lot_no'])
        expiry = _text(row['expiry_date'])
        unit = _text(row['unit'])
        try:
            ea_per_unit = float(row['ea_per_document_unit'] or 1)
        except (KeyError, IndexError, TypeError, ValueError):
            ea_per_unit = 1.0
        if ea_per_unit <= 0:
            ea_per_unit = 1.0
        key = (box_no, business, product, lot, expiry, unit)
        box = boxes_by_no.get(box_no)

        if key not in grouped:
            grouped[key] = {
                'id': int(row['id']),
                'box_no': box_no,
                'business_unit': business,
                'product_name': product,
                'lot_no': lot,
                'expiry_date': expiry,
                'unit': unit,
                'requested_qty': 0.0,
                'weight_kg': box['weight_kg'] if box else 0,
                'length_cm': box['length_cm'] if box else 0,
                'width_cm': box['width_cm'] if box else 0,
                'height_cm': box['height_cm'] if box else 0,
            }
        grouped[key]['requested_qty'] += float(row['requested_qty'] or 0) / ea_per_unit

    return sorted(
        grouped.values(),
        key=lambda row: (
            int(row['box_no']),
            _business_sort_key(row['business_unit']),
            _text(row['product_name']).casefold(),
            _text(row['lot_no']).casefold(),
            _text(row['expiry_date']),
            _text(row['unit']).casefold(),
        ),
    )


def get_packed_document_data(case_id: int) -> list[dict]:
    packed_rows = db.rows(
        '''SELECT s.id, s.box_no,
                  COALESCE(NULLIF(TRIM(s.business_unit),''), NULLIF(TRIM(s.location),''), '') AS business_unit,
                  s.product_name, s.lot_no, s.expiry_date, s.requested_qty,
                  COALESCE(NULLIF(TRIM(o.document_unit), ''), NULLIF(TRIM(o.unit), ''), 'EA') AS unit,
                  CASE
                    WHEN COALESCE(o.ea_per_document_unit, 0) > 0 THEN o.ea_per_document_unit
                    ELSE 1
                  END AS ea_per_document_unit
           FROM shipment_items s
           JOIN order_items o
             ON o.id=s.order_item_id
            AND o.case_id=s.case_id
           WHERE s.case_id=? AND s.box_no IS NOT NULL
           ORDER BY s.box_no, s.id''',
        (case_id,),
    )
    boxes_by_no = {
        int(box['box_no']): box
        for box in packing_service.list_boxes(case_id)
    }
    return _aggregate_packed(packed_rows, boxes_by_no)


def get_document_data(case_id: int):
    """최종문서 버튼을 누른 경우에만 CTN 및 현재 입고 데이터를 조회한다."""
    packed = get_packed_document_data(case_id)

    current_rows = shipment_service.list_case_items(case_id)
    actual = _aggregate_actual(current_rows)
    return packed, actual
