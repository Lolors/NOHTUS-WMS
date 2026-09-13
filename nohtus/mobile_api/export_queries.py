"""모바일 수출 현황 API가 사용하는 조회 전용 함수.

데스크톱과 같은 원본 데이터(order_service.list_editable_cases 등)를 쓰지만
모바일 전용 규칙으로 나눈다:
  - 진행중: 아직 "국내배송" 단계까지 가지 않은 건. 필터(국가/운송방식)는
    적용하지만 기간 필터는 적용하지 않는다 — 언제 등록됐든 아직 안 끝난
    건은 항상 보여준다.
  - 완료: "국내배송" 단계까지 간 건. 기간 필터로 셋 중 하나를 고른다.
      * 최근: 최근 2주 이내에 선적된 건만 바로 목록으로.
      * 월별: 월별 건수 요약 카드 → 카드를 누르면 그 달의 전체 목록.
      * 연도별: 연도별 건수 요약 카드 → 카드를 누르면 그 해의 전체 목록.
"""

from __future__ import annotations

from datetime import date, timedelta

from nohtus.export_app.services import dashboard_view_service as dash
from nohtus.export_app.services import export_service, order_service

RECENT_DAYS = 14
TRANSPORT_ICONS = {"AIR": "✈️", "SEA": "🚢", "HAND": "✋"}
_MONTH_NAMES_KO = "1월 2월 3월 4월 5월 6월 7월 8월 9월 10월 11월 12월".split()

_is_completed_stage = dash.is_completed_stage
_overall_progress_percent = dash.overall_progress_percent


def _parse_date(value):
    try:
        return date.fromisoformat(str(value or "").strip()[:10])
    except ValueError:
        return None


def _reference_date(case):
    return _parse_date(case["actual_ship_date"]) or _parse_date(case["created_at"])


def _filtered_cases(country=None, transport=None):
    cases = order_service.list_editable_cases()
    country = (country or "").strip()
    transport = (transport or "").strip()
    if country:
        cases = [case for case in cases if str(case["country"] or "").strip() == country]
    if transport:
        cases = [case for case in cases if str(case["transport_mode"] or "").strip() == transport]
    return cases


def _serialize_case(case, intake, sales_status):
    stage = dash.stage_label(case["stage"])
    bg, fg, _ = dash.stage_bar_colors(case["stage"])
    export_no = str(case["export_no"] or "").strip()
    transport_mode = str(case["transport_mode"] or "").strip()
    intake_percent = intake.get(int(case["id"]), 0.0)
    case_sales_status = sales_status.get(export_no, "미등록")
    return {
        "id": int(case["id"]),
        "export_no": export_no,
        "created_date": str(case["created_at"] or "").strip()[:10],
        "confirmed_date": str(case["actual_ship_date"] or "").strip()[:10],
        "buyer": str(case["buyer"] or ""),
        "country": str(case["country"] or ""),
        "transport_mode": transport_mode,
        "transport_icon": TRANSPORT_ICONS.get(transport_mode, ""),
        "stage": stage,
        "stage_bg": bg,
        "stage_fg": fg,
        "progress_percent": _overall_progress_percent(case, intake_percent, case_sales_status),
        "sales_status": case_sales_status,
        "products_summary": dash.summarize_product_names(case["product_names"]),
        "note": str(case["note"] or ""),
    }


def _serialize_all(cases):
    case_ids = [int(case["id"]) for case in cases]
    intake = dash.intake_progress_percentages(case_ids)
    export_numbers = [case["export_no"] for case in cases]
    sales_status = dash.sales_registration_statuses(export_numbers)
    return [_serialize_case(case, intake, sales_status) for case in cases]


def available_countries():
    cases = order_service.list_editable_cases()
    countries = {str(case["country"] or "").strip() for case in cases if str(case["country"] or "").strip()}
    return sorted(countries)


def export_dashboard(country=None, transport=None, period="recent"):
    cases = _filtered_cases(country, transport)
    in_progress = [case for case in cases if not _is_completed_stage(case)]
    completed = [case for case in cases if _is_completed_stage(case)]

    in_progress.sort(
        key=lambda case: (
            dash.STAGE_ORDER.get(dash.stage_label(case["stage"]), len(dash.STAGE_ORDER)),
            str(case["created_at"] or ""),
            int(case["id"]),
        )
    )

    result = {"in_progress": _serialize_all(in_progress)}

    if period == "monthly":
        month_counts: dict[tuple[int, int], int] = {}
        for case in completed:
            ref_date = _reference_date(case)
            if not ref_date:
                continue
            key = (ref_date.year, ref_date.month)
            month_counts[key] = month_counts.get(key, 0) + 1
        result["completed_mode"] = "months"
        result["completed_months"] = [
            {"year": year, "month": month, "label": _MONTH_NAMES_KO[month - 1], "count": count}
            for (year, month), count in sorted(month_counts.items(), reverse=True)
        ]
    elif period == "yearly":
        year_counts: dict[int, int] = {}
        for case in completed:
            ref_date = _reference_date(case)
            if not ref_date:
                continue
            year_counts[ref_date.year] = year_counts.get(ref_date.year, 0) + 1
        result["completed_mode"] = "years"
        result["completed_years"] = [
            {"year": year, "count": count}
            for year, count in sorted(year_counts.items(), reverse=True)
        ]
    else:
        cutoff = date.today() - timedelta(days=RECENT_DAYS)
        recent = [case for case in completed if (_reference_date(case) or date.min) >= cutoff]
        recent.sort(key=lambda case: _reference_date(case) or date.min, reverse=True)
        result["completed_mode"] = "list"
        result["completed_cases"] = _serialize_all(recent)

    return result


def export_year_cases(year, country=None, transport=None):
    cases = _filtered_cases(country, transport)
    completed = [case for case in cases if _is_completed_stage(case)]
    matched = [
        case
        for case in completed
        if (_reference_date(case) or date.min).year == int(year)
    ]
    matched.sort(key=lambda case: _reference_date(case) or date.min, reverse=True)
    return _serialize_all(matched)


def export_month_cases(year, month, country=None, transport=None):
    cases = _filtered_cases(country, transport)
    completed = [case for case in cases if _is_completed_stage(case)]
    matched = []
    for case in completed:
        ref_date = _reference_date(case)
        if ref_date and ref_date.year == int(year) and ref_date.month == int(month):
            matched.append(case)
    matched.sort(key=lambda case: _reference_date(case) or date.min, reverse=True)
    return _serialize_all(matched)


def _intake_status(quantity, actual_qty):
    quantity = float(quantity or 0)
    actual_qty = float(actual_qty or 0)
    if actual_qty <= 0:
        return "미입고"
    if actual_qty >= quantity:
        return "입고완료"
    return "부분입고"


def case_order_items(case_id):
    rows = export_service.get_order_items_with_actual(int(case_id))
    items = []
    for index, row in enumerate(rows, start=1):
        items.append(
            {
                "no": index,
                "product_name": str(row["product_name"] or ""),
                "quantity": row["quantity"],
                "unit": str(row["unit"] or ""),
                "intake_status": _intake_status(row["quantity"], row["actual_qty"]),
            }
        )
    return items
