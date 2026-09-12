"""유통기한 구간/배지 판정 순수 규칙. Streamlit을 import하지 않는다.

데스크톱 페이지들은 각자 다른 모양(한글 라벨 딕셔너리, 문자열 날짜 파싱,
Timestamp 등)으로 이 판정을 따로 구현해왔다. 여기서는 "구간 일수"와
"배지 판정" 두 가지 핵심만 공유하고, 각 화면의 HTML/DataFrame 렌더링은
호출부가 그대로 맡는다.
"""

from __future__ import annotations

from datetime import date, datetime

import pandas as pd

PERIOD_DAYS = {"3m": 90, "6m": 180, "1y": 365}

# 데스크톱 일부 화면은 기간을 한글 라벨로 다룬다 — 숫자는 PERIOD_DAYS와
# 항상 같은 값이어야 하므로 별도로 적지 않고 그대로 파생시킨다.
PERIOD_DAYS_KO = {
    "3개월 이내": PERIOD_DAYS["3m"],
    "6개월 이내": PERIOD_DAYS["6m"],
    "1년 이내": PERIOD_DAYS["1y"],
}


def _badge_for_days(days: int, date_text: str) -> dict:
    if days <= PERIOD_DAYS["3m"]:
        return {"label": "3개월 이내", "level": "red", "date": date_text}
    if days <= PERIOD_DAYS["6m"]:
        return {"label": "6개월 이내", "level": "yellow", "date": date_text}
    return {"label": "1년 이내", "level": "blue", "date": date_text}


def expiry_badge_for(nearest_expiry_ts) -> dict | None:
    """가장 빠른 유통기한(Timestamp)으로 배지 정보를 만든다."""
    if nearest_expiry_ts is None or pd.isna(nearest_expiry_ts):
        return None
    days = int((nearest_expiry_ts.date() - date.today()).days)
    date_text = nearest_expiry_ts.strftime("%Y.%m.%d")
    return _badge_for_days(days, date_text)


def expiry_badge_for_date_text(exp_date_text: str) -> dict | None:
    """"2026-01-01" 류 문자열로 배지 정보를 만든다(여러 날짜 포맷 허용)."""
    text = str(exp_date_text or "").strip()
    if not text:
        return None
    parsed = None
    for fmt in ("%Y.%m.%d", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            parsed = datetime.strptime(text, fmt).date()
            break
        except ValueError:
            continue
    if parsed is None:
        return None
    days = (parsed - date.today()).days
    return _badge_for_days(days, parsed.strftime("%Y.%m.%d"))
