"""SQLite 연결과 공통 트랜잭션 설정."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

DB_FILENAME = "purchase_order.db"


def database_path(data_dir: Path) -> Path:
    return Path(data_dir) / DB_FILENAME


def connect(data_dir: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(database_path(data_dir), timeout=10)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


@contextmanager
def transaction(data_dir: Path) -> Iterator[sqlite3.Connection]:
    conn = connect(data_dir)
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
