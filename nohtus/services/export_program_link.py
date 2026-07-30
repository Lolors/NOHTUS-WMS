from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from nohtus.db import connect


_SETTING_KEY = "export_program_db_path"


def _ensure_settings(cur) -> None:
    cur.execute("""CREATE TABLE IF NOT EXISTS integration_settings(
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL DEFAULT ''
    )""")


def configured_db_path() -> str:
    env_path = str(os.getenv("NOHTUS_EXPORT_DB_PATH") or "").strip()
    if env_path:
        return env_path
    with connect() as con:
        cur = con.cursor()
        _ensure_settings(cur)
        row = cur.execute("SELECT value FROM integration_settings WHERE key=?", (_SETTING_KEY,)).fetchone()
        con.commit()
    return str(row[0] or "").strip() if row else ""


def save_db_path(path_text: str) -> str:
    path = Path(str(path_text or "").strip()).expanduser()
    if not path.is_file():
        raise ValueError("수출관리 export.db 파일을 찾을 수 없습니다.")
    with sqlite3.connect(path) as external:
        tables = {row[0] for row in external.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {"export_cases", "order_items"}.issubset(tables):
            raise ValueError("선택한 파일은 수출관리 프로그램의 export.db가 아닙니다.")
    resolved = str(path.resolve())
    with connect() as con:
        cur = con.cursor()
        _ensure_settings(cur)
        cur.execute(
            """INSERT INTO integration_settings(key,value) VALUES(?,?)
               ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
            (_SETTING_KEY, resolved),
        )
        con.commit()
    return resolved


def list_active_orders() -> list[dict]:
    path_text = configured_db_path()
    if not path_text or not Path(path_text).is_file():
        return []
    try:
        with sqlite3.connect(f"file:{Path(path_text).resolve()}?mode=ro", uri=True) as con:
            con.row_factory = sqlite3.Row
            rows = con.execute(
                """SELECT c.id,c.export_no,c.country,c.buyer,c.transport_mode,c.stage,c.status,
                          COUNT(o.id) AS item_count,COALESCE(SUM(o.quantity),0) AS order_qty
                   FROM export_cases c
                   LEFT JOIN order_items o ON o.case_id=c.id
                   WHERE COALESCE(c.status,'')<>'취소'
                   GROUP BY c.id
                   ORDER BY c.id DESC"""
            ).fetchall()
            return [dict(row) for row in rows]
    except sqlite3.Error as exc:
        raise ValueError(f"수출관리 DB를 읽을 수 없습니다: {exc}") from exc


def order_items(case_id: int) -> list[dict]:
    path_text = configured_db_path()
    if not path_text or not Path(path_text).is_file():
        return []
    with sqlite3.connect(f"file:{Path(path_text).resolve()}?mode=ro", uri=True) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            """SELECT product_name,quantity,unit
               FROM order_items WHERE case_id=? ORDER BY id""",
            (int(case_id),),
        ).fetchall()
        return [dict(row) for row in rows]
