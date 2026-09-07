"""거래명세서·가격이력·월마감 SQLite 저장소."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from infrastructure.database import connect, transaction
from app_layers.db_migration import normalize_product_code

STATEMENT_COLUMNS = [
    "명세서ID", "발주ID", "거래처명", "명세서번호", "명세서일자",
    "운송비", "운송비입력여부", "메모", "등록일시", "수정일시",
]
STATEMENT_ITEM_COLUMNS = [
    "명세서ID", "순번", "제품코드", "정식제품명", "규격", "단위", "발주수량",
    "입고수량", "매입단가", "상품금액", "출고단가", "가격적용여부",
    "원발주제품코드", "원발주제품명", "원발주규격", "원발주단위", "입고유형", "대체사유",
    "제조번호", "유통기한",
]
PRICE_HISTORY_COLUMNS = [
    "가격ID", "명세서ID", "명세서일자", "제품코드", "정식제품명", "매입단가", "출고단가", "등록일시",
]
MONTH_CLOSE_COLUMNS = [
    "마감월", "상품매입금액", "운송비", "총매입금액", "거래명세서수", "등록일시", "메모",
]


def _frame(rows, columns):
    return pd.DataFrame(rows, columns=columns).fillna("")


def _ensure_substitution_columns(conn) -> None:
    existing = {str(row[1]) for row in conn.execute("PRAGMA table_info(statement_items)").fetchall()}
    additions = {
        "original_product_code": "TEXT",
        "original_product_name": "TEXT",
        "original_specification": "TEXT",
        "original_packaging_unit": "TEXT",
        "receipt_type": "TEXT",
        "substitution_reason": "TEXT",
        "lot_number": "TEXT",
        "expiry_date": "TEXT",
    }
    for column, sql_type in additions.items():
        if column not in existing:
            conn.execute(f"ALTER TABLE statement_items ADD COLUMN {column} {sql_type}")
    conn.commit()


def load_all(data_dir: Path):
    with connect(data_dir) as conn:
        _ensure_substitution_columns(conn)
        statements = _frame(conn.execute("""
            SELECT statement_id, order_id, vendor_name, statement_number, statement_date,
                   freight, freight_entered, memo, created_at, updated_at
            FROM statements ORDER BY statement_date DESC, created_at DESC, id DESC
        """).fetchall(), STATEMENT_COLUMNS)
        items = _frame(conn.execute("""
            SELECT statement_id, sequence, product_code, product_name, specification,
                   packaging_unit, ordered_quantity, received_quantity, purchase_price,
                   product_amount, sale_price, apply_price,
                   original_product_code, original_product_name, original_specification,
                   original_packaging_unit, receipt_type, substitution_reason,
                   lot_number, expiry_date
            FROM statement_items ORDER BY statement_id, sequence, id
        """).fetchall(), STATEMENT_ITEM_COLUMNS)
        prices = _frame(conn.execute("""
            SELECT price_id, statement_id, statement_date, product_code, product_name,
                   purchase_price, sale_price, created_at
            FROM price_history ORDER BY statement_date DESC, created_at DESC, id DESC
        """).fetchall(), PRICE_HISTORY_COLUMNS)
        closes = _frame(conn.execute("""
            SELECT close_month, product_purchase_amount, freight, total_purchase_amount,
                   statement_count, created_at, memo
            FROM monthly_closes ORDER BY close_month DESC, id DESC
        """).fetchall(), MONTH_CLOSE_COLUMNS)
    for df in (items, prices):
        if not df.empty:
            df["제품코드"] = df["제품코드"].map(normalize_product_code)
    if not items.empty:
        items["원발주제품코드"] = items["원발주제품코드"].map(normalize_product_code)
    return statements, items, prices, closes


def _int(value):
    try:
        return int(float(str(value or "0").replace(",", "")))
    except (TypeError, ValueError):
        return 0


def replace_statements(data_dir: Path, df: pd.DataFrame) -> None:
    clean = df.copy().fillna("")
    rows = [(
        str(r.get("명세서ID", "")), str(r.get("발주ID", "")), str(r.get("거래처명", "")),
        str(r.get("명세서번호", "")), str(r.get("명세서일자", "")), _int(r.get("운송비", 0)),
        str(r.get("운송비입력여부", "")), str(r.get("메모", "")), str(r.get("등록일시", "")),
        str(r.get("수정일시", "")),
    ) for _, r in clean.iterrows() if str(r.get("명세서ID", "")).strip()]
    with transaction(data_dir) as conn:
        conn.execute("DELETE FROM statements")
        conn.executemany("""
            INSERT INTO statements(statement_id,order_id,vendor_name,statement_number,statement_date,
            freight,freight_entered,memo,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)
        """, rows)


def replace_statement_items(data_dir: Path, df: pd.DataFrame) -> None:
    clean = df.copy().fillna("")
    rows = [(
        str(r.get("명세서ID", "")), _int(r.get("순번", 0)), normalize_product_code(r.get("제품코드", "")),
        str(r.get("정식제품명", "")), str(r.get("규격", "")), str(r.get("단위", "")),
        _int(r.get("발주수량", 0)), _int(r.get("입고수량", 0)), _int(r.get("매입단가", 0)),
        _int(r.get("상품금액", 0)), _int(r.get("출고단가", 0)), str(r.get("가격적용여부", "")),
        normalize_product_code(r.get("원발주제품코드", "")), str(r.get("원발주제품명", "")),
        str(r.get("원발주규격", "")), str(r.get("원발주단위", "")),
        str(r.get("입고유형", "")), str(r.get("대체사유", "")),
        str(r.get("제조번호", "")), str(r.get("유통기한", "")),
    ) for _, r in clean.iterrows() if str(r.get("명세서ID", "")).strip()]
    with transaction(data_dir) as conn:
        _ensure_substitution_columns(conn)
        conn.execute("DELETE FROM statement_items")
        conn.executemany("""
            INSERT INTO statement_items(statement_id,sequence,product_code,product_name,specification,
            packaging_unit,ordered_quantity,received_quantity,purchase_price,product_amount,sale_price,
            apply_price,original_product_code,original_product_name,original_specification,
            original_packaging_unit,receipt_type,substitution_reason,lot_number,expiry_date)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, rows)


def replace_price_history(data_dir: Path, df: pd.DataFrame) -> None:
    clean = df.copy().fillna("")
    rows = [(
        str(r.get("가격ID", "")), str(r.get("명세서ID", "")), str(r.get("명세서일자", "")),
        normalize_product_code(r.get("제품코드", "")), str(r.get("정식제품명", "")),
        _int(r.get("매입단가", 0)), _int(r.get("출고단가", 0)), str(r.get("등록일시", "")),
    ) for _, r in clean.iterrows()]
    with transaction(data_dir) as conn:
        conn.execute("DELETE FROM price_history")
        conn.executemany("""
            INSERT INTO price_history(price_id,statement_id,statement_date,product_code,product_name,
            purchase_price,sale_price,created_at) VALUES(?,?,?,?,?,?,?,?)
        """, rows)


def replace_monthly_closes(data_dir: Path, df: pd.DataFrame) -> None:
    clean = df.copy().fillna("")
    rows = [(
        str(r.get("마감월", "")), _int(r.get("상품매입금액", 0)), _int(r.get("운송비", 0)),
        _int(r.get("총매입금액", 0)), _int(r.get("거래명세서수", 0)),
        str(r.get("등록일시", "")), str(r.get("메모", "")),
    ) for _, r in clean.iterrows() if str(r.get("마감월", "")).strip()]
    with transaction(data_dir) as conn:
        conn.execute("DELETE FROM monthly_closes")
        conn.executemany("""
            INSERT INTO monthly_closes(close_month,product_purchase_amount,freight,total_purchase_amount,
            statement_count,created_at,memo) VALUES(?,?,?,?,?,?,?)
        """, rows)
