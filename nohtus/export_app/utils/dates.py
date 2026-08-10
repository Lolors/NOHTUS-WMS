from __future__ import annotations

from datetime import date, datetime


def now_text() -> str:
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ('%Y-%m-%d', '%Y.%m.%d', '%Y/%m/%d'):
        try:
            return datetime.strptime(str(value), fmt)
        except ValueError:
            continue
    return None


def date_value(value: str | None) -> date:
    parsed = parse_date(value)
    return parsed.date() if parsed else date.today()
