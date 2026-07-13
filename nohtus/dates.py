"""Date helpers for NOHTUS WMS.

These functions are kept independent from Streamlit so they can be moved out of
app.py safely during gradual refactoring.
"""

from __future__ import annotations

import calendar
from datetime import date, datetime

import pandas as pd


def normalize_exp_date(value) -> str:
    """Normalize common expiry-date inputs to YYYY-MM-DD.

    Empty values are stored as '-'. Two-digit years are treated as 20xx.
    When only year/month is entered, store one day before that month's final day.
    Example: 28/3 -> 2028-03-30.
    """
    if value is None:
        return "-"
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y-%m-%d")

    raw = str(value).strip()
    if not raw or raw.lower() == "nan" or raw == "-":
        return "-"

    raw = raw.split(" ")[0].strip()
    compact = raw.replace("/", ".").replace("-", ".").replace("_", ".").replace(" ", "")

    try:
        if compact.isdigit() and len(compact) == 8:
            y, m, d = int(compact[:4]), int(compact[4:6]), int(compact[6:8])
            return date(y, m, d).strftime("%Y-%m-%d")

        if compact.isdigit() and len(compact) == 6:
            y, m, d = int(compact[:2]), int(compact[2:4]), int(compact[4:6])
            y = 2000 + y if y < 100 else y
            return date(y, m, d).strftime("%Y-%m-%d")

        parts = [x for x in compact.split(".") if x]
        if len(parts) == 3:
            y, m, d = map(int, parts)
            y = 2000 + y if y < 100 else y
            return date(y, m, d).strftime("%Y-%m-%d")

        if len(parts) == 2:
            y, m = map(int, parts)
            y = 2000 + y if y < 100 else y
            last_day = calendar.monthrange(y, m)[1]
            target_day = max(1, last_day - 1)
            return date(y, m, target_day).strftime("%Y-%m-%d")
    except Exception:
        pass

    parsed = pd.to_datetime(raw, errors="coerce")
    if pd.notna(parsed):
        return parsed.strftime("%Y-%m-%d")
    return raw


def display_date_only(value) -> str:
    """Return a display-safe date string in YYYY-MM-DD form."""
    if value is None:
        return "-"
    text = str(value).strip()
    if not text or text.lower() == "nan" or text == "-":
        return "-"
    parsed = pd.to_datetime(text, errors="coerce")
    if pd.notna(parsed):
        return parsed.strftime("%Y-%m-%d")
    return normalize_exp_date(text)


def expiry_status(exp_date: str) -> str:
    """Classify expiry as 정상, 임박(1년), or 만료."""
    exp = (exp_date or "").strip()
    if not exp or exp == "-":
        return "정상"
    try:
        d = datetime.strptime(exp, "%Y-%m-%d").date()
    except Exception:
        return "정상"
    today = date.today()
    if d < today:
        return "만료"
    if (d - today).days <= 365:
        return "임박(1년)"
    return "정상"
