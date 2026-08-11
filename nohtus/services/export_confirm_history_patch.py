from __future__ import annotations

from datetime import datetime

import nohtus.services.export_waiting as export_waiting
from nohtus.db import connect
from nohtus.services.inventory import insert_transaction_log


_original_update_confirmed_export_waiting_items = export_waiting.update_confirmed_export_waiting_items


def _patched_update_confirmed_export_waiting_items(
    order_id,
    item_ids,
    *,
    erp_company,
    customer_code,
    customer_name,
    shipment_date,
):
    """확정 출고정보 수정 뒤 새 출고지시 이력도 다시 남긴다.

    기존 수정 흐름에서 이전 출고 이력 취소가 기록되더라도, 수정 저장된 값이
    이력조회에서 다시 검색될 수 있도록 선택 품목별 출고지시 이력을 추가한다.
    재고는 이미 확정 시 차감되었으므로 여기서는 재고 수량을 다시 변경하지 않는다.
    """
    result = _original_update_confirmed_export_waiting_items(
        order_id,
        item_ids,
        erp_company=erp_company,
        customer_code=customer_code,
        customer_name=customer_name,
        shipment_date=shipment_date,
    )

    selected_ids = sorted({int(x) for x in (item_ids or [])})
    if not selected_ids:
        return result

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    order_date = str(result.get("order_date") or shipment_date or "")[:10]
    placeholders = ",".join("?" for _ in selected_ids)
    with connect() as con:
        cur = con.cursor()
        order = cur.execute(
            "SELECT title,export_no FROM export_waiting_orders WHERE id=?",
            (int(order_id),),
        ).fetchone()
        rows = cur.execute(
            f"""SELECT product_name,warehouse_name,lot,exp_date,company,qty
                FROM export_waiting_items
                WHERE order_id=? AND id IN ({placeholders})
                  AND COALESCE(confirmed,0)=1
                ORDER BY id""",
            (int(order_id), *selected_ids),
        ).fetchall()
        title = str(order[0] or "") if order else ""
        export_no = str(order[1] or "") if order else ""
        for product_name, warehouse_name, lot, exp_date, company, qty in rows:
            insert_transaction_log(
                cur,
                created_at=now,
                tx_type="출고지시",
                product_name=product_name,
                warehouse_name=warehouse_name,
                lot=lot,
                exp_date=exp_date,
                from_company=company,
                from_location="P",
                to_company=str(erp_company or "").strip(),
                to_location="",
                qty=int(qty or 0),
                memo=(
                    f"수출확정 출고내역 수정 저장 / {title} / {customer_name} / "
                    f"수출번호: {export_no} / 출고일자: {order_date}"
                ),
            )
        con.commit()
    return result


export_waiting.update_confirmed_export_waiting_items = _patched_update_confirmed_export_waiting_items
