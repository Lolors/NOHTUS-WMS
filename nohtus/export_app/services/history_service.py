from __future__ import annotations

from nohtus.export_app import db
from nohtus.export_app.utils.dates import now_text


def add(case_id: int | None, action: str, detail: str) -> None:
    db.execute(
        'INSERT INTO history(case_id, action, detail, created_at) VALUES (?,?,?,?)',
        (case_id, action, detail, now_text()),
    )


def add_history(case_id: int | None, action: str, detail: str) -> None:
    """Backward-compatible alias used by existing page code."""
    add(case_id, action, detail)


def list_for_case(case_id: int):
    return db.rows(
        'SELECT action, detail, created_at FROM history WHERE case_id=? ORDER BY id DESC',
        (case_id,),
    )
