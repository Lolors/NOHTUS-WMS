from __future__ import annotations

from difflib import SequenceMatcher

import pandas as pd

from nohtus.export_app.services import order_service


PRODUCT_NAME_WARNING_THRESHOLD = 0.45


def safe_number(value: object) -> float:
    try:
        if value is None or pd.isna(value) or value == '':
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def order_state(order_qty: float, linked_qty: float) -> tuple[str, str]:
    if order_qty > 0 and linked_qty >= order_qty:
        return '🟢', '입고 완료'
    if linked_qty > 0:
        return '🟡', '일부 입고'
    return '🔴', '미입고'


def sort_orders_for_intake(orders: list, linked_rows_by_order: dict[int, list]) -> list:
    def sort_key(order) -> tuple[int, str]:
        order_id = int(order['id'])
        ordered_qty = safe_number(order['quantity'])
        received_qty = sum(
            safe_number(row['requested_qty'])
            for row in linked_rows_by_order.get(order_id, [])
        )
        is_completed = ordered_qty > 0 and received_qty + 0.000001 >= ordered_qty
        product_name = order_service.normalize_product_name(order['product_name'])
        return (1 if is_completed else 0, product_name)

    return sorted(orders, key=sort_key)


def product_name_similarity(order_name: str, actual_name: str) -> float:
    normalized_order = order_service.normalize_product_name(order_name)
    normalized_actual = order_service.normalize_product_name(actual_name)
    if not normalized_order or not normalized_actual:
        return 0.0
    if normalized_order == normalized_actual:
        return 1.0
    if normalized_order in normalized_actual or normalized_actual in normalized_order:
        return 0.92
    return SequenceMatcher(None, normalized_order, normalized_actual).ratio()


def find_product_name_mismatches(
    order_name: str,
    values: list[dict],
    *,
    threshold: float = PRODUCT_NAME_WARNING_THRESHOLD,
) -> list[dict]:
    mismatches = []
    for index, value in enumerate(values, start=1):
        actual_name = str(value.get('product_name', '') or '').strip()
        if not actual_name:
            continue
        similarity = product_name_similarity(order_name, actual_name)
        if similarity < threshold:
            mismatches.append({
                '행': index,
                '주문 제품명': order_name,
                '입력 제품명': actual_name,
                '유사도': f'{similarity * 100:.0f}%',
            })
    return mismatches


def intake_progress(orders: list, linked_rows_by_order: dict[int, list]) -> dict:
    ratios: list[float] = []
    completed_count = 0

    for order in orders:
        order_id = int(order['id'])
        ordered_qty = safe_number(order['quantity'])
        received_qty = sum(
            safe_number(row['requested_qty'])
            for row in linked_rows_by_order.get(order_id, [])
        )
        if ordered_qty <= 0:
            ratios.append(0.0)
            continue

        ratios.append(min(received_qty / ordered_qty, 1.0))
        if received_qty + 0.000001 >= ordered_qty:
            completed_count += 1

    item_count = len(ratios)
    ratio = sum(ratios) / item_count if item_count else 0.0
    return {
        'ratio': ratio,
        'completed_count': completed_count,
        'item_count': item_count,
        'all_received': item_count > 0 and completed_count == item_count,
    }
