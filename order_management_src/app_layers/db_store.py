"""발주관리 시스템의 주요 데이터를 SQLite에서 읽고 저장하는 저장소 모듈."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Callable

import pandas as pd

from db_migration import normalize_product_code

PRODUCT_COLUMNS = ["제품유형", "제품코드", "제품명", "규격", "포장단위"]
ALIAS_COLUMNS = ["거래처명", "별칭", "제품코드"]
VENDOR_COLUMNS = ["거래처코드", "거래처명", "담당자", "연락처", "이메일", "배송지"]
ORDER_COLUMNS = ["발주ID", "발주일시", "거래처명", "요청사항", "상태", "총품목수", "총수량"]
ORDER_ITEM_COLUMNS = ["발주ID", "순번", "제품코드", "정식제품명", "검색별칭", "규격", "단위", "수량"]


def _db_path(data_dir: Path) -> Path:
    return Path(data_dir) / "purchase_order.db"


def _connect(data_dir: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path(data_dir), timeout=10)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


def _to_int(value: object) -> int:
    try:
        return int(float(str(value or "0").replace(",", "")))
    except (TypeError, ValueError):
        return 0


def load_products(data_dir: Path) -> pd.DataFrame:
    with _connect(data_dir) as conn:
        rows = conn.execute(
            """
            SELECT product_type, product_code, product_name, specification, packaging_unit
            FROM products
            ORDER BY product_name, product_code
            """
        ).fetchall()
    result = pd.DataFrame(rows, columns=PRODUCT_COLUMNS)
    if result.empty:
        return pd.DataFrame(columns=PRODUCT_COLUMNS)
    result["제품코드"] = result["제품코드"].map(normalize_product_code)
    return result.fillna("")


def save_products(data_dir: Path, products: pd.DataFrame) -> None:
    clean = products.copy().fillna("")
    if "제품명" not in clean.columns:
        clean["제품명"] = clean.get("정식제품명", "")
    if "포장단위" not in clean.columns:
        clean["포장단위"] = clean.get("단위", "")
    if "제품유형" not in clean.columns:
        clean["제품유형"] = ""
    for col in PRODUCT_COLUMNS:
        if col not in clean.columns:
            clean[col] = ""
        clean[col] = clean[col].astype(str).str.strip()
    clean["제품코드"] = clean["제품코드"].map(normalize_product_code)
    clean = clean[(clean["제품코드"] != "") & (clean["제품명"] != "")]
    clean = clean.drop_duplicates("제품코드", keep="last")
    rows = [tuple(row[col] for col in PRODUCT_COLUMNS) for _, row in clean.iterrows()]
    with _connect(data_dir) as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM products")
        conn.executemany(
            "INSERT INTO products(product_type,product_code,product_name,specification,packaging_unit) VALUES(?,?,?,?,?)",
            rows,
        )
        conn.commit()


def load_aliases(data_dir: Path) -> pd.DataFrame:
    with _connect(data_dir) as conn:
        rows = conn.execute(
            "SELECT vendor_name, alias, product_code FROM aliases ORDER BY vendor_name, alias, product_code"
        ).fetchall()
    result = pd.DataFrame(rows, columns=ALIAS_COLUMNS)
    if result.empty:
        return pd.DataFrame(columns=ALIAS_COLUMNS)
    result["제품코드"] = result["제품코드"].map(normalize_product_code)
    return result.fillna("")


def save_aliases(data_dir: Path, aliases: pd.DataFrame) -> None:
    clean = aliases.copy().fillna("")
    for col in ALIAS_COLUMNS:
        if col not in clean.columns:
            clean[col] = ""
        clean[col] = clean[col].astype(str).str.strip()
    clean["제품코드"] = clean["제품코드"].map(normalize_product_code)
    clean = clean[(clean["별칭"] != "") & (clean["제품코드"] != "")]
    clean.loc[clean["거래처명"] == "", "거래처명"] = "전체"
    clean = clean.drop_duplicates(ALIAS_COLUMNS, keep="last")
    rows = [tuple(row[col] for col in ALIAS_COLUMNS) for _, row in clean.iterrows()]
    with _connect(data_dir) as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM aliases")
        conn.executemany("INSERT INTO aliases(vendor_name,alias,product_code) VALUES(?,?,?)", rows)
        conn.commit()


def load_vendors(data_dir: Path) -> pd.DataFrame:
    with _connect(data_dir) as conn:
        rows = conn.execute(
            """
            SELECT vendor_code, vendor_name, manager, phone, email, delivery_address
            FROM vendors
            ORDER BY vendor_name, id
            """
        ).fetchall()
    return pd.DataFrame(rows, columns=VENDOR_COLUMNS).fillna("")


def save_vendors(data_dir: Path, vendors: pd.DataFrame) -> None:
    clean = vendors.copy().fillna("")
    for col in VENDOR_COLUMNS:
        if col not in clean.columns:
            clean[col] = ""
        clean[col] = clean[col].astype(str).str.strip()
    clean = clean[clean["거래처명"] != ""]
    clean = clean.drop_duplicates("거래처명", keep="last")
    rows = [tuple(row[col] for col in VENDOR_COLUMNS) for _, row in clean.iterrows()]
    with _connect(data_dir) as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM vendors")
        conn.executemany(
            "INSERT INTO vendors(vendor_code,vendor_name,manager,phone,email,delivery_address) VALUES(?,?,?,?,?,?)",
            rows,
        )
        conn.commit()


def load_orders(data_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    with _connect(data_dir) as conn:
        headers = conn.execute(
            """
            SELECT order_id, ordered_at, vendor_name, request_note, status,
                   total_item_count, total_quantity
            FROM orders
            ORDER BY ordered_at DESC, order_id DESC
            """
        ).fetchall()
        items = conn.execute(
            """
            SELECT order_id, sequence, product_code, product_name, search_alias,
                   specification, packaging_unit, quantity
            FROM order_items
            ORDER BY order_id, sequence, id
            """
        ).fetchall()
    orders = pd.DataFrame(headers, columns=ORDER_COLUMNS).fillna("")
    order_items = pd.DataFrame(items, columns=ORDER_ITEM_COLUMNS).fillna("")
    if not order_items.empty:
        order_items["제품코드"] = order_items["제품코드"].map(normalize_product_code)
    return orders, order_items


def _selected_order_date(base_app) -> date:
    value = base_app.st.session_state.get("order_date")
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value:
        try:
            return pd.to_datetime(value).date()
        except Exception:
            pass
    return datetime.now().date()


def _item_rows(order_id: str, order_items: list[dict]) -> list[tuple]:
    rows = []
    for idx, item in enumerate(order_items, 1):
        rows.append((
            order_id,
            idx,
            normalize_product_code(item.get("제품코드", "")),
            str(item.get("제품명", item.get("정식제품명", "")) or ""),
            str(item.get("검색별칭", "") or ""),
            str(item.get("규격", "") or ""),
            str(item.get("포장단위", item.get("단위", "")) or ""),
            _to_int(item.get("수량", 0)),
        ))
    return rows


def save_order(data_dir: Path, base_app, vendor_name: str, request_note: str, order_items: list[dict]) -> str:
    selected_date = _selected_order_date(base_app)
    now = datetime.now()
    ordered_at = datetime.combine(selected_date, now.time().replace(microsecond=0))
    base_id = f"PO-{ordered_at.strftime('%y%m%d-%H%M%S')}"

    total_count = len(order_items)
    total_qty = sum(_to_int(item.get("수량", 0)) for item in order_items)

    with _connect(data_dir) as conn:
        conn.execute("BEGIN IMMEDIATE")
        existing = {row[0] for row in conn.execute("SELECT order_id FROM orders WHERE order_id LIKE ?", (f"{base_id}%",))}
        order_id = base_id
        suffix = 2
        while order_id in existing:
            order_id = f"{base_id}-{suffix}"
            suffix += 1

        conn.execute(
            """
            INSERT INTO orders(order_id,ordered_at,vendor_name,request_note,status,total_item_count,total_quantity)
            VALUES(?,?,?,?,?,?,?)
            """,
            (
                order_id,
                ordered_at.strftime("%Y-%m-%d %H:%M:%S"),
                str(vendor_name or "").strip(),
                str(request_note or ""),
                "발주완료",
                total_count,
                total_qty,
            ),
        )

        rows = _item_rows(order_id, order_items)
        if rows:
            conn.executemany(
                """
                INSERT INTO order_items(order_id,sequence,product_code,product_name,search_alias,specification,packaging_unit,quantity)
                VALUES(?,?,?,?,?,?,?,?)
                """,
                rows,
            )
        conn.commit()
    return order_id


def update_order(data_dir: Path, base_app, order_id: str, vendor_name: str, request_note: str, order_items: list[dict]) -> str:
    order_id = str(order_id or "").strip()
    if not order_id:
        raise ValueError("수정할 발주ID가 없습니다.")

    selected_date = _selected_order_date(base_app)
    total_count = len(order_items)
    total_qty = sum(_to_int(item.get("수량", 0)) for item in order_items)

    with _connect(data_dir) as conn:
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute(
            "SELECT ordered_at, status FROM orders WHERE order_id = ?",
            (order_id,),
        ).fetchone()
        if existing is None:
            raise ValueError(f"수정할 발주서를 찾을 수 없습니다: {order_id}")

        original_time = pd.to_datetime(existing[0], errors="coerce")
        if pd.isna(original_time):
            original_time = datetime.now()
        ordered_at = datetime.combine(selected_date, original_time.time().replace(microsecond=0))

        conn.execute(
            """
            UPDATE orders
            SET ordered_at = ?, vendor_name = ?, request_note = ?,
                total_item_count = ?, total_quantity = ?
            WHERE order_id = ?
            """,
            (
                ordered_at.strftime("%Y-%m-%d %H:%M:%S"),
                str(vendor_name or "").strip(),
                str(request_note or ""),
                total_count,
                total_qty,
                order_id,
            ),
        )
        conn.execute("DELETE FROM order_items WHERE order_id = ?", (order_id,))
        rows = _item_rows(order_id, order_items)
        if rows:
            conn.executemany(
                """
                INSERT INTO order_items(order_id,sequence,product_code,product_name,search_alias,specification,packaging_unit,quantity)
                VALUES(?,?,?,?,?,?,?,?)
                """,
                rows,
            )
        conn.commit()
    return order_id


def delete_order(data_dir: Path, order_id: str) -> None:
    order_id = str(order_id or "").strip()
    if not order_id:
        raise ValueError("삭제할 발주ID가 없습니다.")

    with _connect(data_dir) as conn:
        conn.execute("BEGIN IMMEDIATE")
        statement_ids = [
            row[0] for row in conn.execute(
                "SELECT statement_id FROM statements WHERE order_id = ?",
                (order_id,),
            ).fetchall()
        ]
        if statement_ids:
            placeholders = ",".join("?" for _ in statement_ids)
            conn.execute(f"DELETE FROM price_history WHERE statement_id IN ({placeholders})", statement_ids)
            conn.execute(f"DELETE FROM statement_items WHERE statement_id IN ({placeholders})", statement_ids)
        conn.execute("DELETE FROM statements WHERE order_id = ?", (order_id,))
        conn.execute("DELETE FROM order_items WHERE order_id = ?", (order_id,))
        conn.execute("DELETE FROM orders WHERE order_id = ?", (order_id,))
        conn.commit()


def activate(base_app) -> None:
    original_load_data: Callable = base_app.load_data

    def load_data_from_db():
        _, _, _, drafts, draft_items, _, _ = original_load_data()
        vendors = load_vendors(base_app.DATA)
        products = load_products(base_app.DATA)
        products["정식제품명"] = products["제품명"]
        products["단위"] = products["포장단위"]
        aliases = load_aliases(base_app.DATA)
        orders, order_items = load_orders(base_app.DATA)
        return vendors, products, aliases, drafts, draft_items, orders, order_items

    base_app.load_data = load_data_from_db
    base_app.save_products = lambda df: save_products(base_app.DATA, df)
    base_app.save_aliases = lambda df: save_aliases(base_app.DATA, df)
    base_app.save_vendors = lambda df: save_vendors(base_app.DATA, df)
    base_app.save_order = lambda vendor_name, request_note, items: save_order(
        base_app.DATA, base_app, vendor_name, request_note, items
    )
    base_app.delete_order = lambda order_id: delete_order(base_app.DATA, order_id)
