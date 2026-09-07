"""발주서와 연결 거래명세서를 한 트랜잭션으로 수정하는 저장소."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil

import pandas as pd

from app_layers.db_migration import normalize_product_code
from infrastructure.database import transaction


def _int(value) -> int:
    try:
        return int(float(str(value or "0").replace(",", "")))
    except (TypeError, ValueError):
        return 0


def _text(value) -> str:
    return str(value if value is not None else "").strip()


def _backup_database(data_dir: Path) -> Path:
    data_dir = Path(data_dir)
    source = data_dir / "purchase_order.db"
    backup_dir = data_dir / "correction_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    target = backup_dir / f"purchase_order_before_correction_{stamp}.db"
    shutil.copy2(source, target)
    return target


def save_bundle(
    data_dir: Path,
    order_id: str,
    order_header: dict,
    order_items: pd.DataFrame,
    statements: pd.DataFrame,
    statement_items: pd.DataFrame,
) -> None:
    """선택한 발주와 연결 명세서를 전부 교체합니다.

    모든 변경은 하나의 SQLite 트랜잭션에서 처리되어 중간 상태가 남지 않습니다.
    """
    order_id = _text(order_id)
    if not order_id:
        raise ValueError("수정할 발주ID가 없습니다.")

    clean_order_items = order_items.copy().fillna("")
    clean_order_items = clean_order_items[
        clean_order_items.get("정식제품명", pd.Series(dtype=str)).astype(str).str.strip() != ""
    ].reset_index(drop=True)
    if clean_order_items.empty:
        raise ValueError("발주 품목을 한 개 이상 입력하세요.")

    clean_statements = statements.copy().fillna("")
    if not clean_statements.empty:
        clean_statements["명세서ID"] = clean_statements["명세서ID"].astype(str).str.strip()
        if (clean_statements["명세서ID"] == "").any():
            raise ValueError("명세서ID는 비워둘 수 없습니다.")
        if clean_statements["명세서ID"].duplicated().any():
            raise ValueError("중복된 명세서ID가 있습니다.")

    valid_statement_ids = set(clean_statements.get("명세서ID", pd.Series(dtype=str)).astype(str))
    clean_statement_items = statement_items.copy().fillna("")
    if not clean_statement_items.empty:
        clean_statement_items["명세서ID"] = clean_statement_items["명세서ID"].astype(str).str.strip()
        unknown = set(clean_statement_items["명세서ID"]) - valid_statement_ids
        if unknown:
            raise ValueError(f"존재하지 않는 명세서ID를 사용하는 품목이 있습니다: {', '.join(sorted(unknown))}")
        clean_statement_items = clean_statement_items[
            clean_statement_items.get("정식제품명", pd.Series(dtype=str)).astype(str).str.strip() != ""
        ].reset_index(drop=True)

    ordered_at = pd.to_datetime(order_header.get("발주일시"), errors="coerce")
    if pd.isna(ordered_at):
        raise ValueError("올바른 발주일자를 입력하세요.")
    vendor_name = _text(order_header.get("거래처명"))
    if not vendor_name:
        raise ValueError("거래처를 선택하세요.")

    total_quantity = sum(_int(value) for value in clean_order_items["수량"])
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    _backup_database(data_dir)
    with transaction(data_dir) as conn:
        existing = conn.execute(
            "SELECT 1 FROM orders WHERE order_id = ?", (order_id,)
        ).fetchone()
        if existing is None:
            raise ValueError(f"발주서를 찾을 수 없습니다: {order_id}")

        old_statement_ids = [
            row[0]
            for row in conn.execute(
                "SELECT statement_id FROM statements WHERE order_id = ?", (order_id,)
            ).fetchall()
        ]
        if old_statement_ids:
            placeholders = ",".join("?" for _ in old_statement_ids)
            conn.execute(
                f"DELETE FROM price_history WHERE statement_id IN ({placeholders})",
                old_statement_ids,
            )
            conn.execute(
                f"DELETE FROM statement_items WHERE statement_id IN ({placeholders})",
                old_statement_ids,
            )
        conn.execute("DELETE FROM statements WHERE order_id = ?", (order_id,))
        conn.execute("DELETE FROM order_items WHERE order_id = ?", (order_id,))

        conn.execute(
            """
            UPDATE orders SET ordered_at=?, vendor_name=?, request_note=?, status=?,
                total_item_count=?, total_quantity=? WHERE order_id=?
            """,
            (
                ordered_at.strftime("%Y-%m-%d %H:%M:%S"),
                vendor_name,
                _text(order_header.get("요청사항")),
                _text(order_header.get("상태")) or "발주완료",
                len(clean_order_items),
                total_quantity,
                order_id,
            ),
        )

        order_rows = []
        for sequence, (_, row) in enumerate(clean_order_items.iterrows(), 1):
            order_rows.append((
                order_id, sequence, normalize_product_code(row.get("제품코드", "")),
                _text(row.get("정식제품명")), _text(row.get("검색별칭")),
                _text(row.get("규격")), _text(row.get("단위")), _int(row.get("수량")),
            ))
        conn.executemany(
            """INSERT INTO order_items(order_id,sequence,product_code,product_name,
            search_alias,specification,packaging_unit,quantity) VALUES(?,?,?,?,?,?,?,?)""",
            order_rows,
        )

        statement_dates = {}
        statement_rows = []
        for _, row in clean_statements.iterrows():
            statement_id = _text(row.get("명세서ID"))
            statement_date = pd.to_datetime(row.get("명세서일자"), errors="coerce")
            if pd.isna(statement_date):
                raise ValueError(f"{statement_id}의 명세서일자가 올바르지 않습니다.")
            date_text = statement_date.strftime("%Y-%m-%d")
            statement_dates[statement_id] = date_text
            statement_rows.append((
                statement_id, order_id, vendor_name, _text(row.get("명세서번호")),
                date_text, _int(row.get("운송비")), _text(row.get("운송비입력여부")),
                _text(row.get("메모")), _text(row.get("등록일시")) or now, now,
            ))
        if statement_rows:
            conn.executemany(
                """INSERT INTO statements(statement_id,order_id,vendor_name,statement_number,
                statement_date,freight,freight_entered,memo,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?)""",
                statement_rows,
            )

        item_rows = []
        price_rows = []
        sequence_by_statement: dict[str, int] = {}
        for _, row in clean_statement_items.iterrows():
            statement_id = _text(row.get("명세서ID"))
            sequence_by_statement[statement_id] = sequence_by_statement.get(statement_id, 0) + 1
            sequence = sequence_by_statement[statement_id]
            quantity = _int(row.get("입고수량"))
            purchase_price = _int(row.get("매입단가"))
            apply_price = _text(row.get("가격적용여부")) or "N"
            amount = (
                _int(row.get("상품금액"))
                if apply_price.startswith("반품:")
                else quantity * purchase_price
            )
            sale_price = _int(row.get("출고단가"))
            item_rows.append((
                statement_id, sequence, normalize_product_code(row.get("제품코드", "")),
                _text(row.get("정식제품명")), _text(row.get("규격")), _text(row.get("단위")),
                _int(row.get("발주수량")), quantity, purchase_price, amount, sale_price,
                apply_price, normalize_product_code(row.get("원발주제품코드", "")),
                _text(row.get("원발주제품명")), _text(row.get("원발주규격")),
                _text(row.get("원발주단위")), _text(row.get("입고유형")),
                _text(row.get("대체사유")), _text(row.get("제조번호")),
                _text(row.get("유통기한")),
            ))
            if apply_price.upper() == "Y":
                price_rows.append((
                    f"PR-CORR-{statement_id}-{sequence}", statement_id,
                    statement_dates[statement_id], normalize_product_code(row.get("제품코드", "")),
                    _text(row.get("정식제품명")), purchase_price, sale_price, now,
                ))
        if item_rows:
            conn.executemany(
                """INSERT INTO statement_items(statement_id,sequence,product_code,product_name,
                specification,packaging_unit,ordered_quantity,received_quantity,purchase_price,
                product_amount,sale_price,apply_price,original_product_code,original_product_name,
                original_specification,original_packaging_unit,receipt_type,substitution_reason,
                lot_number,expiry_date) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                item_rows,
            )
        if price_rows:
            conn.executemany(
                """INSERT INTO price_history(price_id,statement_id,statement_date,product_code,
                product_name,purchase_price,sale_price,created_at) VALUES(?,?,?,?,?,?,?,?)""",
                price_rows,
            )
