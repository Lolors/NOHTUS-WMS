from __future__ import annotations

import re
from datetime import date, timedelta

from nohtus.export_app.utils.formatters import fmt_number


STAGE_LABELS = {
    '주문 접수': '주문 접수',
    '주문 입력': '주문 접수',
    '제품 준비': '제품 준비',
    '실출고 입력': '출고 대기',
    '출고 대기': '출고 대기',
    '패킹': '패킹',
    '박스 패킹': '패킹',
    '패킹 진행': '패킹 진행',
    '패킹 대기': '패킹 대기',
    '패킹 완료': '패킹 완료',
    '국내배송': '국내배송',
    '선적 준비': '선적 준비',
    '선적 완료': '선적 완료',
    '완료': '완료',
    '취소': '주문 취소',
    '주문 취소': '주문 취소',
}

STAGE_SORT_ORDER = {
    '패킹 완료': 0,
    '패킹 대기': 1,
    '입고 진행': 2,
    '제품 준비': 2,
    '출고 대기': 2,
    '주문 접수': 3,
    '주문 입력': 3,
    '국내배송': 99,
}


def display_stage(value: object) -> str:
    stage = str(value or '').strip()
    return STAGE_LABELS.get(stage, stage or '-')


def summarize_product_names(raw_names: object) -> str:
    names = [name.strip() for name in re.split(r'[,\n]+', str(raw_names or '')) if name.strip()]
    if len(names) <= 2:
        return ', '.join(names)
    return f"{', '.join(names[:2])} 외 {len(names) - 2}품목"


def quantity_with_unit(row) -> str:
    quantity = fmt_number(row['requested_qty'])
    try:
        unit = str(row['unit'] or '').strip()
    except (KeyError, IndexError):
        unit = ''
    return f'{quantity} {unit}'.strip()


def shipment_date(case) -> str:
    return str(case['actual_ship_date'] or '').strip()


def default_document_period(reference: date | None = None) -> tuple[date, date]:
    """최근 출고 건과, 며칠 뒤로 잡힌 국내배송 예정 건까지 기본 조회기간에 포함한다.

    출고일을 오늘 이후 날짜로 입력한 건(예: 국내배송 예정일)이 예전엔 기본
    조회기간(오늘까지)에서 통째로 빠져서, 저장은 멀쩡히 됐는데 화면에서
    사라진 것처럼 보이는 혼란을 일으켰다."""
    today = reference or date.today()
    return today - timedelta(days=7), today + timedelta(days=7)


def filter_and_sort_cases(
    cases,
    *,
    start_date: date,
    end_date: date,
    selected_country: str,
    product_query: str,
):
    filtered = []
    for case in cases:
        raw_date = shipment_date(case)
        if raw_date:
            try:
                case_date = date.fromisoformat(raw_date[:10])
            except ValueError:
                case_date = None
            if case_date is not None and not start_date <= case_date <= end_date:
                continue
        if selected_country != '전체' and str(case['country']).strip() != selected_country:
            continue
        if product_query and product_query not in str(case['product_names'] or '').casefold():
            continue
        filtered.append(case)
    return sorted(
        filtered,
        key=lambda case: STAGE_SORT_ORDER.get(str(case['stage'] or '').strip(), 90),
    )


def format_case_option(case) -> str:
    country = str(case['country'] or '').strip() or '국가 미입력'
    buyer = str(case['buyer'] or '').strip() or '바이어 미입력'
    transport_mode = str(case['transport_mode'] or '').strip() or '운송방식 미입력'
    export_no = str(case['export_no'] or '').strip() or '수출번호 미입력'
    products = summarize_product_names(case['product_names'])
    return f'{country} · {buyer} · {transport_mode} · {export_no} · {products}'
