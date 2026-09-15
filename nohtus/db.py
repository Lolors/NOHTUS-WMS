import sqlite3
from functools import lru_cache

import pandas as pd

from .config import DB_PATH


@lru_cache(maxsize=64)
def _ensure_wal_mode(db_path_str: str) -> None:
    """이 DB 파일을 WAL 저널 모드로 한 번만 전환해둔다.

    데스크톱 Streamlit 앱과 모바일 API가 같은 SQLite 파일을 별도 프로세스로
    동시에 여는데, 기본 저널 모드(rollback journal)에서는 한쪽이 쓰는 동안
    다른 쪽 접근이 최대 5초(sqlite3 기본 timeout)까지 조용히 멈춰서 데스크톱
    화면이 이유 없이 버벅이는 것처럼 보인다. WAL 모드는 읽기와 쓰기가 서로
    막지 않아 이 정체를 없앤다. maxsize를 둔 건 테스트가 DB_PATH를 매번 다른
    임시 파일로 바꿔치기하기 때문(무한정 쌓이지 않게 상한만 둔 것)."""
    conn = sqlite3.connect(db_path_str, timeout=5.0)
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.commit()
    finally:
        conn.close()


def connect():
    DB_PATH.parent.mkdir(exist_ok=True)
    _ensure_wal_mode(str(DB_PATH))
    conn = sqlite3.connect(DB_PATH, timeout=5.0)
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def q(sql, params=()):
    with connect() as con:
        return pd.read_sql_query(sql, con, params=params)


def exec_sql(sql, params=()):
    with connect() as con:
        con.execute(sql, params)
        con.commit()


def read_cache_token():
    """Cheap fingerprint that changes whenever the WMS SQLite file changes.

    Meant for @st.cache_data(...) callers so they can invalidate a cached
    query result when the underlying data actually changed, instead of never
    caching (always slow) or never invalidating (stale results). Includes the
    path itself (not just mtime/size) so two different DB_PATH values that
    happen to produce identically-sized files at the same timestamp (e.g.
    fresh temp databases created back-to-back in tests) never collide."""
    db_stat = DB_PATH.stat() if DB_PATH.exists() else None
    return (
        str(DB_PATH),
        int(db_stat.st_mtime_ns) if db_stat else 0,
        int(db_stat.st_size) if db_stat else 0,
    )
