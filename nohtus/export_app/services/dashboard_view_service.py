from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta

from nohtus.export_app import db
from nohtus.export_app.services import export_service, order_service


STAGE_LABELS = {
    '출고 대기': '패킹 대기',
}

STAGE_COLORS = {
    '주문 접수': 'background-color: #eef1f5; color: #46505f; font-weight: 700;',
    '제품 준비': 'background-color: #fff2cc; color: #7a5a00; font-weight: 700;',
    '패킹 대기': 'background-color: #dff3ff; color: #075f85; font-weight: 700;',
    '패킹 진행': 'background-color: #e8f0ff; color: #315d9b; font-weight: 700;',
    '패킹 완료': 'background-color: #e7e0ff; color: #5637a5; font-weight: 700;',
    '국내배송': 'background-color: #ffe7d6; color: #9a4b0b; font-weight: 700;',
    '선적 준비': 'background-color: #dff5f2; color: #14685f; font-weight: 700;',
    '선적 완료': 'background-color: #dcecff; color: #174f8f; font-weight: 700;',
    '완료': 'background-color: #dff5e7; color: #17683a; font-weight: 700;',
}

STAGE_BAR_COLORS = {
    '주문 접수': ('#6b7280', '#ffffff', '#4b5563'),
    '제품 준비': ('#eab308', '#3f3200', '#ca8a04'),
    '패킹 대기': ('#38bdf8', '#063d55', '#0284c7'),
    '패킹 진행': ('#60a5fa', '#102f62', '#2563eb'),
    '패킹 완료': ('#8b5cf6', '#ffffff', '#6d28d9'),
    '국내배송': ('#fb923c', '#4f2605', '#ea580c'),
    '선적 준비': ('#2dd4bf', '#073f39', '#0d9488'),
    '선적 완료': ('#3b82f6', '#ffffff', '#1d4ed8'),
    '완료': ('#22c55e', '#073b1b', '#16a34a'),
}

STAGE_ORDER = {
    '주문 접수': 0,
    '제품 준비': 1,
    '출고 대기': 2,
    '입고 진행': 3,
    '패킹 대기': 4,
    '패킹 진행': 5,
    '패킹 완료': 6,
    '국내배송': 7,
    '선적 준비': 8,
    '선적 완료': 9,
    '완료': 10,
}



def _recent_month_prefixes(reference: datetime, month_count: int) -> list[str]:
    prefixes: list[str] = []
    year = reference.year
    month = reference.month
    for _ in range(max(1, month_count)):
        prefixes.append(f'{year:04d}-{month:02d}')
        month -= 1
        if month == 0:
            year -= 1
            month = 12
    return prefixes


def recent_order_cases(
    cases: list,
    *,
    reference: datetime | None = None,
    month_count: int = 2,
) -> list:
    reference_date = (reference or datetime.now()).date()
    cutoff = _months_before(reference_date, month_count)
    return [
        case
        for case in cases
        if cutoff <= _parse_case_date(case['created_at']) <= reference_date
    ]


def _months_before(reference_date: date, month_count: int) -> date:
    target_month = reference_date.month - max(1, month_count)
    target_year = reference_date.year
    while target_month <= 0:
        target_year -= 1
        target_month += 12
    return date(
        target_year,
        target_month,
        min(reference_date.day, monthrange(target_year, target_month)[1]),
    )


def _parse_case_date(value: object) -> date:
    try:
        return date.fromisoformat(str(value or '').strip()[:10])
    except ValueError:
        return date.min


def timeline_date(case) -> str:
    """Return the date used to place an order on the dashboard timeline."""
    export_no = str(case['export_no'] or '').strip().upper()
    actual_ship_date = str(case['actual_ship_date'] or '').strip()[:10]
    created_at = str(case['created_at'] or '').strip()[:10]
    if export_no.startswith('HIS') and actual_ship_date:
        return actual_ship_date
    return created_at


def timeline_period(case) -> tuple[str, str]:
    """Return the start/end dates used by the dashboard Gantt bar.

    Historical imports represent an already-finished shipment, so their
    registration date is not part of the visual duration.  They are shown as
    a one-day bar on the actual shipment date instead.
    """
    export_no = str(case['export_no'] or '').strip().upper()
    actual_ship_date = str(case['actual_ship_date'] or '').strip()[:10]
    created_at = str(case['created_at'] or '').strip()[:10]
    if export_no.startswith('HIS') and actual_ship_date:
        return actual_ship_date, actual_ship_date
    return created_at, actual_ship_date


def timeline_date_label(value: object) -> str:
    raw = str(value or '').strip()[:10]
    try:
        parsed = date.fromisoformat(raw)
    except ValueError:
        return raw or '날짜 미입력'
    return f'{parsed.month}월 {parsed.day}일'


def timeline_bounds(rows: list[dict], *, today: date | None = None) -> tuple[date, date]:
    """Return an axis that includes every order, today, and two weeks of breathing room."""
    reference = today or date.today()
    parsed_dates: list[date] = []
    for row in rows:
        for field in ('start_date', 'end_date'):
            raw = str(row.get(field) or '').strip()[:10]
            try:
                parsed_dates.append(date.fromisoformat(raw))
            except ValueError:
                continue
    earliest = min(parsed_dates, default=reference)
    latest = max(parsed_dates, default=reference)
    return min(earliest, reference) - timedelta(days=14), max(latest, reference) + timedelta(days=14)


def recent_order_period_label(
    *,
    reference: datetime | None = None,
    month_count: int = 2,
) -> str:
    reference_date = (reference or datetime.now()).date()
    cutoff = _months_before(reference_date, month_count)
    return f'{cutoff.isoformat()}~{reference_date.isoformat()}'

def stage_label(value: object) -> str:
    stage = str(value or '').strip()
    return STAGE_LABELS.get(stage, stage)


def stage_style(value: object) -> str:
    return STAGE_COLORS.get(
        str(value or '').strip(),
        'background-color: #f3f4f6; color: #555; font-weight: 700;',
    )


def stage_bar_colors(value: object) -> tuple[str, str, str]:
    """Return background, text, and accent colors for a timeline stage."""
    stage = stage_label(value)
    return STAGE_BAR_COLORS.get(stage, ('#94a3b8', '#1f2937', '#64748b'))


def order_products_summary(case_id: int) -> str:
    product_names = [
        str(item['product_name'] or '').strip()
        for item in export_service.get_order_items(case_id)
        if str(item['product_name'] or '').strip()
    ]
    if not product_names:
        return '-'

    visible_names = product_names[:2]
    summary = ', '.join(visible_names)
    remaining_count = len(product_names) - len(visible_names)
    if remaining_count > 0:
        summary += f' + 그 외 {remaining_count}품목'
    return summary


def order_products_detail(case_id: int) -> str:
    lines = []
    for item in export_service.get_order_items(case_id):
        name = str(item['product_name'] or '').strip()
        if not name:
            continue
        quantity = float(item['quantity'] or 0)
        quantity_text = f'{quantity:g}'
        unit = str(item['unit'] or '').strip()
        lines.append(f'{name} · {quantity_text}{unit}')
    return '\n'.join(lines) or '주문목록 없음'


def summarize_product_names(value: object) -> str:
    """Same shortening rule as order_products_summary, but from an already
    fetched GROUP_CONCAT string so the dashboard doesn't need a query per case."""
    names = [name.strip() for name in str(value or '').split(',') if name.strip()]
    if not names:
        return '-'
    visible_names = names[:2]
    summary = ', '.join(visible_names)
    remaining_count = len(names) - len(visible_names)
    if remaining_count > 0:
        summary += f' + 그 외 {remaining_count}품목'
    return summary


def active_and_recent_cases(*, reference: date | None = None, recent_days: int = 7) -> list[dict]:
    """Cases still in progress (stage not yet 국내배송), plus 국내배송 cases
    whose actual_ship_date falls within the last `recent_days` days."""
    reference_date = reference or date.today()
    cutoff = reference_date - timedelta(days=recent_days)
    cases = []
    for case in order_service.list_editable_cases():
        if str(case['case_type'] or '') == 'historical':
            continue
        stage = str(case['stage'] or '').strip()
        if stage != '국내배송':
            cases.append(case)
            continue
        if _parse_case_date(case['actual_ship_date']) >= cutoff:
            cases.append(case)
    return sorted(
        cases,
        key=lambda case: (
            STAGE_ORDER.get(str(case['stage'] or '').strip(), len(STAGE_ORDER)),
            str(case['created_at'] or ''),
            int(case['id']),
        ),
    )


def intake_progress_percentages(case_ids: list[int]) -> dict[int, float]:
    """Bulk 실제 수출대기 입고 수량 / 주문목록 총 수량 ratio per case, as a 0-100 percentage."""
    ids = sorted({int(case_id) for case_id in case_ids})
    if not ids:
        return {}
    placeholders = ','.join('?' for _ in ids)
    rows = db.rows(
        f'''SELECT o.case_id AS case_id,
                   SUM(o.quantity) AS ordered_qty,
                   COALESCE(SUM(r.received_qty), 0) AS received_qty
            FROM order_items o
            LEFT JOIN (
                SELECT order_item_id, SUM(requested_qty) AS received_qty
                FROM shipment_items
                GROUP BY order_item_id
            ) r ON r.order_item_id = o.id
            WHERE o.case_id IN ({placeholders})
            GROUP BY o.case_id''',
        tuple(ids),
    )
    result: dict[int, float] = {}
    for row in rows:
        ordered_qty = float(row['ordered_qty'] or 0)
        received_qty = float(row['received_qty'] or 0)
        result[int(row['case_id'])] = min(100.0, received_qty / ordered_qty * 100.0) if ordered_qty > 0 else 0.0
    return result
