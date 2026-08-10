"""WMS 수출대기 데이터를 실출고 입력으로 불러오는 서비스.

WMS와 EXPORT가 같은 프로세스로 합쳐지기 전에는 사용자가 지정한 WMS DB
파일을 읽기전용으로 열어서 데이터를 가져왔다. 이제는 같은 프로세스이므로
WMS 자체 서비스 계층의 DB 접근 함수를 그대로 호출한다 — 경로 설정,
파일 존재 확인, 읽기전용 연결이 전부 필요 없어졌다.
"""
from __future__ import annotations

from nohtus.db import q as wms_q
from nohtus.export_app import db
from nohtus.export_app.services import product_name_match_service, shipment_service
from nohtus.export_app.utils.dates import now_text


def _wms_rows(export_no: str) -> list[dict]:
    df = wms_q(
        """SELECT i.id AS wms_item_id,i.company,i.product_name,i.lot,i.exp_date,i.qty,
                  o.id AS wms_order_id,o.status,o.updated_at
           FROM export_waiting_orders o
           JOIN export_waiting_items i ON i.order_id=o.id
           WHERE TRIM(o.export_no)=TRIM(?) AND COALESCE(o.status,'')<>'cancelled'
           ORDER BY o.id,i.id""",
        (export_no,),
    )
    return df.to_dict("records")


def preview(case_id: int) -> dict:
    case = db.row("SELECT export_no FROM export_cases WHERE id=?", (int(case_id),))
    if not case:
        raise ValueError("수출 건을 찾을 수 없습니다.")
    orders = db.rows(
        "SELECT id,product_name,quantity,unit FROM order_items WHERE case_id=? ORDER BY id",
        (int(case_id),),
    )
    normalized_orders: dict[str, list] = {}
    for order in orders:
        key = product_name_match_service.normalize_for_match(str(order["product_name"] or ""))
        normalized_orders.setdefault(key, []).append(order)

    rows = []
    matched_by_order: dict[int, list[dict]] = {}
    for item in _wms_rows(str(case["export_no"] or "")):
        key = product_name_match_service.normalize_for_match(str(item["product_name"] or ""))
        candidates = normalized_orders.get(key, [])
        if len(candidates) == 1:
            order = candidates[0]
            status = "일치"
            order_item_id = int(order["id"])
            order_name = str(order["product_name"] or "")
            matched_by_order.setdefault(order_item_id, []).append({
                "business_unit": item["company"] or "",
                "product_name": item["product_name"] or "",
                "lot_no": item["lot"] or "",
                "expiry_date": item["exp_date"] or "",
                "requested_qty": float(item["qty"] or 0),
            })
        elif len(candidates) > 1:
            status, order_item_id, order_name = "주문 중복", None, ""
        else:
            status, order_item_id, order_name = "주문에 없음", None, ""
        rows.append({
            "매칭상태": status,
            "주문제품": order_name,
            "WMS 표준제품명": item["product_name"] or "",
            "사업장": item["company"] or "",
            "제조번호": item["lot"] or "",
            "유통기한": item["exp_date"] or "",
            "수량": float(item["qty"] or 0),
            "_order_item_id": order_item_id,
        })

    order_totals = {int(order["id"]): float(order["quantity"] or 0) for order in orders}
    differences = []
    for order in orders:
        order_id = int(order["id"])
        imported = sum(float(row["requested_qty"]) for row in matched_by_order.get(order_id, []))
        ordered = order_totals[order_id]
        if abs(imported - ordered) > 0.000001:
            differences.append({
                "주문제품": order["product_name"],
                "주문수량": ordered,
                "WMS 수출대기": imported,
                "차이": imported - ordered,
            })
    return {
        "rows": rows,
        "matched_by_order": matched_by_order,
        "differences": differences,
        "order_ids": [int(order["id"]) for order in orders],
    }


def apply(case_id: int) -> dict:
    result = preview(case_id)
    unmatched = [row for row in result["rows"] if row["매칭상태"] != "일치"]
    if unmatched:
        raise ValueError("주문과 자동 매칭되지 않은 WMS 품목이 있어 불러올 수 없습니다.")
    for order_item_id in result["order_ids"]:
        rows = result["matched_by_order"].get(order_item_id, [])
        shipment_service.save_for_order(int(case_id), int(order_item_id), rows)
    db.execute("UPDATE export_cases SET updated_at=? WHERE id=?", (now_text(), int(case_id)))
    return {
        "row_count": len(result["rows"]),
        "order_count": len(result["matched_by_order"]),
        "difference_count": len(result["differences"]),
    }
