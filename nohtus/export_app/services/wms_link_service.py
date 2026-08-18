"""EXPORT 주문품목에 고른 실재고를 WMS 수출대기(export_waiting_orders/items)에
실제로 반영하고, 그 결과를 EXPORT의 shipment_items에 미러링한다.

nohtus.services.export_waiting.save_export_waiting_order()는 editing_order_id로
기존 건을 수정할 때 "현재 미확정 품목 전체"를 넘긴 cart로 통째로 교체한다(부분
추가가 아님). 그래서 이 케이스의 다른 주문품목에 이미 연결된 실재고까지 항상
함께 담아서 호출해야, 그 연결이 조용히 원위치로 복원되는 사고를 막을 수 있다.
"""
from __future__ import annotations

import re

from nohtus.db import q as wms_q
from nohtus.export_app import db as export_db
from nohtus.export_app.services import export_service, shipment_service
from nohtus.export_app.utils.dates import now_text
from nohtus.services.export_waiting import repair_p_inventory_links, save_export_waiting_order

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
           ORDER BY id""",
        (export_no,),
    )
    if df.empty:
        return None
    if len(df.index) > 1:
        raise ValueError(
            f"수출번호 {export_no}에 진행 중인 수출대기 건이 여러 개입니다. "
            "기존 건을 하나로 병합하거나 새 수출번호를 사용하세요."
        )
    return int(df.iloc[0]["id"])


def _linkable_order_ids(export_no: str) -> list[int]:
    df = wms_q(
        """SELECT id FROM export_waiting_orders
           WHERE TRIM(export_no)=TRIM(?)
             AND status IN ('waiting','partial','confirmed')
           ORDER BY id""",
        (export_no,),
    )
    return [int(value) for value in df["id"].tolist()] if not df.empty else []


def _match_text(value: object) -> str:
    return "".join(str(value or "").split("(", 1)[0].split()).casefold()


def _match_value(value: object) -> str:
    return "".join(str(value or "").split()).casefold()


def _match_date(value: object) -> str:
    parts = re.findall(r"\d+", str(value or ""))
    if len(parts) == 3:
        return f"{int(parts[0]):04d}{int(parts[1]):02d}{int(parts[2]):02d}"
    return "".join(parts)


def _same_quantity(left: object, right: object) -> bool:
    return abs(float(left or 0) - float(right or 0)) <= 0.000001


def _matching_legacy_rows(rows: list[dict], waiting_row: dict, order_item_id: int) -> list[dict]:
    product_key = _match_text(waiting_row.get("product_name"))
    company_key = _match_value(waiting_row.get("company"))
    lot_key = _match_value(waiting_row.get("lot"))
    expiry_key = _match_date(waiting_row.get("exp_date"))
    candidates = []
    for row in rows:
        if row.get("source_inventory_id"):
            continue
        if int(row.get("order_item_id") or 0) != int(order_item_id):
            continue
        row_product_key = _match_text(row.get("product_name"))
        if not product_key or not row_product_key or not (
            row_product_key == product_key or row_product_key in product_key or product_key in row_product_key
        ):
            continue
        row_company_key = _match_value(row.get("business_unit"))
        if row_company_key and company_key and row_company_key != company_key:
            continue
        if _match_value(row.get("lot_no")) != lot_key:
            continue
        if _match_date(row.get("expiry_date")) != expiry_key:
            continue
        candidates.append(row)
    if not candidates:
        return []
    total = sum(float(row.get("requested_qty") or 0) for row in candidates)
    return candidates if _same_quantity(total, waiting_row.get("qty")) else []


def _update_legacy_rows(rows: list[dict], waiting_row: dict, source_id: int, now: str) -> None:
    export_db.executemany(
        """UPDATE shipment_items
           SET business_unit=?, location=?, source_inventory_id=?, product_name=?,
               lot_no=?, expiry_date=?, updated_at=?
           WHERE id=?""",
        [(str(waiting_row.get("company") or ""), str(waiting_row.get("source_location") or ""), source_id,
          str(waiting_row.get("product_name") or ""), str(waiting_row.get("lot") or ""),
          str(waiting_row.get("exp_date") or ""), now, int(row["id"])) for row in rows],
    )


def restore_legacy_waiting_links(case_id: int) -> int:
    case = export_service.get_case(case_id)
    if case is None:
        return 0
    export_no = str(case.get("export_no") or "").strip()
    if not export_no:
        return 0
    order_ids = _linkable_order_ids(export_no)
    if not order_ids:
        return 0
    open_orders = wms_q(
        """SELECT id FROM export_waiting_orders WHERE id IN ({}) AND status IN ('waiting','partial')""".format(
            ",".join("?" for _ in order_ids)), tuple(order_ids))
    for order_id in open_orders["id"].tolist() if not open_orders.empty else []:
        repair_p_inventory_links(order_id)
    placeholders = ",".join("?" for _ in order_ids)
    waiting = wms_q(
        f"""SELECT i.source_inventory_id, i.waiting_inventory_id, i.company, i.product_name, i.lot, i.exp_date,
                   i.source_location, i.qty, COALESCE(i.confirmed,0) AS confirmed
            FROM export_waiting_items i LEFT JOIN inventory p ON p.id=i.waiting_inventory_id
            WHERE i.order_id IN ({placeholders}) AND i.qty>0
              AND (COALESCE(i.confirmed,0)=1 OR UPPER(TRIM(COALESCE(p.location,'')))='P')
            ORDER BY i.order_id, i.id""", tuple(order_ids))
    if waiting.empty:
        return 0
    orders = [dict(row) for row in export_service.get_order_items(case_id)]
    if not orders:
        return 0
    existing = [dict(row) for row in export_db.rows(
        """SELECT id,order_item_id,business_unit,location,source_inventory_id,product_name,lot_no,expiry_date,requested_qty,box_no
           FROM shipment_items WHERE case_id=? ORDER BY id""", (case_id,))]
    now = now_text(); inserts = []; changed = 0
    for row in waiting.to_dict("records"):
        source_id = int(row.get("source_inventory_id") or 0)
        if not source_id: continue
        product_key = _match_text(row.get("product_name"))
        candidates = [order for order in orders if product_key and (_match_text(order.get("product_name")) == product_key or _match_text(order.get("product_name")) in product_key or product_key in _match_text(order.get("product_name")))]
        if len(candidates) != 1: candidates = orders if len(orders) == 1 else []
        if len(candidates) != 1: continue
        order_item_id = int(candidates[0]["id"])
        linked_rows_elsewhere = [item for item in existing if int(item.get("source_inventory_id") or 0) == source_id and int(item.get("order_item_id") or 0) != order_item_id]
        if linked_rows_elsewhere: continue
        linked_rows = [item for item in existing if int(item.get("source_inventory_id") or 0) == source_id and int(item.get("order_item_id") or 0) == order_item_id]
        legacy_rows = _matching_legacy_rows(existing, row, order_item_id)
        if linked_rows and legacy_rows:
            linked_total = sum(float(item.get("requested_qty") or 0) for item in linked_rows)
            if _same_quantity(linked_total, row.get("qty")):
                legacy_is_packed = any(item.get("box_no") is not None for item in legacy_rows); linked_is_packed = any(item.get("box_no") is not None for item in linked_rows)
                if legacy_is_packed or not linked_is_packed:
                    export_db.executemany("DELETE FROM shipment_items WHERE id=?", [(int(item["id"]),) for item in linked_rows]); _update_legacy_rows(legacy_rows, row, source_id, now)
                    deleted_ids = {int(item["id"]) for item in linked_rows}; existing = [item for item in existing if int(item["id"]) not in deleted_ids]
                    for item in legacy_rows: item.update({"business_unit":str(row.get("company") or ""),"location":str(row.get("source_location") or ""),"source_inventory_id":source_id,"product_name":str(row.get("product_name") or ""),"lot_no":str(row.get("lot") or ""),"expiry_date":str(row.get("exp_date") or "")})
                else:
                    export_db.executemany("DELETE FROM shipment_items WHERE id=?", [(int(item["id"]),) for item in legacy_rows]); deleted_ids={int(item["id"]) for item in legacy_rows}; existing=[item for item in existing if int(item["id"]) not in deleted_ids]
                changed += 1; continue
        if linked_rows: continue
        if legacy_rows:
            _update_legacy_rows(legacy_rows,row,source_id,now)
            for item in legacy_rows: item.update({"business_unit":str(row.get("company") or ""),"location":str(row.get("source_location") or ""),"source_inventory_id":source_id,"product_name":str(row.get("product_name") or ""),"lot_no":str(row.get("lot") or ""),"expiry_date":str(row.get("exp_date") or "")})
            changed += 1; continue
        inserts.append((case_id,order_item_id,str(row.get("company") or ""),str(row.get("source_location") or ""),source_id,str(row.get("product_name") or ""),str(row.get("lot") or ""),str(row.get("exp_date") or ""),float(row.get("qty") or 0),None,now,now))
        existing.append({"id":0,"order_item_id":order_item_id,"source_inventory_id":source_id,"requested_qty":float(row.get("qty") or 0),"box_no":None})
    if not inserts and not changed: return 0
    if inserts:
        export_db.executemany("""INSERT INTO shipment_items(case_id,order_item_id,business_unit,location,source_inventory_id,product_name,lot_no,expiry_date,requested_qty,box_no,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", inserts)
    shipment_service.sync_case_stage(case_id, now)
    return len(inserts)+changed


def _cart_row_from_shipment_row(row: dict) -> dict:
    return {"id":int(row["source_inventory_id"] or 0),"요청수량":float(row["requested_qty"] or 0),"사업장":row.get("business_unit") or "","제품명":row.get("product_name") or "","LOT":row.get("lot_no") or "","유통기한":row.get("expiry_date") or "","로케이션":row.get("source_location") or row.get("location") or ""}


def _cart_row_from_pick(pick: dict) -> dict:
    return {"id":int(pick["inventory_id"]),"요청수량":float(pick["qty"]),"사업장":pick.get("company") or "","제품명":pick.get("product_name") or "","LOT":pick.get("lot") or "","유통기한":pick.get("exp_date") or "","로케이션":pick.get("location") or ""}


def _waiting_rows_for_order(order_id: int) -> list[dict]:
    df = wms_q("""SELECT source_inventory_id,company,product_name,warehouse_name,lot,exp_date,source_location,qty
                    FROM export_waiting_items WHERE order_id=? AND COALESCE(confirmed,0)=0 ORDER BY id""", (int(order_id),))
    return df.to_dict("records") if not df.empty else []


def _all_rows_for_order(order_id: int) -> list[dict]:
    df = wms_q(
        """SELECT source_inventory_id,company,product_name,warehouse_name,lot,exp_date,
                  source_location,qty,COALESCE(confirmed,0) AS confirmed
           FROM export_waiting_items WHERE order_id=? ORDER BY id""",
        (int(order_id),),
    )
    return df.to_dict("records") if not df.empty else []


def _cart_row_from_waiting_row(row: dict) -> dict:
    return {
        "id": int(row.get("source_inventory_id") or 0),
        "요청수량": float(row.get("qty") or 0),
        "사업장": row.get("company") or "",
        "제품명": row.get("product_name") or "",
        "LOT": row.get("lot") or "",
        "유통기한": row.get("exp_date") or "",
        "로케이션": row.get("source_location") or "",
    }


def _stock_signature(row: dict) -> tuple[str, str, str, str]:
    return (
        _match_value(row.get("company") or row.get("business_unit") or row.get("사업장")),
        _match_text(row.get("product_name") or row.get("제품명")),
        _match_value(row.get("lot") or row.get("lot_no") or row.get("LOT")),
        _match_date(row.get("exp_date") or row.get("expiry_date") or row.get("유통기한")),
    )


def missing_canonical_cart_rows(
    wms_rows: list[dict], canonical_rows: list[dict], cart: list[dict]
) -> list[dict]:
    """WMS 연결에서 통째로 사라진 EXPORT 저장행만 복구 대상으로 돌려준다.

    source id는 재고 이동/병합 뒤 달라질 수 있으므로 제품·제조번호·유통기한
    서명으로 비교한다. 이미 같은 재고가 WMS에 있으면 오래된 미러 중복행은
    다시 추가하지 않는다.
    """
    represented = {_stock_signature(row) for row in wms_rows}
    represented.update(_stock_signature(row) for row in cart)
    missing_by_signature: dict[tuple[str, str, str, str], dict] = {}
    for row in canonical_rows:
        if not row.get("source_inventory_id") or safe_quantity(row.get("requested_qty")) <= 0:
            continue
        signature = _stock_signature(row)
        if not signature[1] or signature in represented:
            continue
        if signature not in missing_by_signature:
            missing_by_signature[signature] = _cart_row_from_shipment_row(row)
        else:
            missing_by_signature[signature]["요청수량"] += safe_quantity(
                row.get("requested_qty")
            )
    return list(missing_by_signature.values())


def missing_saved_inventory_count(export_no: str) -> int:
    _, missing = _missing_saved_inventory_context(export_no)
    return len(missing)


def _missing_saved_inventory_context(
    export_no: str,
) -> tuple[int | None, set[tuple[str, str, str, str]]]:
    normalized = str(export_no or "").strip()
    cases = export_db.rows(
        """SELECT id FROM export_cases
           WHERE TRIM(export_no)=TRIM(?) AND case_type<>'historical'
             AND status<>'취소' AND stage<>'취소' ORDER BY id""",
        (normalized,),
    )
    order_ids = _linkable_order_ids(normalized)
    if len(cases) != 1 or len(order_ids) != 1:
        return None, set()
    case_id = int(cases[0]["id"])
    canonical = shipment_service.list_case_items(case_id)
    wms_rows = _all_rows_for_order(order_ids[0])
    represented = {_stock_signature(row) for row in wms_rows}
    missing = {
        _stock_signature(row)
        for row in canonical
        if row.get("source_inventory_id")
        and safe_quantity(row.get("requested_qty")) > 0
        and _stock_signature(row)[1]
        and _stock_signature(row) not in represented
    }
    return case_id, missing


def repair_missing_saved_inventory(export_no: str) -> int:
    normalized = str(export_no or "").strip()
    case_id, initial_missing = _missing_saved_inventory_context(normalized)
    if case_id is None:
        raise ValueError("복구할 수출 건을 하나로 특정할 수 없습니다.")
    if not initial_missing:
        return 0

    for _ in range(len(initial_missing) + 1):
        _, missing = _missing_saved_inventory_context(normalized)
        if not missing:
            return len(initial_missing)
        rows = shipment_service.list_case_items(case_id)
        target = next(
            (
                row for row in rows
                if row.get("order_item_id") and _stock_signature(row) in missing
            ),
            None,
        )
        if target is None:
            break
        order_item_id = int(target["order_item_id"])
        kept_rows = [
            dict(row) for row in rows
            if int(row.get("order_item_id") or 0) == order_item_id
        ]
        save_picked_inventory(
            case_id=case_id,
            order_item_id=order_item_id,
            kept_rows=kept_rows,
            picked_rows=[],
        )

    remaining = missing_saved_inventory_count(normalized)
    if remaining:
        raise ValueError(f"{remaining}개 품목 연결이 아직 복구되지 않았습니다.")
    return len(initial_missing)


def safe_quantity(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def authoritative_other_cart_rows(
    waiting_rows: list[dict], selected_source_ids: set[int]
) -> list[dict]:
    """현재 편집 재고 외의 WMS 예약은 미러가 아닌 WMS 원본 그대로 보존한다."""
    return [
        _cart_row_from_waiting_row(row)
        for row in waiting_rows
        if int(row.get("source_inventory_id") or 0) > 0
        and int(row.get("source_inventory_id") or 0) not in selected_source_ids
        and float(row.get("qty") or 0) > 0
    ]


def cart_rows_after_selected_order_edit(
    waiting_rows: list[dict],
    current_rows: list[dict],
    kept_rows: list[dict],
    picked_rows: list[dict],
) -> list[dict]:
    """WMS 총예약량에서 현재 주문행 몫만 교체한다.

    같은 source_inventory_id를 다른 주문행도 나눠 쓰는 경우 ID 전체를
    제외하면 다른 주문행 수량까지 사라지므로 수량 차감/가산으로 계산한다.
    """
    totals: dict[int, dict] = {}

    def add(row: dict, quantity: float) -> None:
        source_id = int(row.get("id") or 0)
        if source_id <= 0 or quantity == 0:
            return
        if source_id not in totals:
            totals[source_id] = {**row, "id": source_id, "요청수량": 0.0}
        totals[source_id]["요청수량"] = float(totals[source_id]["요청수량"]) + float(quantity)

    for row in waiting_rows:
        cart_row = _cart_row_from_waiting_row(row)
        add(cart_row, float(cart_row["요청수량"]))
    for row in current_rows:
        if row.get("source_inventory_id"):
            add(
                _cart_row_from_shipment_row(row),
                -float(row.get("requested_qty") or 0),
            )
    for row in kept_rows:
        if row.get("source_inventory_id"):
            add(
                _cart_row_from_shipment_row(row),
                float(row.get("requested_qty") or 0),
            )
    for pick in picked_rows:
        cart_row = _cart_row_from_pick(pick)
        add(cart_row, float(cart_row["요청수량"]))

    result = []
    for row in totals.values():
        row["요청수량"] = max(0.0, float(row["요청수량"]))
        if row["요청수량"] > 0:
            result.append(row)
    return result


def _fill_missing_source_links(rows: list[dict], waiting_rows: list[dict]) -> None:
    """구형/편집표 행에서 source_inventory_id가 빠졌다면 현재 WMS 대기행으로 복구한다."""
    used: set[int] = set()
    for row in rows:
        if row.get("source_inventory_id"):
            used.add(int(row["source_inventory_id"])); continue
        matches = [w for w in waiting_rows if int(w.get("source_inventory_id") or 0) not in used
                   and _match_text(w.get("product_name")) == _match_text(row.get("product_name"))
                   and (not _match_value(row.get("business_unit")) or _match_value(w.get("company")) == _match_value(row.get("business_unit")))
                   and _match_value(w.get("lot")) == _match_value(row.get("lot_no"))
                   and _match_date(w.get("exp_date")) == _match_date(row.get("expiry_date"))]
        if len(matches) == 1:
            match = matches[0]; source_id = int(match.get("source_inventory_id") or 0)
            if source_id:
                row["source_inventory_id"] = source_id
                row["source_location"] = row.get("source_location") or row.get("location") or match.get("source_location") or ""
                used.add(source_id)


def save_picked_inventory(*, case_id:int, order_item_id:int, kept_rows:list[dict], picked_rows:list[dict]) -> dict:
    case=export_service.get_case(case_id)
    if case is None: raise ValueError("수출 건을 찾을 수 없습니다.")
    export_no=str(case["export_no"] or "").strip()
    if not export_no: raise ValueError("이 수출 건에는 수출번호가 없습니다.")
    country=str(case["country"] or "").strip()
    if not country: raise ValueError("이 수출 건에는 국가가 입력되어 있지 않습니다. 먼저 국가를 입력하세요.")
    transport_method=TRANSPORT_MODE_TO_METHOD.get(str(case["transport_mode"] or "").strip(),"미지정")
    editing_order_id=_find_open_order_id(export_no)

    all_kept_rows=list(kept_rows)
    case_rows = shipment_service.list_case_items(case_id)
    current_rows = [row for row in case_rows if int(row["order_item_id"] or 0)==int(order_item_id)]
    other_rows=[row for row in case_rows if int(row["order_item_id"] or 0)!=int(order_item_id)]
    if editing_order_id:
        waiting_rows=_waiting_rows_for_order(editing_order_id)
        all_wms_rows=_all_rows_for_order(editing_order_id)
        _fill_missing_source_links(all_kept_rows, waiting_rows)
        _fill_missing_source_links(other_rows, waiting_rows)
    linked_kept_rows=[row for row in all_kept_rows if row.get("source_inventory_id")]
    cart = (
        cart_rows_after_selected_order_edit(
            waiting_rows, current_rows, linked_kept_rows, picked_rows
        )
        if editing_order_id else
        [_cart_row_from_shipment_row(row) for row in other_rows if row.get("source_inventory_id")]
    )
    if not editing_order_id:
        cart += [_cart_row_from_shipment_row(row) for row in linked_kept_rows]
        cart += [_cart_row_from_pick(pick) for pick in picked_rows]
    else:
        final_canonical_rows = other_rows + all_kept_rows
        cart += missing_canonical_cart_rows(all_wms_rows, final_canonical_rows, cart)

    mirror_rows=[{"_id":row["id"],"business_unit":row.get("business_unit") or "","location":row.get("source_location") or row.get("location") or "","source_inventory_id":row.get("source_inventory_id"),"product_name":row.get("product_name") or "","lot_no":row.get("lot_no") or "","expiry_date":row.get("expiry_date") or "","requested_qty":float(row["requested_qty"] or 0)} for row in all_kept_rows]
    mirror_rows += [{"_id":None,"business_unit":pick.get("company") or "","location":pick.get("location") or "","source_inventory_id":int(pick["inventory_id"]),"product_name":pick.get("product_name") or "","lot_no":pick.get("lot") or "","expiry_date":pick.get("exp_date") or "","requested_qty":float(pick["qty"])} for pick in picked_rows]
    original_mirror_rows=[{"_id":row["id"],"business_unit":row.get("business_unit") or "","location":row.get("source_location") or row.get("location") or "","source_inventory_id":row.get("source_inventory_id"),"product_name":row.get("product_name") or "","lot_no":row.get("lot_no") or "","expiry_date":row.get("expiry_date") or "","requested_qty":float(row["requested_qty"] or 0)} for row in current_rows]
    total_qty=shipment_service.save_for_order(case_id,order_item_id,mirror_rows)
    try:
        result=save_export_waiting_order(cart,country=country,buyer=str(case.get("buyer") or ""),transport_method=transport_method,export_no=export_no,editing_order_id=editing_order_id)
    except Exception:
        shipment_service.save_for_order(case_id,order_item_id,original_mirror_rows); raise
    return {"order_id":result["order_id"],"total_qty":total_qty,"row_count":len(mirror_rows)}
