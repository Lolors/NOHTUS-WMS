"""거래명세서 등록·내역·월별 매입 화면."""
from __future__ import annotations

from datetime import datetime

import pandas as pd

from ui.pages import accounting_export


def register(purchase_module, data) -> None:
    purchase_module.page_statement_register(data["orders"], data["order_items"])


def _to_int(purchase_module, value) -> int:
    return purchase_module.to_int(value)


def _money(purchase_module, value, suffix="원") -> str:
    return f"{_to_int(purchase_module, value):,}{suffix}"


def _date_text(value) -> str:
    parsed = pd.to_datetime(value, errors="coerce")
    return "" if pd.isna(parsed) else parsed.strftime("%Y-%m-%d")


def _order_table(order_items: pd.DataFrame, purchase_module) -> pd.DataFrame:
    rows = order_items.copy()
    for col in ["정식제품명", "규격", "수량", "포장단위", "단위"]:
        if col not in rows.columns:
            rows[col] = ""
    rows["수량"] = rows["수량"].apply(lambda value: _to_int(purchase_module, value))
    rows["포장단위"] = rows.apply(
        lambda row: str(row.get("포장단위", "") or row.get("단위", "")), axis=1
    )
    rows = rows.reset_index(drop=True)
    rows.insert(0, "No.", range(1, len(rows) + 1))
    return rows[["No.", "정식제품명", "규격", "수량", "포장단위"]]


def _statement_table(items: pd.DataFrame, purchase_module) -> pd.DataFrame:
    rows = items.copy()
    required = [
        "정식제품명", "규격", "입고수량", "포장단위", "단위",
        "매입단가", "출고단가", "상품금액",
    ]
    for col in required:
        if col not in rows.columns:
            rows[col] = ""

    rows["수량"] = rows["입고수량"].apply(lambda value: _to_int(purchase_module, value))
    rows["포장단위"] = rows.apply(
        lambda row: str(row.get("포장단위", "") or row.get("단위", "")), axis=1
    )
    rows["매입단가_숫자"] = rows["매입단가"].apply(lambda value: _to_int(purchase_module, value))
    rows["판매가_숫자"] = rows.apply(
        lambda row: _to_int(purchase_module, row.get("출고단가", ""))
        or int(round(_to_int(purchase_module, row.get("매입단가", 0)) * 1.3)),
        axis=1,
    )
    rows["상품금액_숫자"] = rows.apply(
        lambda row: _to_int(purchase_module, row.get("상품금액", ""))
        or (_to_int(purchase_module, row.get("입고수량", 0)) * _to_int(purchase_module, row.get("매입단가", 0))),
        axis=1,
    )
    rows["매입단가"] = rows["매입단가_숫자"].apply(lambda value: f"{value:,}원")
    rows["판매가"] = rows["판매가_숫자"].apply(lambda value: f"{value:,}원")
    rows["상품금액"] = rows["상품금액_숫자"].apply(lambda value: f"{value:,}원")
    rows = rows.reset_index(drop=True)
    rows.insert(0, "No.", range(1, len(rows) + 1))
    return rows[[
        "No.", "정식제품명", "규격", "수량", "포장단위",
        "매입단가", "판매가", "상품금액",
    ]]


def _matching_product_codes(aliases: pd.DataFrame, keyword: str) -> set[str]:
    if aliases.empty or not keyword:
        return set()
    working = aliases.copy()
    for col in ["별칭", "제품코드"]:
        if col not in working.columns:
            working[col] = ""
    mask = working["별칭"].astype(str).str.contains(keyword, case=False, na=False, regex=False)
    return set(working.loc[mask, "제품코드"].astype(str))


def _filter_statements(statements, statement_items, aliases, start_date, end_date, vendor, keyword):
    filtered = statements.copy()
    filtered["_date"] = pd.to_datetime(filtered["명세서일자"], errors="coerce").dt.date
    filtered = filtered[(filtered["_date"] >= start_date) & (filtered["_date"] <= end_date)]

    if vendor != "전체":
        filtered = filtered[filtered["거래처명"].astype(str) == vendor]

    keyword = str(keyword or "").strip()
    if keyword:
        alias_codes = _matching_product_codes(aliases, keyword)
        items = statement_items.copy()
        for col in ["명세서ID", "제품코드", "정식제품명"]:
            if col not in items.columns:
                items[col] = ""
        item_mask = items["정식제품명"].astype(str).str.contains(
            keyword, case=False, na=False, regex=False
        )
        if alias_codes:
            item_mask = item_mask | items["제품코드"].astype(str).isin(alias_codes)
        matching_ids = set(items.loc[item_mask, "명세서ID"].astype(str))
        filtered = filtered[filtered["명세서ID"].astype(str).isin(matching_ids)]

    return filtered.drop(columns=["_date"], errors="ignore")


def _delete_statement(purchase_module, statement_id, statements, statement_items, price_history):
    remaining_statements = statements[statements["명세서ID"].astype(str) != str(statement_id)].copy()
    remaining_items = statement_items[
        statement_items["명세서ID"].astype(str) != str(statement_id)
    ].copy()
    remaining_prices = price_history[
        price_history["명세서ID"].astype(str) != str(statement_id)
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


def statement_list(purchase_module, data) -> None:
    st = purchase_module.st
    statements, statement_items, price_history, _ = purchase_module.load_purchase_data()
    orders = data["orders"]
    order_items = data["order_items"]
    aliases = data["aliases"]

    st.markdown("## 거래명세서 내역")
    if statements.empty:
        st.info("등록된 거래명세서가 없습니다.")
        return

    st.markdown(
        """
<style>
.st-key-statement_history_filters {
    width: 70vw;
    max-width: 70vw;
}
.st-key-statement_history_filters [data-testid="stHorizontalBlock"] {
    width: 100%;
}
.st-key-statement_history_results {
    width: 60vw;
    max-width: 60vw;
}
.st-key-statement_history_results [data-testid="stExpander"] {
    width: 100%;
}
.statement-summary-title {
    font-size: 21px;
    font-weight: 800;
    margin: 22px 0 8px 0;
}
.statement-total-box {
    font-size: 23px;
    font-weight: 800;
    padding: 10px 0 16px 0;
}
</style>
""",
        unsafe_allow_html=True,
    )

    today = datetime.now().date()
    vendor_options = ["전체"] + sorted(
        statements["거래처명"].astype(str).replace("", pd.NA).dropna().unique().tolist()
    )

    with st.container(key="statement_history_filters"):
        c1, c2, c3, c4 = st.columns([1, 1, 3, 5], gap="small")
        start_date = c1.date_input("시작", value=today, key="statement_history_start")
        end_date = c2.date_input("끝", value=today, key="statement_history_end")
        vendor = c3.selectbox("거래처별 검색", vendor_options, key="statement_history_vendor")
        keyword = c4.text_input(
            "제품명/별칭 검색",
            value="",
            placeholder="정식제품명 또는 별칭 입력",
            key="statement_history_keyword",
        )

    if start_date > end_date:
        st.warning("시작일은 종료일보다 늦을 수 없습니다.")
        return

    filtered = _filter_statements(
        statements, statement_items, aliases, start_date, end_date, vendor, keyword
    )
    if filtered.empty:
        st.info("검색 조건에 맞는 거래명세서가 없습니다.")
        return

    order_lookup = orders.copy()
    if not order_lookup.empty:
        order_lookup["발주ID"] = order_lookup["발주ID"].astype(str)

    filtered = filtered.sort_values(["명세서일자", "등록일시"], ascending=False)
    order_ids = filtered["발주ID"].astype(str).drop_duplicates().tolist()
    st.caption(f"검색 결과: 발주서 {len(order_ids):,}건 / 거래명세서 {len(filtered):,}건")

    with st.container(key="statement_history_results"):
        for order_id in order_ids:
            linked_statements = filtered[filtered["발주ID"].astype(str) == order_id].copy()
            vendor_name = str(linked_statements.iloc[0].get("거래처명", ""))

            header_rows = order_lookup[order_lookup["발주ID"] == order_id] if not order_lookup.empty else pd.DataFrame()
            if not header_rows.empty:
                order_date = _date_text(header_rows.iloc[0].get("발주일시", ""))
            else:
                order_date = _date_text(linked_statements.iloc[0].get("명세서일자", ""))

            label = f"[{vendor_name}] {order_date} | {order_id}"
            with st.expander(label, expanded=False):
                st.markdown('<div class="statement-summary-title">1) 전체 발주 내용</div>', unsafe_allow_html=True)
                order_rows = order_items[order_items["발주ID"].astype(str) == order_id].copy()
                if order_rows.empty:
                    st.info("저장된 발주 품목이 없습니다.")
                else:
                    st.dataframe(
                        _order_table(order_rows, purchase_module),
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "No.": st.column_config.NumberColumn(width="small"),
                            "정식제품명": st.column_config.TextColumn(width="large"),
                        },
                    )

                linked_ids = linked_statements["명세서ID"].astype(str).tolist()
                linked_items = statement_items[
                    statement_items["명세서ID"].astype(str).isin(linked_ids)
                ].copy()
                total_received = (
                    linked_items["입고수량"].apply(lambda value: _to_int(purchase_module, value)).sum()
                    if not linked_items.empty else 0
                )
                product_amount = (
                    linked_items["상품금액"].apply(lambda value: _to_int(purchase_module, value)).sum()
                    if not linked_items.empty else 0
                )
                freight_amount = linked_statements["운송비"].apply(
                    lambda value: _to_int(purchase_module, value)
                ).sum()
                total_purchase = int(product_amount + freight_amount)

                st.markdown('<div class="statement-summary-title">2) 연결된 거래명세서</div>', unsafe_allow_html=True)
                m1, m2, m3 = st.columns(3)
                m1.metric("연결 거래명세서", f"{len(linked_statements):,}건")
                m2.metric("총 입고수량", f"{int(total_received):,}")
                m3.metric("총 매입금액", f"{total_purchase:,}원")

                for seq, (_, statement) in enumerate(linked_statements.iterrows(), 1):
                    statement_id = str(statement.get("명세서ID", ""))
                    statement_no = str(statement.get("명세서번호", "")) or str(seq)
                    statement_date = _date_text(statement.get("명세서일자", ""))
                    st.markdown(f"### {seq}번 거래명세서 · 번호 {statement_no} · {statement_date}")

                    items = statement_items[
                        statement_items["명세서ID"].astype(str) == statement_id
                    ].copy()
                    if items.empty:
                        st.info("이 거래명세서에는 저장된 품목이 없습니다.")
                        received_qty = 0
                        item_amount = 0
                    else:
                        st.dataframe(
                            _statement_table(items, purchase_module),
                            use_container_width=True,
                            hide_index=True,
                            column_config={
                                "No.": st.column_config.NumberColumn(width="small"),
                                "정식제품명": st.column_config.TextColumn(width="large"),
                            },
                        )
                        received_qty = int(
                            items["입고수량"].apply(lambda value: _to_int(purchase_module, value)).sum()
                        )
                        item_amount = int(
                            items["상품금액"].apply(lambda value: _to_int(purchase_module, value)).sum()
                        )

                    freight = _to_int(purchase_module, statement.get("운송비", 0))
                    statement_total = item_amount + freight
                    t1, t2 = st.columns(2)
                    t1.markdown(
                        f'<div class="statement-total-box">입고수량 합계&nbsp;&nbsp;{received_qty:,}</div>',
                        unsafe_allow_html=True,
                    )
                    t2.markdown(
                        f'<div class="statement-total-box">매입금액 합계&nbsp;&nbsp;{statement_total:,}원</div>',
                        unsafe_allow_html=True,
                    )
                    st.caption(
                        f"상품금액 {_money(purchase_module, item_amount)} + 배송비 {_money(purchase_module, freight)}"
                    )

                    confirm_key = f"delete_statement_confirm_{statement_id}"
                    delete_col, _ = st.columns([1, 4])
                    with delete_col:
                        confirmed = st.checkbox("삭제 확인", key=confirm_key)
                        if st.button(
                            "이 거래명세서 삭제",
                            key=f"delete_statement_{statement_id}",
                            disabled=not confirmed,
                            use_container_width=True,
                        ):
                            _delete_statement(
                                purchase_module,
                                statement_id,
                                statements,
                                statement_items,
                                price_history,
                            )
                            st.success(f"{statement_no}번 거래명세서를 삭제했습니다.")
                            st.rerun()

                    if seq < len(linked_statements):
                        st.markdown("---")


def monthly(purchase_module, data) -> None:
    accounting_export.render(purchase_module, data)
