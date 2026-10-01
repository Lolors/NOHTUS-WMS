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


class _ClosingConnection(sqlite3.Connection):
    """sqlite3.Connection.__exit__은 커밋/롤백만 하고 연결을 닫지 않는다 —
    `with connect() as con:`으로 쓰는 모든 호출부(수십 곳)가 매번 연결을
    새로 열고 한 번도 닫지 않은 채 버려지게 된다. CPython에서는 보통 곧
    가비지 컬렉션되지만 타이밍이 보장되지 않고, WAL 모드에서는 아직 안
    닫힌 연결이 남아 있으면 -wal/-shm 파일과 그 디렉터리가 잠긴 채로
    남는다 — 테스트가 임시 DB 디렉터리를 정리하려 할 때
    `PermissionError: [WinError 32]`로 실패하고, 그 임시 폴더가
    AppData\\Local\\Temp에 영구히 쌓이는 원인이었다(GB 단위로 누적).
    `with` 블록을 빠져나올 때 커밋/롤백에 이어 연결도 닫는다."""

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def connect():
    DB_PATH.parent.mkdir(exist_ok=True)
    _ensure_wal_mode(str(DB_PATH))
    conn = sqlite3.connect(DB_PATH, timeout=5.0, factory=_ClosingConnection)
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
