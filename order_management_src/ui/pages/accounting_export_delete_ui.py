"""월별 매입 현황 화면 아래에서 거래명세서를 선택 삭제할 수 있게 하는 보정 레이어."""
from __future__ import annotations

import pandas as pd

from ui.month_grid import render_month_grid
from ui.pages import accounting_export as base


def _to_int(purchase_module, value) -> int:
    return purchase_module.to_int(value)


def _statement_rows(purchase_module, year: int, month: int):
    statements, statement_items, price_history, _ = purchase_module.load_purchase_data()
    if statements.empty:
        return statements, statement_items, price_history, pd.DataFrame()

    working = statements.copy()
    working["_date"] = pd.to_datetime(working["명세서일자"], errors="coerce")
    working = working[
        (working["_date"].dt.year == int(year))
        & (working["_date"].dt.month == int(month))
    ].copy()
    if working.empty:
        return statements, statement_items, price_history, pd.DataFrame()

    rows = []
    for _, statement in working.sort_values(["명세서일자", "등록일시"]).iterrows():
        statement_id = str(statement.get("명세서ID", ""))
        items = statement_items[
            statement_items["명세서ID"].astype(str) == statement_id
        ]
        product_amount = int(
            items["상품금액"].apply(lambda value: _to_int(purchase_module, value)).sum()
        ) if not items.empty else 0
        freight = _to_int(purchase_module, statement.get("운송비", 0))
        rows.append({
            "삭제": False,
            "명세서ID": statement_id,
            "거래처명": str(statement.get("거래처명", "")),
            "명세서일자": str(statement.get("명세서일자", "")),
            "명세서번호": str(statement.get("명세서번호", "")),
            "품목 수": len(items),
            "총 매입금액": product_amount + freight,
        })

    return statements, statement_items, price_history, pd.DataFrame(rows)


def _delete_statements(purchase_module, statement_ids, statements, statement_items, price_history):
    ids = {str(value) for value in statement_ids}
    remaining_statements = statements[~statements["명세서ID"].astype(str).isin(ids)].copy()
    remaining_items = statement_items[
        ~statement_items["명세서ID"].astype(str).isin(ids)
    ].copy()
    remaining_prices = price_history[
        ~price_history["명세서ID"].astype(str).isin(ids)
    ].copy()

    purchase_module.save_table(
        purchase_module.STATEMENTS_FILE,
        remaining_statements,
        purchase_module.STATEMENT_COLUMNS,
    )
    purchase_module.save_table(
        purchase_module.STATEMENT_ITEMS_FILE,
        remaining_items,
        purchase_module.STATEMENT_ITEM_COLUMNS,
    )
    purchase_module.save_table(
        purchase_module.PRICE_HISTORY_FILE,
        remaining_prices,
        purchase_module.PRICE_HISTORY_COLUMNS,
    )


def render(purchase_module, data) -> None:
    st = purchase_module.st
    base.render(purchase_module, data)

    st.markdown("---")
    st.markdown("### 거래명세서 삭제")
    st.caption("삭제할 거래명세서의 달을 고르고, 목록에서 체크한 뒤 삭제하세요. 품목과 가격이력도 함께 삭제됩니다.")

    today = pd.Timestamp.now()
    with st.container(border=True):
        year, month = render_month_grid(
            st, "statement_delete", default_year=today.year, default_month=today.month
        )

    statements, statement_items, price_history, rows = _statement_rows(purchase_module, year, month)
    if rows.empty:
        st.info("선택한 월에 삭제할 거래명세서가 없습니다.")
        return

    display = rows.copy()
    display["총 매입금액"] = display["총 매입금액"].apply(lambda value: f"{int(value):,}원")

    edited = st.data_editor(
        display,
        use_container_width=True,
        hide_index=True,
        disabled=["명세서ID", "거래처명", "명세서일자", "명세서번호", "품목 수", "총 매입금액"],
        column_config={"삭제": st.column_config.CheckboxColumn("삭제")},
        key="statement_delete_editor",
    )

    selected_ids = edited.loc[edited["삭제"] == True, "명세서ID"].tolist()

    confirm_col, delete_col = st.columns([3, 1])
    confirmed = confirm_col.checkbox(
        f"선택한 거래명세서 {len(selected_ids)}건을 삭제하겠습니다.",
        key="statement_delete_confirm",
        disabled=not selected_ids,
    )
    if delete_col.button(
        "거래명세서 삭제",
        type="primary",
        use_container_width=True,
        disabled=not (selected_ids and confirmed),
        key="statement_delete_button",
    ):
        _delete_statements(purchase_module, selected_ids, statements, statement_items, price_history)
        st.success(f"거래명세서 {len(selected_ids)}건을 삭제했습니다.")
        st.rerun()
