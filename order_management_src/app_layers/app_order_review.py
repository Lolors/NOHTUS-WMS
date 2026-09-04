"""발주서 상세 아래에 거래명세서 기준 입고 검수 요약을 추가하는 실행 런처."""

import pandas as pd

import app_product_schema as current

purchase = current.purchase
base_app = current.base_app
st = base_app.st
ORIGINAL_PAGE_ORDERS = base_app.page_orders


def _text(value):
    return str(value or "").strip()


def _item_key(row):
    """제품코드가 있으면 코드, 없으면 제품명/규격/포장단위 조합으로 품목을 식별합니다."""
    code = _text(row.get("제품코드", ""))
    if code:
        return ("CODE", code)
    name = _text(row.get("제품명", row.get("정식제품명", "")))
    spec = _text(row.get("규격", ""))
    pack = _text(row.get("포장단위", row.get("단위", "")))
    return ("TEXT", name, spec, pack)


def _status(ordered_qty, received_qty):
    ordered_qty = purchase.to_int(ordered_qty)
    received_qty = purchase.to_int(received_qty)
    if received_qty <= 0:
        return "미입고"
    if received_qty < ordered_qty:
        return "입고가 덜 됨"
    if received_qty == ordered_qty:
        return "입고완료"
    return "초과입고"


def render_order_receipt_review(orders, order_items_saved):
    st.markdown("---")
    st.markdown("## 발주별 입고 검수 요약")
    st.caption("연결된 거래명세서를 기준으로 품목별 입고 상태를 확인합니다. 포장단위는 발주서에 저장된 값을 그대로 사용합니다.")

    if orders.empty:
        st.info("검수할 발주서가 없습니다.")
        return

    purchase.ensure_purchase_files()
    statements, statement_items, _, _ = purchase.load_purchase_data()

    ordered = orders.copy().sort_values("발주일시", ascending=False)
    order_ids = ordered["발주ID"].astype(str).tolist()
    vendor_map = ordered.set_index("발주ID")["거래처명"].astype(str).to_dict()
    selected_order = st.selectbox(
        "검수할 발주서",
        order_ids,
        format_func=lambda oid: f'[{vendor_map.get(oid, "")}] {oid}',
        key="order_receipt_review_selector",
    )

    order_rows = order_items_saved[
        order_items_saved["발주ID"].astype(str) == str(selected_order)
    ].copy()
    linked_statements = statements[
        statements["발주ID"].astype(str) == str(selected_order)
    ].copy()
    linked_ids = linked_statements["명세서ID"].astype(str).tolist()
    linked_items = statement_items[
        statement_items["명세서ID"].astype(str).isin(linked_ids)
    ].copy()

    if order_rows.empty:
        st.info("이 발주서에는 저장된 품목이 없습니다.")
        return

    received_by_key = {}
    if not linked_items.empty:
        for _, row in linked_items.iterrows():
            key = _item_key(row)
            received_by_key[key] = received_by_key.get(key, 0) + purchase.to_int(row.get("입고수량", 0))

    review_rows = []
    for _, row in order_rows.iterrows():
        ordered_qty = purchase.to_int(row.get("수량", 0))
        received_qty = received_by_key.get(_item_key(row), 0)
        name = _text(row.get("제품명", row.get("정식제품명", "")))
        pack = _text(row.get("포장단위", row.get("단위", "")))
        review_rows.append({
            "제품명": name,
            "규격": _text(row.get("규격", "")),
            "포장단위": pack,
            "발주수량": ordered_qty,
            "거래명세서 확인수량": received_qty,
            "상태": _status(ordered_qty, received_qty),
        })

    review = pd.DataFrame(review_rows)
    counts = review["상태"].value_counts().to_dict()
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("발주 품목", f"{len(review):,}개")
    c2.metric("입고완료", f"{counts.get('입고완료', 0):,}개")
    c3.metric("입고가 덜 됨", f"{counts.get('입고가 덜 됨', 0):,}개")
    c4.metric("미입고", f"{counts.get('미입고', 0):,}개")
    c5.metric("연결 거래명세서", f"{len(linked_statements):,}건")

    partial = review.loc[review["상태"] == "입고가 덜 됨", "제품명"].tolist()
    missing = review.loc[review["상태"] == "미입고", "제품명"].tolist()
    over = review.loc[review["상태"] == "초과입고", "제품명"].tolist()
    complete = review.loc[review["상태"] == "입고완료", "제품명"].tolist()

    messages = []
    if partial:
        messages.append("입고가 덜 된 품목은 " + ", ".join(partial) + "입니다.")
    if missing:
        messages.append("아직 입고되지 않은 품목은 " + ", ".join(missing) + "입니다.")
    if over:
        messages.append("발주수량보다 많이 확인된 품목은 " + ", ".join(over) + "입니다.")
    if not partial and not missing and not over and complete:
        messages.append("모든 발주 품목의 입고가 거래명세서로 확인되었습니다.")
    if messages:
        st.info("\n\n".join(messages))

    st.dataframe(
        review[["제품명", "규격", "포장단위", "발주수량", "거래명세서 확인수량", "상태"]],
        use_container_width=True,
        hide_index=True,
    )


def page_orders_with_receipt_review(vendors, orders, order_items_saved):
    ORIGINAL_PAGE_ORDERS(vendors, orders, order_items_saved)
    render_order_receipt_review(orders, order_items_saved)


base_app.page_orders = page_orders_with_receipt_review


if __name__ == "__main__":
    purchase.main()
