from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta

from nohtus.export_app import db
from nohtus.export_app.services import export_confirm_service, export_service, order_service


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


def is_completed_stage(case: dict) -> bool:
    """실제 운영 기준 마지막 단계(국내배송)에 도달했는지."""
    order = STAGE_ORDER.get(stage_label(case['stage']), -1)
    return order >= STAGE_ORDER['국내배송']


_SALES_REGISTERED_BONUS = 10
_INTAKE_START_PERCENT = 1
_INTAKE_DONE_PERCENT = 60
# 입고가 끝난 뒤부터는 패킹 단계마다 10%씩 깔끔하게 올라간다:
# 패킹대기 60 → 패킹진행 70 → 패킹완료 80 → 국내배송 90(매출등록 전) → 100(매출등록 후).
_PACKING_STAGE_PERCENTS = {4: 60, 5: 70, 6: 80}
_STAGE_PROGRESS_CAP = 90


def overall_progress_percent(case: dict, intake_percent: float, sales_status: str) -> float:
    """전체 진행률(0~100).

    - 주문 접수 ~ 아직 입고가 시작되지 않은 상태: 0%.
    - "입고 진행" 단계: 입고된 수량 비율에 따라 1%(막 시작)에서 60%(입고
      완료)까지 정수로 오른다.
    - 패킹 단계(대기/진행/완료): 60% → 70% → 80%로 10%씩 깔끔하게 오른다.
    - "국내배송" 단계에 도달하면 90%. 매출 등록까지 완료돼야(등록완료)
      비로소 100%가 된다.
    - 어느 단계든 입고가 시작된 뒤라면, 매출 등록이 먼저 끝나 있으면
      그만큼 진척된 거니까 +10%를 더해준다(같은 단계라도 매출 등록완료
      건이 미등록 건보다 진행률이 높게 보이도록).
    """
    final_stage_order = STAGE_ORDER['국내배송']
    intake_stage_order = STAGE_ORDER['입고 진행']
    stage_order = STAGE_ORDER.get(stage_label(case['stage']), 0)
    registered = sales_status == '등록완료'

    if stage_order >= final_stage_order:
        return 100.0 if registered else float(_STAGE_PROGRESS_CAP)

    if stage_order >= intake_stage_order + 1:
        base = float(_PACKING_STAGE_PERCENTS.get(stage_order, _INTAKE_DONE_PERCENT))
    elif stage_order == intake_stage_order:
        intake_ratio = max(0.0, min(1.0, float(intake_percent or 0.0) / 100.0))
        if intake_ratio <= 0.0:
            base = 0.0
        else:
            span = _INTAKE_DONE_PERCENT - _INTAKE_START_PERCENT
            base = float(round(_INTAKE_START_PERCENT + span * intake_ratio))
    else:
        base = 0.0

    if registered and base > 0.0:
        return min(base + _SALES_REGISTERED_BONUS, float(_STAGE_PROGRESS_CAP))
    return base


def active_and_recent_cases(*, reference: date | None = None, recent_days: int = 7) -> list[dict]:
    """Cases still in progress (stage not yet 국내배송), plus 국내배송 cases
    whose actual_ship_date falls within the last `recent_days` days.

    과거 이력으로 등록된(case_type='historical') 건도 모바일 수출현황과
    동일하게 포함한다 — 예전엔 여기서만 숨겨져 있었다."""
    reference_date = reference or date.today()
    cutoff = reference_date - timedelta(days=recent_days)
    cases = []
    for case in order_service.list_editable_cases():
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
                   SUM(
                       o.quantity * CASE
                         WHEN COALESCE(o.ea_per_document_unit, 0) > 0 THEN o.ea_per_document_unit
                         ELSE 1
                       END
                   ) AS ordered_qty,
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


def sales_registration_statuses(export_numbers: list[object]) -> dict[str, str]:
    """Return the sales-registration state shown by the confirmation screen.

    A missing/waiting WMS link has no confirmed sales, a partial link (or a
    mixture of confirmed and waiting duplicate links) is in progress, and only
    export numbers whose every active link is confirmed are complete.
    """
    requested = {
        str(export_no or '').strip()
        for export_no in export_numbers
        if str(export_no or '').strip()
    }
    result = {export_no: '미등록' for export_no in requested}
    if not requested:
        return result

    orders = export_confirm_service.list_active_orders()
    if orders.empty:
        return result

    matched = orders.copy()
    matched['_export_no'] = matched['export_no'].fillna('').astype(str).str.strip()
    matched = matched[matched['_export_no'].isin(requested)]
    for export_no, rows in matched.groupby('_export_no', sort=False):
        statuses = {str(value or '').strip() for value in rows['status']}
        if statuses and statuses == {'confirmed'}:
            result[export_no] = '등록완료'
        elif 'confirmed' in statuses or 'partial' in statuses:
            result[export_no] = '등록중'
    return result
