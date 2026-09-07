"""선택한 발주일자를 YYMMDD 형식으로 발주ID에 반영하는 실행 런처."""

from datetime import date, datetime

import pandas as pd

import app_cascade_delete as cascade

purchase = cascade.purchase
base_app = cascade.base_app


def _selected_order_date():
    """발주 작성 화면에서 선택한 발주일자를 date 객체로 반환합니다."""
    value = base_app.st.session_state.get("order_date")
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value:
        try:
            return pd.to_datetime(value).date()
        except Exception:
            pass
    return datetime.now().date()


def _unique_order_id(base_id, existing_ids):
    """같은 초에 저장해도 발주ID가 겹치지 않도록 순번을 붙입니다."""
    if base_id not in existing_ids:
        return base_id

    suffix = 2
    candidate = f"{base_id}-{suffix}"
    while candidate in existing_ids:
        suffix += 1
        candidate = f"{base_id}-{suffix}"
    return candidate


def save_order_with_short_selected_date(vendor_name, request_note, order_items):
    """선택한 발주일자를 YYMMDD 형식으로 발주ID에 반영해 저장합니다.

    예: 발주일자 2026-07-10, 저장시각 15:30:22 -> PO-260710-153022
    발주일시는 선택한 발주일자 + 저장시각으로 저장합니다.
    """
    orders = base_app.read_csv(
        base_app.ORDERS_FILE,
        ["발주ID", "발주일시", "거래처명", "요청사항", "상태", "총품목수", "총수량"],
    )
    order_items_df = base_app.read_csv(
        base_app.ORDER_ITEMS_FILE,
        ["발주ID", "순번", "제품코드", "정식제품명", "검색별칭", "규격", "단위", "수량"],
    )

    selected_date = _selected_order_date()
    now = datetime.now()
    selected_datetime = datetime.combine(selected_date, now.time().replace(microsecond=0))
    base_id = f"PO-{selected_datetime.strftime('%y%m%d-%H%M%S')}"
    order_id = _unique_order_id(base_id, set(orders["발주ID"].astype(str).tolist()))

    total_count, total_qty = base_app.calc_totals(order_items)
    orders = pd.concat([
        orders,
        pd.DataFrame([{
            "발주ID": order_id,
            "발주일시": selected_datetime.strftime("%Y-%m-%d %H:%M:%S"),
            "거래처명": vendor_name,
            "요청사항": request_note,
            "상태": "발주완료",
            "총품목수": total_count,
            "총수량": total_qty,
        }]),
    ], ignore_index=True)

    rows = []
    for idx, item in enumerate(order_items, 1):
        rows.append({
            "발주ID": order_id,
            "순번": idx,
            "제품코드": item.get("제품코드", ""),
            "정식제품명": item.get("정식제품명", ""),
            "검색별칭": item.get("검색별칭", ""),
            "규격": item.get("규격", ""),
            "단위": item.get("단위", ""),
            "수량": base_app.safe_int(item.get("수량", 0)),
        })

    if rows:
        order_items_df = pd.concat([order_items_df, pd.DataFrame(rows)], ignore_index=True)

    orders.to_csv(base_app.ORDERS_FILE, index=False, encoding="utf-8-sig")
    order_items_df.to_csv(base_app.ORDER_ITEMS_FILE, index=False, encoding="utf-8-sig")
    return order_id


base_app.save_order = save_order_with_short_selected_date


if __name__ == "__main__":
    purchase.main()
