from __future__ import annotations

import re
import unicodedata


def packing_summary(items: list) -> dict:
    unpacked_count = sum(1 for item in items if item['box_no'] is None)
    packed_count = len(items) - unpacked_count
    box_count = len({item['box_no'] for item in items if item['box_no'] is not None})
    total_quantity = sum(float(item['requested_qty'] or 0) for item in items)
    return {
        'row_count': len(items),
        'total_quantity': total_quantity,
        'packed_count': packed_count,
        'unpacked_count': unpacked_count,
        'box_count': box_count,
    }


def normalize_product_name(value: object) -> str:
    text = unicodedata.normalize('NFKC', str(value or ''))
    text = text.replace('\u200b', '').replace('\ufeff', '')
    return re.sub(r'\s+', ' ', text).strip().casefold()


def filter_packing_items(
    items: list,
    *,
    query: str = '',
    business_unit: str = '전체',
    lot_query: str = '',
    unpacked_only: bool = True,
) -> list:
    normalized_query = normalize_product_name(query)
    normalized_lot = str(lot_query or '').strip().casefold()
    filtered = []
    for item in items:
        if unpacked_only and item['box_no'] is not None:
            continue
        if business_unit != '전체' and str(item['business_unit'] or '').strip() != business_unit:
            continue
        if normalized_query and normalized_query not in normalize_product_name(item['product_name']):
            continue
        if normalized_lot and normalized_lot not in str(item['lot_no'] or '').strip().casefold():
            continue
        filtered.append(item)
    return filtered


def expand_same_product_selection(items: list, selected_ids: list[int]) -> list[int]:
    selected_set = {int(item_id) for item_id in selected_ids}
    selected_names = {
        normalize_product_name(item['product_name'])
        for item in items
        if int(item['id']) in selected_set
    }
    if not selected_names:
        return sorted(selected_set)
    return sorted({
        int(item['id'])
        for item in items
        if normalize_product_name(item['product_name']) in selected_names
    })


def items_by_box(items: list) -> dict[int, list]:
    grouped: dict[int, list] = {}
    for item in items:
        if item['box_no'] is None:
            continue
        grouped.setdefault(int(item['box_no']), []).append(item)
    return grouped


def product_summary(items: list, *, visible_count: int = 2) -> str:
    names: list[str] = []
    for item in items:
        name = str(item['product_name'] or '').strip()
        if name and name not in names:
            names.append(name)
    if not names:
        return '-'
    result = ', '.join(names[:visible_count])
    remaining = len(names) - visible_count
    return f'{result} 외 {remaining}품목' if remaining > 0 else result
