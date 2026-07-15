from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from nohtus.db import connect
from nohtus.services.inventory import insert_transaction_log


EXPORT_WAITING_LOCATION = "P"


def move_cart_to_export_waiting(cart, *, title="", customer_name=""):
    """출고 장바구니의 재고를 같은 사업장 내 수출대기 위치 P로 원자적으로 이동한다."""
    grouped = defaultdict(int)
    for item in cart or []:
        try:
            inventory_id = int(item.get("id"))
            qty = int(item.get("요청수량") or 0)
        except Exception as exc:
            raise ValueError("수출대기 등록 품목 정보가 올바르지 않습니다.") from exc
        if qty <= 0:
            continue
        grouped[inventory_id] += qty

    if not grouped:
        raise ValueError("수출대기 등록할 품목이 없습니다.")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    customer_name = str(customer_name or "").strip()
    title = str(title or "").strip()
    memo_parts = ["수출대기 등록"]
    if customer_name:
        memo_parts.append(f"매출처: {customer_name}")
    if title:
        memo_parts.append(f"제목: {title}")
    memo = " / ".join(memo_parts)

    with connect() as con:
        cur = con.cursor()
        inventory_columns = {row[1] for row in cur.execute("PRAGMA table_info(inventory)").fetchall()}
        has_shippable = "is_shippable" in inventory_columns

        source_rows = {}
        for inventory_id, qty in grouped.items():
            raw = cur.execute("SELECT * FROM inventory WHERE id=?", (inventory_id,)).fetchone()
            if not raw:
                raise ValueError(f"재고 #{inventory_id}를 찾을 수 없습니다. 화면을 새로고침한 뒤 다시 선택하세요.")
            columns = [description[0] for description in cur.description]
            source = dict(zip(columns, raw))
            available = int(source.get("qty") or 0)
            if qty > available:
                raise ValueError(
                    f"{source.get('product_name', '제품')} 재고가 부족합니다. "
                    f"요청 {qty}EA / 현재 {available}EA"
                )
            if str(source.get("location") or "").strip() == EXPORT_WAITING_LOCATION:
                raise ValueError(f"{source.get('product_name', '제품')}은 이미 수출대기 위치 P에 있습니다.")
            source_rows[inventory_id] = source

        total_qty = 0
        for inventory_id, qty in grouped.items():
            source = source_rows[inventory_id]
            remaining = int(source.get("qty") or 0) - qty
            cur.execute(
                "UPDATE inventory SET qty=?, updated_at=? WHERE id=?",
                (remaining, now, inventory_id),
            )

            destination_query = """
                SELECT id, qty
                FROM inventory
                WHERE company=?
                  AND product_name=?
                  AND IFNULL(warehouse_name,'')=?
                  AND IFNULL(lot,'-')=?
                  AND IFNULL(exp_date,'-')=?
                  AND location=?
            """
            destination_params = (
                source.get("company", ""),
                source.get("product_name", ""),
                source.get("warehouse_name", "") or "",
                source.get("lot", "-") or "-",
                source.get("exp_date", "-") or "-",
                EXPORT_WAITING_LOCATION,
            )
            destination = cur.execute(destination_query, destination_params).fetchone()

            if destination:
                if has_shippable:
                    cur.execute(
                        "UPDATE inventory SET qty=?, updated_at=?, is_shippable=0 WHERE id=?",
                        (int(destination[1] or 0) + qty, now, int(destination[0])),
                    )
                else:
                    cur.execute(
                        "UPDATE inventory SET qty=?, updated_at=? WHERE id=?",
                        (int(destination[1] or 0) + qty, now, int(destination[0])),
                    )
            elif has_shippable:
                cur.execute(
                    """
                    INSERT INTO inventory(
                        company, product_name, warehouse_name, lot, exp_date,
                        location, qty, updated_at, is_shippable
                    ) VALUES(?,?,?,?,?,?,?,?,0)
                    """,
                    (
                        source.get("company", ""),
                        source.get("product_name", ""),
                        source.get("warehouse_name", "") or "",
                        source.get("lot", "-") or "-",
                        source.get("exp_date", "-") or "-",
                        EXPORT_WAITING_LOCATION,
                        qty,
                        now,
                    ),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO inventory(
                        company, product_name, warehouse_name, lot, exp_date,
                        location, qty, updated_at
                    ) VALUES(?,?,?,?,?,?,?,?)
                    """,
                    (
                        source.get("company", ""),
                        source.get("product_name", ""),
                        source.get("warehouse_name", "") or "",
                        source.get("lot", "-") or "-",
                        source.get("exp_date", "-") or "-",
                        EXPORT_WAITING_LOCATION,
                        qty,
                        now,
                    ),
                )

            insert_transaction_log(
                cur,
                created_at=now,
                tx_type="위치이동",
                product_name=source.get("product_name", ""),
                warehouse_name=source.get("warehouse_name", "") or "",
                lot=source.get("lot", "-") or "-",
                exp_date=source.get("exp_date", "-") or "-",
                from_company=source.get("company", ""),
                from_location=source.get("location", ""),
                to_company=source.get("company", ""),
                to_location=EXPORT_WAITING_LOCATION,
                qty=qty,
                memo=memo,
            )
            total_qty += qty

        con.commit()

    return {"row_count": len(grouped), "total_qty": total_qty}
