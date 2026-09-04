"""CSV 데이터를 SQLite로 안전하게 1회 이전하는 초기 마이그레이션 모듈."""

from __future__ import annotations

import re
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Iterable

import pandas as pd

DB_FILENAME = "purchase_order.db"
MIGRATION_KEY = "csv_migration_v1"


def normalize_product_code(value: object) -> str:
    """ERP 제품코드를 5자리 텍스트로 보존합니다."""
    text = str(value if value is not None else "").strip()
    if not text or text.lower() == "nan":
        return ""
    if re.fullmatch(r"\d+\.0+", text):
        text = text.split(".", 1)[0]
    if text.isdigit():
        return text.zfill(5)
    return text


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str, keep_default_na=False).fillna("")


def _value(row: pd.Series, *names: str) -> str:
    for name in names:
        if name in row.index:
            return str(row.get(name, "") or "").strip()
    return ""


def _int_text(value: object) -> int:
    try:
        return int(float(str(value or "0").replace(",", "")))
    except (TypeError, ValueError):
        return 0


def _create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        PRAGMA foreign_keys = ON;
        PRAGMA journal_mode = WAL;
        PRAGMA synchronous = NORMAL;
        PRAGMA busy_timeout = 5000;

        CREATE TABLE IF NOT EXISTS app_metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS vendors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vendor_code TEXT,
            vendor_name TEXT NOT NULL,
            manager TEXT,
            phone TEXT,
            email TEXT,
            delivery_address TEXT
        );

        CREATE TABLE IF NOT EXISTS products (
            product_code TEXT PRIMARY KEY,
            product_type TEXT,
            product_name TEXT NOT NULL,
            specification TEXT,
            packaging_unit TEXT
        );

        CREATE TABLE IF NOT EXISTS aliases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vendor_name TEXT NOT NULL,
            alias TEXT NOT NULL,
            product_code TEXT NOT NULL,
            UNIQUE(vendor_name, alias, product_code)
        );

        CREATE TABLE IF NOT EXISTS drafts (
            draft_id TEXT PRIMARY KEY,
            created_at TEXT,
            vendor_name TEXT,
            request_note TEXT,
            status TEXT,
            total_item_count INTEGER DEFAULT 0,
            total_quantity INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS draft_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            draft_id TEXT NOT NULL,
            sequence INTEGER,
            product_code TEXT,
            product_name TEXT,
            search_alias TEXT,
            specification TEXT,
            packaging_unit TEXT,
            quantity INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS orders (
            order_id TEXT PRIMARY KEY,
            ordered_at TEXT,
            vendor_name TEXT,
            request_note TEXT,
            status TEXT,
            total_item_count INTEGER DEFAULT 0,
            total_quantity INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT NOT NULL,
            sequence INTEGER,
            product_code TEXT,
            product_name TEXT,
            search_alias TEXT,
            specification TEXT,
            packaging_unit TEXT,
            quantity INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS statements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            statement_id TEXT NOT NULL,
            order_id TEXT,
            vendor_name TEXT,
            statement_number TEXT,
            statement_date TEXT,
            freight INTEGER DEFAULT 0,
            freight_entered TEXT,
            memo TEXT,
            created_at TEXT,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS statement_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            statement_id TEXT NOT NULL,
            sequence INTEGER,
            product_code TEXT,
            product_name TEXT,
            specification TEXT,
            packaging_unit TEXT,
            ordered_quantity INTEGER DEFAULT 0,
            received_quantity INTEGER DEFAULT 0,
            purchase_price INTEGER DEFAULT 0,
            product_amount INTEGER DEFAULT 0,
            sale_price INTEGER DEFAULT 0,
            apply_price TEXT
        );

        CREATE TABLE IF NOT EXISTS price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            price_id TEXT,
            statement_id TEXT,
            statement_date TEXT,
            product_code TEXT,
            product_name TEXT,
            purchase_price INTEGER DEFAULT 0,
            sale_price INTEGER DEFAULT 0,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS monthly_closes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            close_month TEXT,
            product_purchase_amount INTEGER DEFAULT 0,
            freight INTEGER DEFAULT 0,
            total_purchase_amount INTEGER DEFAULT 0,
            statement_count INTEGER DEFAULT 0,
            created_at TEXT,
            memo TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_products_name ON products(product_name);
        CREATE INDEX IF NOT EXISTS idx_aliases_product_code ON aliases(product_code);
        CREATE INDEX IF NOT EXISTS idx_aliases_alias ON aliases(alias);
        CREATE INDEX IF NOT EXISTS idx_orders_vendor_date ON orders(vendor_name, ordered_at);
        CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items(order_id);
        CREATE INDEX IF NOT EXISTS idx_order_items_product_code ON order_items(product_code);
        CREATE INDEX IF NOT EXISTS idx_statements_order_id ON statements(order_id);
        CREATE INDEX IF NOT EXISTS idx_statements_statement_id ON statements(statement_id);
        CREATE INDEX IF NOT EXISTS idx_statements_date ON statements(statement_date);
        CREATE INDEX IF NOT EXISTS idx_statement_items_statement_id ON statement_items(statement_id);
        CREATE INDEX IF NOT EXISTS idx_statement_items_product_code ON statement_items(product_code);
        CREATE INDEX IF NOT EXISTS idx_price_history_product_date ON price_history(product_code, statement_date);
        """
    )


def _backup_csv_files(data_dir: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = data_dir / f"csv_backup_{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=False)
    for path in data_dir.glob("*.csv"):
        shutil.copy2(path, backup_dir / path.name)
    return backup_dir


def _executemany(conn: sqlite3.Connection, sql: str, rows: Iterable[tuple]) -> int:
    values = list(rows)
    if values:
        conn.executemany(sql, values)
    return len(values)


def _migrate_vendors(conn: sqlite3.Connection, data_dir: Path) -> int:
    df = _read_csv(data_dir / "vendors.csv")
    rows = [(
        _value(r, "거래처코드"), _value(r, "거래처명"), _value(r, "담당자"),
        _value(r, "연락처"), _value(r, "이메일"), _value(r, "배송지", "납품처 주소"),
    ) for _, r in df.iterrows() if _value(r, "거래처명")]
    return _executemany(conn, "INSERT INTO vendors(vendor_code,vendor_name,manager,phone,email,delivery_address) VALUES(?,?,?,?,?,?)", rows)


def _migrate_products(conn: sqlite3.Connection, data_dir: Path) -> int:
    df = _read_csv(data_dir / "products.csv")
    rows = []
    for _, r in df.iterrows():
        code = normalize_product_code(_value(r, "제품코드"))
        name = _value(r, "제품명", "정식제품명")
        if not code or not name:
            continue
        rows.append((code, _value(r, "제품유형"), name, _value(r, "규격"), _value(r, "포장단위", "단위")))
    return _executemany(conn, "INSERT OR REPLACE INTO products(product_code,product_type,product_name,specification,packaging_unit) VALUES(?,?,?,?,?)", rows)


def _migrate_aliases(conn: sqlite3.Connection, data_dir: Path) -> int:
    df = _read_csv(data_dir / "aliases.csv")
    rows = []
    for _, r in df.iterrows():
        alias = _value(r, "별칭")
        code = normalize_product_code(_value(r, "제품코드"))
        if alias and code:
            rows.append((_value(r, "거래처명") or "전체", alias, code))
    return _executemany(conn, "INSERT OR IGNORE INTO aliases(vendor_name,alias,product_code) VALUES(?,?,?)", rows)


def _migrate_drafts(conn: sqlite3.Connection, data_dir: Path) -> tuple[int, int]:
    headers = _read_csv(data_dir / "drafts.csv")
    header_rows = [(
        _value(r, "임시ID"), _value(r, "작성일시"), _value(r, "거래처명"), _value(r, "요청사항"),
        _value(r, "상태"), _int_text(_value(r, "총품목수")), _int_text(_value(r, "총수량")),
    ) for _, r in headers.iterrows() if _value(r, "임시ID")]
    h = _executemany(conn, "INSERT OR REPLACE INTO drafts(draft_id,created_at,vendor_name,request_note,status,total_item_count,total_quantity) VALUES(?,?,?,?,?,?,?)", header_rows)

    items = _read_csv(data_dir / "draft_items.csv")
    item_rows = [(
        _value(r, "임시ID"), _int_text(_value(r, "순번")), normalize_product_code(_value(r, "제품코드")),
        _value(r, "정식제품명", "제품명"), _value(r, "검색별칭"), _value(r, "규격"),
        _value(r, "포장단위", "단위"), _int_text(_value(r, "수량")),
    ) for _, r in items.iterrows() if _value(r, "임시ID")]
    i = _executemany(conn, "INSERT INTO draft_items(draft_id,sequence,product_code,product_name,search_alias,specification,packaging_unit,quantity) VALUES(?,?,?,?,?,?,?,?)", item_rows)
    return h, i


def _migrate_orders(conn: sqlite3.Connection, data_dir: Path) -> tuple[int, int]:
    headers = _read_csv(data_dir / "orders.csv")
    header_rows = [(
        _value(r, "발주ID"), _value(r, "발주일시"), _value(r, "거래처명"), _value(r, "요청사항"),
        _value(r, "상태"), _int_text(_value(r, "총품목수")), _int_text(_value(r, "총수량")),
    ) for _, r in headers.iterrows() if _value(r, "발주ID")]
    h = _executemany(conn, "INSERT OR REPLACE INTO orders(order_id,ordered_at,vendor_name,request_note,status,total_item_count,total_quantity) VALUES(?,?,?,?,?,?,?)", header_rows)

    items = _read_csv(data_dir / "order_items.csv")
    item_rows = [(
        _value(r, "발주ID"), _int_text(_value(r, "순번")), normalize_product_code(_value(r, "제품코드")),
        _value(r, "정식제품명", "제품명"), _value(r, "검색별칭"), _value(r, "규격"),
        _value(r, "포장단위", "단위"), _int_text(_value(r, "수량")),
    ) for _, r in items.iterrows() if _value(r, "발주ID")]
    i = _executemany(conn, "INSERT INTO order_items(order_id,sequence,product_code,product_name,search_alias,specification,packaging_unit,quantity) VALUES(?,?,?,?,?,?,?,?)", item_rows)
    return h, i


def _migrate_purchase(conn: sqlite3.Connection, data_dir: Path) -> tuple[int, int, int, int]:
    statements = _read_csv(data_dir / "purchase_statements.csv")
    statement_rows = [(
        _value(r, "명세서ID"), _value(r, "발주ID"), _value(r, "거래처명"), _value(r, "명세서번호"),
        _value(r, "명세서일자"), _int_text(_value(r, "운송비")), _value(r, "운송비입력여부"),
        _value(r, "메모"), _value(r, "등록일시"), _value(r, "수정일시"),
    ) for _, r in statements.iterrows() if _value(r, "명세서ID")]
    s = _executemany(conn, "INSERT INTO statements(statement_id,order_id,vendor_name,statement_number,statement_date,freight,freight_entered,memo,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)", statement_rows)

    items = _read_csv(data_dir / "purchase_statement_items.csv")
    item_rows = [(
        _value(r, "명세서ID"), _int_text(_value(r, "순번")), normalize_product_code(_value(r, "제품코드")),
        _value(r, "정식제품명", "제품명"), _value(r, "규격"), _value(r, "포장단위", "단위"),
        _int_text(_value(r, "발주수량")), _int_text(_value(r, "입고수량")), _int_text(_value(r, "매입단가")),
        _int_text(_value(r, "상품금액")), _int_text(_value(r, "출고단가")), _value(r, "가격적용여부"),
    ) for _, r in items.iterrows() if _value(r, "명세서ID")]
    si = _executemany(conn, "INSERT INTO statement_items(statement_id,sequence,product_code,product_name,specification,packaging_unit,ordered_quantity,received_quantity,purchase_price,product_amount,sale_price,apply_price) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", item_rows)

    prices = _read_csv(data_dir / "price_history.csv")
    price_rows = [(
        _value(r, "가격ID"), _value(r, "명세서ID"), _value(r, "명세서일자"), normalize_product_code(_value(r, "제품코드")),
        _value(r, "정식제품명", "제품명"), _int_text(_value(r, "매입단가")), _int_text(_value(r, "출고단가")), _value(r, "등록일시"),
    ) for _, r in prices.iterrows()]
    p = _executemany(conn, "INSERT INTO price_history(price_id,statement_id,statement_date,product_code,product_name,purchase_price,sale_price,created_at) VALUES(?,?,?,?,?,?,?,?)", price_rows)

    closes = _read_csv(data_dir / "purchase_month_close.csv")
    close_rows = [(
        _value(r, "마감월"), _int_text(_value(r, "상품매입금액")), _int_text(_value(r, "운송비")),
        _int_text(_value(r, "총매입금액")), _int_text(_value(r, "거래명세서수")), _value(r, "등록일시"), _value(r, "메모"),
    ) for _, r in closes.iterrows()]
    c = _executemany(conn, "INSERT INTO monthly_closes(close_month,product_purchase_amount,freight,total_purchase_amount,statement_count,created_at,memo) VALUES(?,?,?,?,?,?,?)", close_rows)
    return s, si, p, c


def initialize_database(data_dir: Path) -> dict:
    """DB를 생성하고 최초 한 번만 CSV를 백업·이전합니다."""
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / DB_FILENAME
    status = {"ok": False, "db_path": str(db_path), "migrated": False, "backup_dir": "", "counts": {}}

    try:
        with sqlite3.connect(db_path, timeout=10) as conn:
            _create_schema(conn)
            marker = conn.execute("SELECT value FROM app_metadata WHERE key = ?", (MIGRATION_KEY,)).fetchone()
            if marker:
                status.update(ok=True, migrated=False)
                return status

            backup_dir = _backup_csv_files(data_dir)
            status["backup_dir"] = str(backup_dir)

            with conn:
                counts = {}
                counts["vendors"] = _migrate_vendors(conn, data_dir)
                counts["products"] = _migrate_products(conn, data_dir)
                counts["aliases"] = _migrate_aliases(conn, data_dir)
                counts["drafts"], counts["draft_items"] = _migrate_drafts(conn, data_dir)
                counts["orders"], counts["order_items"] = _migrate_orders(conn, data_dir)
                (
                    counts["statements"], counts["statement_items"],
                    counts["price_history"], counts["monthly_closes"],
                ) = _migrate_purchase(conn, data_dir)
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                conn.execute(
                    "INSERT OR REPLACE INTO app_metadata(key,value,updated_at) VALUES(?,?,?)",
                    (MIGRATION_KEY, now, now),
                )

            status.update(ok=True, migrated=True, counts=counts)
            return status
    except Exception as exc:
        status["error"] = str(exc)
        return status
