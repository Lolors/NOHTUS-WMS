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
):
    """Rebuild P inventory safely, but record history only for actual changes."""
    current_items = export_waiting._items(cur, order_id, confirmed=False)
    target_qty = {int(k): int(v) for k, v in dict(grouped).items() if int(v) > 0}

    before_qty = defaultdict(int)
    before_item = {}
    for item in current_items:
        source_id = int(item.get("source_inventory_id") or 0)
        before_qty[source_id] += int(item.get("qty") or 0)
        before_item.setdefault(source_id, item)

    # 소스별 현재 행 개수를 세어, 수량이 그대로인 품목만 안전하게 건드리지 않고
    # 넘어갈 수 있는지 판단한다(같은 source_id가 여러 행으로 쪼개져 있으면
    # 어느 행이 그대로인지 알 수 없으므로 이 최적화를 적용하지 않는다).
    source_id_counts = defaultdict(int)
    for item in current_items:
        source_id_counts[int(item.get("source_inventory_id") or 0)] += 1

    # 재고 정합성을 위해 내부적으로는 기존 목록을 전부 원복한 뒤 새 목록을 다시 적재한다.
    # 이 과정 자체는 이력에 남기지 않고, 아래에서 변경분만 별도로 기록한다.
    unchanged_item_ids = []
    restored_source_rows = {}
    for item in current_items:
        source_id = int(item.get("source_inventory_id") or 0)
        current_qty = int(item.get("qty") or 0)
        # 수량이 바뀌지 않은 품목은 P<->원위치 왕복(복원 후 재적재)을 건너뛴다.
        # 매 저장마다 안 바뀐 품목까지 왕복시키면, P 재고 연결이 끊어져 있을
        # 때마다 실패하거나 "이미 원위치에 있다"는 조용한 폴백이 반복 발동해
        # 실제로는 P로 옮겨진 적 없는 것처럼 원래 위치에 눌러앉는 사고로
        # 이어진다.
        if (
            source_id
            and source_id_counts[source_id] == 1
            and target_qty.get(source_id, 0) == current_qty
        ):
            unchanged_item_ids.append(int(item["id"]))
            target_qty.pop(source_id, None)
            before_qty.pop(source_id, None)
            continue
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

    if unchanged_item_ids:
        placeholders = ",".join("?" for _ in unchanged_item_ids)
        cur.execute(
            f"DELETE FROM export_waiting_items WHERE order_id=? AND id NOT IN ({placeholders})",
            (int(order_id), *unchanged_item_ids),
        )
    else:
        cur.execute("DELETE FROM export_waiting_items WHERE order_id=?", (int(order_id),))

    after_item = {}
    for source_id, qty in target_qty.items():
        hint = source_hints.get(source_id) or restored_source_rows.get(source_id)
        source = export_waiting._take_source(cur, source_id, qty, now, hint)
        resolved_inventory_id = int(
            source.get("_resolved_inventory_id") or source.get("id") or source_id
        )
        waiting_inventory_id = export_waiting._add(
            cur, source, export_waiting.P, qty, now, 0
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
                export_waiting.P,
                qty,
                now,
            ),
        )
        after_item[source_id] = source

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
                from_location=export_waiting.P,
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
                to_location=export_waiting.P,
                qty=changed_qty,
                memo=(
                    f"수출대기 수정 / 품목추가 또는 수량증가 / {title} / "
                    f"수출번호: {export_no}"
                ),
            )


export_waiting._apply_export_waiting_item_changes = _patched_apply_export_waiting_item_changes
