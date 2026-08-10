from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache, wraps
from pathlib import Path
from typing import Any, Iterable

from nohtus.export_app.services import usb_storage_service
from nohtus.export_app.utils.dates import now_text
from nohtus.export_app.utils.performance import measure

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / 'data' / 'export.db'
UPLOAD_DIR = PROJECT_ROOT / 'data' / 'export_uploads'
LAST_USB_BACKUP_ERROR = ''
LAST_USB_BACKUP_PATH = ''

_BACKUP_BATCH_DEPTH: ContextVar[int] = ContextVar('backup_batch_depth', default=0)
_BACKUP_BATCH_PENDING: ContextVar[bool] = ContextVar('backup_batch_pending', default=False)
_PAGE_CONNECTION: ContextVar[sqlite3.Connection | None] = ContextVar('page_connection', default=None)


@lru_cache(maxsize=1)
def _initialize_database_runtime() -> None:
    conn = sqlite3.connect(DB_PATH, timeout=5.0)
    try:
        conn.execute('PRAGMA journal_mode = WAL')
        conn.execute('PRAGMA synchronous = NORMAL')
        conn.execute(f'PRAGMA user_version = {usb_storage_service.DB_VERSION}')
        conn.commit()
    finally:
        conn.close()


def read_cache_token() -> tuple[int, int, int, int]:
    """Return a cheap fingerprint that changes whenever SQLite data changes."""
    db_stat = DB_PATH.stat() if DB_PATH.exists() else None
    wal_path = DB_PATH.with_name(DB_PATH.name + '-wal')
    wal_stat = wal_path.stat() if wal_path.exists() else None
    return (
        int(db_stat.st_mtime_ns) if db_stat else 0,
        int(db_stat.st_size) if db_stat else 0,
        int(wal_stat.st_mtime_ns) if wal_stat else 0,
        int(wal_stat.st_size) if wal_stat else 0,
    )


def _configure_connection(conn: sqlite3.Connection) -> None:
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    conn.execute('PRAGMA busy_timeout = 5000')
    conn.execute('PRAGMA temp_store = MEMORY')


@contextmanager
def connection_session() -> Iterable[sqlite3.Connection]:
    """Reuse one SQLite connection during a single Streamlit page execution."""
    existing = _PAGE_CONNECTION.get()
    if existing is not None:
        yield existing
        return

    _initialize_database_runtime()
    conn = sqlite3.connect(DB_PATH, timeout=5.0)
    _configure_connection(conn)
    token = _PAGE_CONNECTION.set(conn)
    try:
        yield conn
    finally:
        _PAGE_CONNECTION.reset(token)
        conn.close()


@contextmanager
def connect() -> Iterable[sqlite3.Connection]:
    existing = _PAGE_CONNECTION.get()
    if existing is not None:
        try:
            yield existing
            existing.commit()
        except Exception:
            existing.rollback()
            raise
        return

    _initialize_database_runtime()
    conn = sqlite3.connect(DB_PATH, timeout=5.0)
    _configure_connection(conn)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def backup_to_usb() -> Path | None:
    # WMS 병합 후에는 database_backup.py의 구글드라이브 백업이 export.db를
    # 함께 처리한다. USB 백업 경로는 비활성화한다.
    return None



def _request_usb_backup() -> None:
    if _BACKUP_BATCH_DEPTH.get() > 0:
        _BACKUP_BATCH_PENDING.set(True)
        return
    backup_to_usb()


@contextmanager
def defer_usb_backup():
    """Run one USB backup after a logical group of database writes."""
    depth = _BACKUP_BATCH_DEPTH.get()
    depth_token = _BACKUP_BATCH_DEPTH.set(depth + 1)
    try:
        yield
    finally:
        _BACKUP_BATCH_DEPTH.reset(depth_token)
        if depth == 0 and _BACKUP_BATCH_PENDING.get():
            _BACKUP_BATCH_PENDING.set(False)
            backup_to_usb()


def backup_batch(func):
    """Decorate a service operation that contains multiple DB writes."""
    @wraps(func)
    def wrapped(*args, **kwargs):
        with defer_usb_backup():
            return func(*args, **kwargs)
    return wrapped

def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row['name'] for row in conn.execute(f'PRAGMA table_info({table})')}


def _add_column(conn: sqlite3.Connection, table: str, definition: str) -> None:
    name = definition.split()[0]
    if name not in _columns(conn, table):
        conn.execute(f'ALTER TABLE {table} ADD COLUMN {definition}')


def _remove_expected_ship_date_column(conn: sqlite3.Connection) -> None:
    if 'expected_ship_date' not in _columns(conn, 'export_cases'):
        return

    conn.executescript('''
    PRAGMA foreign_keys = OFF;
    CREATE TABLE export_cases_new (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        export_no TEXT NOT NULL UNIQUE,
        buyer TEXT DEFAULT '',
        country TEXT NOT NULL DEFAULT '',
        transport_mode TEXT DEFAULT 'AIR',
        stage TEXT NOT NULL DEFAULT '주문 접수',
        status TEXT NOT NULL DEFAULT '진행중',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        domestic_method TEXT DEFAULT '',
        tracking_no TEXT DEFAULT '',
        driver_name TEXT DEFAULT '',
        driver_phone TEXT DEFAULT '',
        consignee_name TEXT DEFAULT '',
        consignee_address TEXT DEFAULT '',
        note TEXT DEFAULT '',
        actual_ship_date TEXT DEFAULT '',
        folder_path TEXT DEFAULT '',
        cancel_reason TEXT DEFAULT '',
        cancelled_at TEXT DEFAULT '',
        previous_stage TEXT DEFAULT '',
        case_type TEXT DEFAULT 'current'
    );
    INSERT INTO export_cases_new(
        id,export_no,buyer,country,transport_mode,stage,status,created_at,updated_at,
        domestic_method,tracking_no,driver_name,driver_phone,consignee_name,consignee_address,
        note,actual_ship_date,folder_path,cancel_reason,cancelled_at,previous_stage,case_type
    )
    SELECT
        id,export_no,buyer,country,transport_mode,stage,status,created_at,updated_at,
        COALESCE(domestic_method,''),COALESCE(tracking_no,''),COALESCE(driver_name,''),
        COALESCE(driver_phone,''),'','',COALESCE(note,''),COALESCE(actual_ship_date,''),
        COALESCE(folder_path,''),COALESCE(cancel_reason,''),COALESCE(cancelled_at,''),
        COALESCE(previous_stage,''),'current'
    FROM export_cases;
    DROP TABLE export_cases;
    ALTER TABLE export_cases_new RENAME TO export_cases;
    PRAGMA foreign_keys = ON;
    ''')


def _migrate_completed_cases_to_domestic(conn: sqlite3.Connection) -> int:
    migration_key = 'migration_completed_to_domestic_20260730_v2'
    completed = conn.execute(
        'SELECT 1 FROM settings WHERE key=?',
        (migration_key,),
    ).fetchone()
    if completed:
        return 0

    timestamp = now_text()
    target_ids = [
        int(row['id'])
        for row in conn.execute(
            "SELECT id FROM export_cases WHERE stage='완료'"
        ).fetchall()
    ]
    if target_ids:
        conn.execute(
            """INSERT INTO history(case_id,action,detail,created_at)
               SELECT id, '단계 일괄 변경', '완료 → 국내배송', ?
               FROM export_cases
               WHERE stage='완료'""",
            (timestamp,),
        )
        conn.execute(
            """UPDATE export_cases
               SET stage='국내배송', status='완료', updated_at=?
               WHERE stage='완료'""",
            (timestamp,),
        )

    conn.execute(
        '''INSERT INTO settings(key,value,updated_at) VALUES (?,?,?)''',
        (migration_key, str(len(target_ids)), timestamp),
    )
    return len(target_ids)


@lru_cache(maxsize=1)
def init_db() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    migrated_completed_case_count = 0

    with connect() as conn:
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS export_cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            export_no TEXT NOT NULL UNIQUE,
            buyer TEXT DEFAULT '',
            country TEXT NOT NULL DEFAULT '',
            transport_mode TEXT DEFAULT 'AIR',
            stage TEXT NOT NULL DEFAULT '주문 접수',
            status TEXT NOT NULL DEFAULT '진행중',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id INTEGER NOT NULL REFERENCES export_cases(id) ON DELETE CASCADE,
            product_name TEXT NOT NULL,
            quantity REAL NOT NULL DEFAULT 0,
            unit TEXT DEFAULT 'EA',
            purchase_price REAL NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS purchase_price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id INTEGER NOT NULL REFERENCES export_cases(id) ON DELETE CASCADE,
            order_item_id INTEGER REFERENCES order_items(id) ON DELETE SET NULL,
            product_name TEXT NOT NULL,
            normalized_name TEXT NOT NULL DEFAULT '',
            purchase_price REAL NOT NULL DEFAULT 0,
            quantity REAL NOT NULL DEFAULT 0,
            unit TEXT DEFAULT 'EA',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS shipment_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id INTEGER NOT NULL REFERENCES export_cases(id) ON DELETE CASCADE,
            business_unit TEXT DEFAULT '',
            location TEXT DEFAULT '',
            product_name TEXT NOT NULL,
            lot_no TEXT DEFAULT '',
            expiry_date TEXT DEFAULT '',
            requested_qty REAL NOT NULL DEFAULT 0,
            box_no INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS boxes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id INTEGER NOT NULL REFERENCES export_cases(id) ON DELETE CASCADE,
            box_no INTEGER NOT NULL,
            length_cm REAL DEFAULT 0,
            width_cm REAL DEFAULT 0,
            height_cm REAL DEFAULT 0,
            weight_kg REAL DEFAULT 0,
            updated_at TEXT NOT NULL,
            UNIQUE(case_id, box_no)
        );
        CREATE TABLE IF NOT EXISTS attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id INTEGER NOT NULL REFERENCES export_cases(id) ON DELETE CASCADE,
            file_name TEXT NOT NULL,
            stored_path TEXT NOT NULL,
            category TEXT DEFAULT '출고사진',
            uploaded_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id INTEGER REFERENCES export_cases(id) ON DELETE CASCADE,
            action TEXT NOT NULL,
            detail TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL
        );
        ''')

        for definition in [
            "domestic_method TEXT DEFAULT ''",
            "tracking_no TEXT DEFAULT ''",
            "driver_name TEXT DEFAULT ''",
            "driver_phone TEXT DEFAULT ''",
            "consignee_name TEXT DEFAULT ''",
            "consignee_address TEXT DEFAULT ''",
            "note TEXT DEFAULT ''",
            "actual_ship_date TEXT DEFAULT ''",
            "folder_path TEXT DEFAULT ''",
            "cancel_reason TEXT DEFAULT ''",
            "cancelled_at TEXT DEFAULT ''",
            "previous_stage TEXT DEFAULT ''",
            "case_type TEXT DEFAULT 'current'",
        ]:
            _add_column(conn, 'export_cases', definition)

        _remove_expected_ship_date_column(conn)
        _add_column(conn, 'shipment_items', 'order_item_id INTEGER')
        _add_column(conn, 'shipment_items', 'source_inventory_id INTEGER')
        _add_column(conn, 'order_items', 'purchase_price REAL NOT NULL DEFAULT 0')

        conn.execute("UPDATE export_cases SET stage='패킹 대기' WHERE stage='출고 대기'")
        conn.execute("UPDATE export_cases SET previous_stage='패킹 대기' WHERE previous_stage='출고 대기'")

        conn.executescript('''
        CREATE INDEX IF NOT EXISTS idx_export_cases_status_stage
            ON export_cases(status, stage);
        CREATE INDEX IF NOT EXISTS idx_export_cases_dates
            ON export_cases(actual_ship_date, created_at);
        CREATE INDEX IF NOT EXISTS idx_export_cases_ship_date
            ON export_cases(date(substr(actual_ship_date, 1, 10)), id);
        CREATE INDEX IF NOT EXISTS idx_order_items_case_id
            ON order_items(case_id);
        CREATE INDEX IF NOT EXISTS idx_purchase_price_history_name
            ON purchase_price_history(normalized_name, created_at);
        CREATE INDEX IF NOT EXISTS idx_purchase_price_history_case
            ON purchase_price_history(case_id, order_item_id);
        CREATE INDEX IF NOT EXISTS idx_shipment_items_case_id
            ON shipment_items(case_id);
        CREATE INDEX IF NOT EXISTS idx_shipment_items_order_item_id
            ON shipment_items(order_item_id);
        CREATE INDEX IF NOT EXISTS idx_shipment_items_case_order
            ON shipment_items(case_id, order_item_id);
        CREATE INDEX IF NOT EXISTS idx_shipment_items_case_box
            ON shipment_items(case_id, box_no);
        CREATE INDEX IF NOT EXISTS idx_boxes_case_box
            ON boxes(case_id, box_no);
        CREATE INDEX IF NOT EXISTS idx_history_case_id
            ON history(case_id);
        ''')
        migrated_completed_case_count = _migrate_completed_cases_to_domestic(conn)

    if migrated_completed_case_count:
        backup_to_usb()


def rows(query: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
    with measure('db.rows'):
        with connect() as conn:
            return list(conn.execute(query, params).fetchall())


def row(query: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
    with measure('db.row'):
        with connect() as conn:
            return conn.execute(query, params).fetchone()


def execute(query: str, params: tuple[Any, ...] = ()) -> int:
    with connect() as conn:
        cursor = conn.execute(query, params)
        result = int(cursor.lastrowid or 0)
    _request_usb_backup()
    return result


def executemany(query: str, values: list[tuple[Any, ...]]) -> None:
    with connect() as conn:
        conn.executemany(query, values)
    _request_usb_backup()


def get_setting(key: str, default: str = '') -> str:
    result = row('SELECT value FROM settings WHERE key=?', (key,))
    return str(result['value']) if result else default


def set_setting(key: str, value: str) -> None:
    execute(
        '''INSERT INTO settings(key,value,updated_at) VALUES (?,?,?)
           ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at''',
        (key, value, now_text()),
    )
