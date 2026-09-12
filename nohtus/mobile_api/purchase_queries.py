"""모바일 매입가 조회 API가 사용하는 조회 전용 함수.

데스크톱의 nohtus/pages/purchase_history_all_products.py(현재 제품마스터 +
과거 매입 DB의 모든 제품명을 함께 검색하는 버전, purchase_history_single.py가
실제로 라우팅하는 것도 이 검색 로직)의 순수 함수를 그대로 재사용한다.
업로드/가져오기 기능은 데스크톱 전용 관리 작업이라 모바일에는 넣지 않는다.
"""

from __future__ import annotations

from datetime import date, timedelta

import nohtus.pages.purchase_history as purchase_page
import nohtus.pages.purchase_history_all_products as purchase_all
from nohtus.services.expiry_rules import PERIOD_DAYS

_EARLIEST_DATE = "2000-01-01"


def period_range(period="1y"):
    end = date.today()
    if period in PERIOD_DAYS:
        start = end - timedelta(days=PERIOD_DAYS[period])
        return start.isoformat(), end.isoformat()
    return _EARLIEST_DATE, end.isoformat()


def product_candidates(term, limit=20):
    term = (term or "").strip().lower()
    if not term:
        return []
    options = purchase_all._all_purchase_product_options()
    matched = [name for name in options if term in name.lower()]
    matched.sort(key=lambda name: (not name.lower().startswith(term), name))
    return matched[:limit]


def _rows_for(product_name, start_date, end_date):
    df = purchase_all._query_all_purchase_rows("", product_name, start_date, end_date)
    return df


def search_products(term, period="1y", limit=20):
    start_date, end_date = period_range(period)
    candidates = product_candidates(term, limit=max(limit * 3, 60))
    results = []
    for name in candidates:
        df = _rows_for(name, start_date, end_date)
        if df.empty:
            continue
        latest = df.iloc[0]
        results.append(
            {
                "name": name,
                "count": int(len(df)),
                "latest_date": str(latest.get("purchase_date") or ""),
                "latest_price": _to_number(latest.get("unit_price")),
            }
        )
        if len(results) >= limit:
            break
    results.sort(key=lambda item: item["latest_date"], reverse=True)
    return results


def product_detail(product_name, period="1y"):
    start_date, end_date = period_range(period)
    df = _rows_for(product_name, start_date, end_date)
    rows = []
    for row in df.itertuples(index=False):
        rows.append(
            {
                "business_name": str(getattr(row, "business_name", "") or ""),
                "purchase_date": str(getattr(row, "purchase_date", "") or ""),
                "supplier_name": str(getattr(row, "supplier_name", "") or ""),
                "specification": str(getattr(row, "specification", "") or ""),
                "quantity": _to_number(getattr(row, "quantity", 0)),
                "unit_price": _to_number(getattr(row, "unit_price", 0)),
                "note": str(getattr(row, "note", "") or ""),
            }
        )
    return {"name": product_name, "rows": rows}


def _to_number(value):
    try:
        num = float(value)
    except (TypeError, ValueError):
        return 0
    return int(num) if num == int(num) else num
