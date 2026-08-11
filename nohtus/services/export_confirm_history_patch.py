from __future__ import annotations

from datetime import date, datetime

import nohtus.services.export_waiting as export_waiting
from nohtus.db import connect
from nohtus.services.inventory import insert_transaction_log


_original_update_confirmed_export_waiting_items = export_waiting.update_confirmed_export_waiting_items


def _date_text(value) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    return str(value or "").strip()[:10]


def _patched_update_confirmed_export_waiting_items(
    order_id,
    item_ids,
    *,
    erp_company,
    customer_code,
    customer_name,
    shipment_date,
):
    """확정 출고정보 수정 시 실제로 값이 바뀐 품목만 취소/재등록 이력을 남긴다.

    화면에서 여러 품목을 선택했더라도 ERP 사업장·매출처·출고일자가 기존과
    같은 품목은 이력을 만들지 않는다. 변경된 품목만 기존 출고지시취소 이력을
    남긴 뒤 수정 저장된 값으로 출고지시 이력을 다시 기록한다. 재고 수량은
    변경하지 않는다.
    """
    selected_ids = sorted({int(x) for x in (item_ids or [])})
    if not selected_ids:
        return _original_update_confirmed_export_waiting_items(
            order_id,
            item_ids,
            erp_company=erp_company,
            customer_code=customer_code,
            customer_name=customer_name,
            shipment_date=shipment_date,
        )

    requested_company = str(erp_company or "").strip()
    requested_code = str(customer_code or "").strip()
    requested_customer = str(customer_name or "").strip()
    requested_date = _date_text(shipment_date)
    placeholders = ",".join("?" for _ in selected_ids)

    # 수정 전 값을 먼저 보존한다. 선택되었다는 이유만으로 취소 이력을 만들지 않고,
    # 실제 값이 달라진 품목 ID만 changed_ids에 넣는다.
    with connect() as con:
        cur = con.cursor()
        order = cur.execute(
            "SELECT title,export_no,order_date FROM export_waiting_orders WHERE id=?",
            (int(order_id),),
        ).fetchone()
        rows = cur.execute(
            f"""SELECT id,product_name,warehouse_name,lot,exp_date,company,qty,
                       confirmed_company,confirmed_customer_code,
                       confirmed_customer_name,confirmed_at
                FROM export_waiting_items
                WHERE order_id=? AND id IN ({placeholders})
                  AND COALESCE(confirmed,0)=1
                ORDER BY id""",
            (int(order_id), *selected_ids),
        ).fetchall()

    old_order_date = _date_text(order[2]) if order else ""
    before_by_id = {}
    changed_ids = []
    for row in rows:
        (
            item_id, product_name, warehouse_name, lot, exp_date, company, qty,
            old_company, old_code, old_customer, old_confirmed_at,
        ) = row
        old_item_date = _date_text(old_confirmed_at) or old_order_date
        before_by_id[int(item_id)] = {
            "product_name": product_name,
            "warehouse_name": warehouse_name,
            "lot": lot,
            "exp_date": exp_date,
            "company": company,
            "qty": int(qty or 0),
            "confirmed_company": str(old_company or "").strip(),
            "confirmed_customer_code": str(old_code or "").strip(),
            "confirmed_customer_name": str(old_customer or "").strip(),
            "order_date": old_item_date,
        }
        if (
            str(old_company or "").strip() != requested_company
            or str(old_code or "").strip() != requested_code
            or str(old_customer or "").strip() != requested_customer
            or old_item_date != requested_date
        ):
            changed_ids.append(int(item_id))

    result = _original_update_confirmed_export_waiting_items(
        order_id,
        item_ids,
        erp_company=erp_company,
        customer_code=customer_code,
        customer_name=customer_name,
        shipment_date=shipment_date,
    )

    if not changed_ids:
        return result

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    new_order_date = str(result.get("order_date") or requested_date)[:10]
    title = str(order[0] or "") if order else ""
    export_no = str(order[1] or "") if order else ""

    with connect() as con:
        cur = con.cursor()
        changed_placeholders = ",".join("?" for _ in changed_ids)
        after_rows = cur.execute(
            f"""SELECT id,product_name,warehouse_name,lot,exp_date,company,qty
                FROM export_waiting_items
                WHERE order_id=? AND id IN ({changed_placeholders})
                  AND COALESCE(confirmed,0)=1
                ORDER BY id""",
            (int(order_id), *changed_ids),
        ).fetchall()

        # 기존 값 취소 이력: 실제 변경이 있는 품목만 기록한다.
        for item_id in changed_ids:
            before = before_by_id.get(item_id)
            if not before:
                continue
            insert_transaction_log(
                cur,
                created_at=now,
                tx_type="출고지시취소",
                product_name=before["product_name"],
                warehouse_name=before["warehouse_name"],
                lot=before["lot"],
                exp_date=before["exp_date"],
                from_company=before["confirmed_company"] or before["company"],
                from_location="",
                to_company=before["company"],
                to_location="P",
                qty=before["qty"],
                memo=(
                    f"수출확정 출고내역 수정 / 기존 출고지시 취소 / {title} / "
                    f"{before['confirmed_customer_name']} / 수출번호: {export_no} / "
                    f"출고일자: {before['order_date']}"
                ),
            )

        # 수정 저장 값 재등록 이력도 같은 변경 품목만 기록한다.
        for item_id, product_name, warehouse_name, lot, exp_date, company, qty in after_rows:
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
                to_company=requested_company,
                to_location="",
                qty=int(qty or 0),
                memo=(
                    f"수출확정 출고내역 수정 저장 / {title} / {requested_customer} / "
                    f"수출번호: {export_no} / 출고일자: {new_order_date}"
                ),
            )
        con.commit()
    return result


export_waiting.update_confirmed_export_waiting_items = _patched_update_confirmed_export_waiting_items
