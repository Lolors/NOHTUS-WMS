from __future__ import annotations

from datetime import datetime

from nohtus.export_app import db


def next_export_no(prefix: str = 'EXP', year: int | None = None) -> str:
    target_year = int(year or datetime.now().year)
    result = db.row(
        'SELECT export_no FROM export_cases WHERE export_no LIKE ? ORDER BY export_no DESC LIMIT 1',
        (f'{prefix}-{target_year}-%',),
    )
    if not result:
        return f'{prefix}-{target_year}-001'
    try:
        number = int(result['export_no'].split('-')[-1]) + 1
    except (TypeError, ValueError):
        number = 1
    return f'{prefix}-{target_year}-{number:03d}'
