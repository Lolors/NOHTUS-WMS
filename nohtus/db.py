import sqlite3

import pandas as pd

from .config import DB_PATH


def connect():
    DB_PATH.parent.mkdir(exist_ok=True)
    return sqlite3.connect(DB_PATH)


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
