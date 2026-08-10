"""EXPORT 주문품목에 고른 실재고를 WMS 수출대기(export_waiting_orders/items)에
실제로 반영하고, 그 결과를 EXPORT의 shipment_items에 미러링한다.

nohtus.services.export_waiting.save_export_waiting_order()는 editing_order_id로
기존 건을 수정할 때 "현재 미확정 품목 전체"를 넘긴 cart로 통째로 교체한다(부분
추가가 아님). 그래서 이 케이스의 다른 주문품목에 이미 연결된 실재고까지 항상
함께 담아서 호출해야, 그 연결이 조용히 원위치로 복원되는 사고를 막을 수 있다.
"""
from __future__ import annotations

from nohtus.db import q as wms_q
from nohtus.export_app.services import export_service, shipment_service
from nohtus.services.export_waiting import save_export_waiting_order

TRANSPORT_MODE_TO_METHOD = {
    "AIR": "항공",
    "SEA": "해상",
    "HAND": "핸드캐리",
    "미지정": "미지정",
}


def _find_open_order_id(export_no: str) -> int | None:
    df = wms_q(
        """SELECT id FROM export_waiting_orders
           WHERE TRIM(export_no)=TRIM(?) AND status IN ('waiting','partial')
           ORDER BY id LIMIT 1""",
        (export_no,),
    )
    if df.empty:
        return None
    return int(df.iloc[0]["id"])


def _cart_row_from_shipment_row(row: dict) -> dict:
    return {
        "id": int(row["source_inventory_id"] or 0),
        "요청수량": float(row["requested_qty"] or 0),
        "사업장": row.get("business_unit") or "",
        "제품명": row.get("product_name") or "",
        "LOT": row.get("lot_no") or "",
        "유통기한": row.get("expiry_date") or "",
        "로케이션": row.get("source_location") or "",
    }


def _cart_row_from_pick(pick: dict) -> dict:
    return {
        "id": int(pick["inventory_id"]),
        "요청수량": float(pick["qty"]),
        "사업장": pick.get("company") or "",
        "제품명": pick.get("product_name") or "",
        "LOT": pick.get("lot") or "",
        "유통기한": pick.get("exp_date") or "",
        "로케이션": pick.get("location") or "",
    }


def save_picked_inventory(
    *,
    case_id: int,
    order_item_id: int,
    kept_rows: list[dict],
    picked_rows: list[dict],
) -> dict:
    """kept_rows: 이번 주문품목에서 계속 유지할, 이미 저장된 shipment_items 행
    (shipment_service.list_case_items()가 반환하는 형태 — id/business_unit/
    source_location/source_inventory_id/product_name/lot_no/expiry_date/
    requested_qty 키를 가짐). picked_rows: 새로 담은 실재고 행
    (wms_inventory_picker_service 조회 결과를 기반으로 만든 dict,
    inventory_id/company/product_name/lot/exp_date/location/qty 키를 가짐)."""
    case = export_service.get_case(case_id)
    if case is None:
        raise ValueError("수출 건을 찾을 수 없습니다.")
    export_no = str(case["export_no"] or "").strip()
    if not export_no:
        raise ValueError("이 수출 건에는 수출번호가 없습니다.")
    country = str(case["country"] or "").strip()
    if not country:
        raise ValueError("이 수출 건에는 국가가 입력되어 있지 않습니다. 먼저 국가를 입력하세요.")
    transport_method = TRANSPORT_MODE_TO_METHOD.get(str(case["transport_mode"] or "").strip(), "미지정")

    other_rows = [
        row for row in shipment_service.list_case_items(case_id)
        if int(row["order_item_id"] or 0) != int(order_item_id) and row.get("source_inventory_id")
    ]
    # source_inventory_id가 없는 행은 실재고 연결 이전(수동 입력/구형 불러오기)의
    # 데이터라 WMS cart로 되돌릴 실제 재고가 없다 — cart에서는 제외한다.
    kept_rows = [row for row in kept_rows if row.get("source_inventory_id")]
    cart = [_cart_row_from_shipment_row(row) for row in other_rows]
    cart += [_cart_row_from_shipment_row(row) for row in kept_rows]
    cart += [_cart_row_from_pick(pick) for pick in picked_rows]

    editing_order_id = _find_open_order_id(export_no)
    result = save_export_waiting_order(
        cart,
        country=country,
        buyer=str(case.get("buyer") or ""),
        transport_method=transport_method,
        export_no=export_no,
        editing_order_id=editing_order_id,
    )

    mirror_rows = [
        {
            "_id": row["id"],
            "business_unit": row.get("business_unit") or "",
            "location": row.get("source_location") or "",
            "source_inventory_id": row.get("source_inventory_id"),
            "product_name": row.get("product_name") or "",
            "lot_no": row.get("lot_no") or "",
            "expiry_date": row.get("expiry_date") or "",
            "requested_qty": float(row["requested_qty"] or 0),
        }
        for row in kept_rows
    ]
    mirror_rows += [
        {
            "_id": None,
            "business_unit": pick.get("company") or "",
            "location": pick.get("location") or "",
            "source_inventory_id": int(pick["inventory_id"]),
            "product_name": pick.get("product_name") or "",
            "lot_no": pick.get("lot") or "",
            "expiry_date": pick.get("exp_date") or "",
            "requested_qty": float(pick["qty"]),
        }
        for pick in picked_rows
    ]
    total_qty = shipment_service.save_for_order(case_id, order_item_id, mirror_rows)

    return {"order_id": result["order_id"], "total_qty": total_qty, "row_count": len(mirror_rows)}
