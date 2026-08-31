from __future__ import annotations

from collections import defaultdict

import nohtus.services.export_waiting as export_waiting
from nohtus.services.inventory import insert_transaction_log


def _patched_apply_export_waiting_item_changes(
    cur,
    order_id,
    grouped,
    source_hints,
    now,
    title,
    export_no,
    target_location=None,
):
    """Rebuild staging inventory safely, but record history only for actual changes."""
    if target_location is None:
        target_location = export_waiting.P
    current_items = export_waiting._items(cur, order_id, confirmed=False)
    target_qty = {int(k): int(v) for k, v in dict(grouped).items() if int(v) > 0}

    before_qty = defaultdict(int)
    before_item = {}
    # 이미 있던 품목은 재저장할 때마다 target_location(기본 P)으로 슬쩍
    # 옮겨가면 안 된다 — T3 등에 실제로 놓인 재고가 관계없는 수정 저장 한 번에
    # 조용히 P로 되돌아가는 사고를 막기 위해, 기존 위치를 그대로 유지하고
    # target_location은 이번에 새로 추가되는 품목에만 적용한다.
    prior_location_by_source = {}
    for item in current_items:
        source_id = int(item.get("source_inventory_id") or 0)
        before_qty[source_id] += int(item.get("qty") or 0)
        before_item.setdefault(source_id, item)
        prior_location_by_source.setdefault(
            source_id, str(item.get("waiting_location") or "").strip() or export_waiting.P
        )

    # 재고 정합성을 위해 내부적으로는 기존 목록을 전부 원복한 뒤 새 목록을 다시 적재한다.
    # 이 과정 자체는 이력에 남기지 않고, 아래에서 변경분만 별도로 기록한다.
    restored_source_rows = {}
    for item in current_items:
        source_id = int(item.get("source_inventory_id") or 0)
        try:
            restored, _ = export_waiting._restore_waiting_item(cur, item, now)
        except ValueError:
            # P와 원위치 재고가 모두 없는 고아 연결은 사용자가
            # 이 품목을 삭제하는 경우에만 연결행을 정리한다.
            if target_qty.get(source_id, 0) > 0:
                raise
            continue
        if restored:
            restored_source_rows[source_id] = restored
            source_hints[source_id] = restored

    cur.execute("DELETE FROM export_waiting_items WHERE order_id=?", (int(order_id),))

    after_item = {}
    after_location = {}
    for source_id, qty in target_qty.items():
        hint = source_hints.get(source_id) or restored_source_rows.get(source_id)
        source = export_waiting._take_source(cur, source_id, qty, now, hint)
        resolved_inventory_id = int(
            source.get("_resolved_inventory_id") or source.get("id") or source_id
        )
        item_target_location = prior_location_by_source.get(source_id, target_location)
        waiting_inventory_id, _ = export_waiting._place_source_in_staging(
            cur, source, qty, now, item_target_location
        )
        cur.execute(
            """INSERT INTO export_waiting_items(
                   order_id,source_inventory_id,waiting_inventory_id,company,product_name,
                   warehouse_name,lot,exp_date,source_location,waiting_location,
                   qty,moved_at,confirmed
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,0)""",
            (
                order_id,
                resolved_inventory_id,
                waiting_inventory_id,
                source.get("company", ""),
                source.get("product_name", ""),
                source.get("warehouse_name", "") or "",
                source.get("lot", "-") or "-",
                source.get("exp_date", "-") or "-",
                source.get("location", ""),
                item_target_location,
                qty,
                now,
            ),
        )
        after_item[source_id] = source
        after_location[source_id] = item_target_location

    # 삭제·감소·추가·증가된 수량만 이력에 남긴다.
    for source_id in sorted(set(before_qty) | set(target_qty)):
        before = int(before_qty.get(source_id, 0))
        after = int(target_qty.get(source_id, 0))
        if before == after:
            continue

        if before > after:
            item = before_item[source_id]
            changed_qty = before - after
            insert_transaction_log(
                cur,
                created_at=now,
                tx_type="위치이동",
                product_name=item.get("product_name", ""),
                warehouse_name=item.get("warehouse_name", "") or "",
                lot=item.get("lot", "-"),
                exp_date=item.get("exp_date", "-"),
                from_company=item.get("company", ""),
                from_location=str(item.get("waiting_location") or "").strip() or export_waiting.P,
                to_company=item.get("company", ""),
                to_location=item.get("source_location", ""),
                qty=changed_qty,
                memo=(
                    f"수출대기 수정 / 품목삭제 또는 수량감소 / {title} / "
                    f"수출번호: {export_no}"
                ),
            )

        if after > before:
            item = after_item[source_id]
            changed_qty = after - before
            insert_transaction_log(
                cur,
                created_at=now,
                tx_type="위치이동",
                product_name=item.get("product_name", ""),
                warehouse_name=item.get("warehouse_name", "") or "",
                lot=item.get("lot", "-"),
                exp_date=item.get("exp_date", "-"),
                from_company=item.get("company", ""),
                from_location=item.get("location", ""),
                to_company=item.get("company", ""),
                to_location=after_location.get(source_id, export_waiting.P),
                qty=changed_qty,
                memo=(
                    f"수출대기 수정 / 품목추가 또는 수량증가 / {title} / "
                    f"수출번호: {export_no}"
                ),
            )


export_waiting._apply_export_waiting_item_changes = _patched_apply_export_waiting_item_changes
