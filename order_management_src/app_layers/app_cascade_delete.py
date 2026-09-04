"""발주 삭제 시 연결된 거래명세서와 가격이력을 함께 삭제하는 실행 런처."""

import pandas as pd

import app_search_fix as fixed

purchase = fixed.purchase
base_app = fixed.base_app


def delete_order_with_statements(order_id):
    """발주와 연결된 거래명세서, 품목, 가격이력을 함께 삭제합니다."""
    order_id = str(order_id)

    orders = base_app.read_csv(
        base_app.ORDERS_FILE,
        ["발주ID", "발주일시", "거래처명", "요청사항", "상태", "총품목수", "총수량"],
    )
    order_items = base_app.read_csv(
        base_app.ORDER_ITEMS_FILE,
        ["발주ID", "순번", "제품코드", "정식제품명", "검색별칭", "규격", "단위", "수량"],
    )

    purchase.ensure_purchase_files()
    statements, statement_items, price_history, _ = purchase.load_purchase_data()

    linked_statement_ids = statements.loc[
        statements["발주ID"].astype(str) == order_id,
        "명세서ID",
    ].astype(str).tolist()

    orders = orders[orders["발주ID"].astype(str) != order_id]
    order_items = order_items[order_items["발주ID"].astype(str) != order_id]
    statements = statements[statements["발주ID"].astype(str) != order_id]

    if linked_statement_ids:
        linked_set = set(linked_statement_ids)
        statement_items = statement_items[
            ~statement_items["명세서ID"].astype(str).isin(linked_set)
        ]
        price_history = price_history[
            ~price_history["명세서ID"].astype(str).isin(linked_set)
        ]

    orders.to_csv(base_app.ORDERS_FILE, index=False, encoding="utf-8-sig")
    order_items.to_csv(base_app.ORDER_ITEMS_FILE, index=False, encoding="utf-8-sig")
    purchase.save_table(purchase.STATEMENTS_FILE, statements, purchase.STATEMENT_COLUMNS)
    purchase.save_table(
        purchase.STATEMENT_ITEMS_FILE,
        statement_items,
        purchase.STATEMENT_ITEM_COLUMNS,
    )
    purchase.save_table(
        purchase.PRICE_HISTORY_FILE,
        price_history,
        purchase.PRICE_HISTORY_COLUMNS,
    )


base_app.delete_order = delete_order_with_statements


if __name__ == "__main__":
    purchase.main()
