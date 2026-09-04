"""거래명세서 등록·내역 보강 화면."""
from __future__ import annotations

from datetime import datetime

import pandas as pd

from ui.pages import purchases
from ui.pages.statement_register_substitution import _normalize_expiry


def _to_int(purchase_module, value) -> int:
    return purchase_module.to_int(value)


def _item_key(row) -> tuple:
    code = str(row.get("제품코드", "") or "").strip()
    if code:
        return ("CODE", code)
    return (
        "TEXT",
        str(row.get("정식제품명", row.get("제품명", "")) or "").strip(),
        str(row.get("규격", "") or "").strip(),
        str(row.get("단위", row.get("포장단위", "")) or "").strip(),
    )


def _open_orders(purchase_module, orders: pd.DataFrame, order_items: pd.DataFrame):
    statements, statement_items, _, _ = purchase_module.load_purchase_data()
    if orders.empty:
        return orders.copy(), order_items.iloc[0:0].copy()

    received_by_order: dict[str, dict[tuple, int]] = {}
    if not statements.empty and not statement_items.empty:
        statement_order = statements.set_index("명세서ID")["발주ID"].astype(str).to_dict()
        for _, row in statement_items.iterrows():
            order_id = statement_order.get(str(row.get("명세서ID", "")), "")
            if not order_id:
                continue
            order_received = received_by_order.setdefault(order_id, {})
            key = _item_key(row)
            order_received[key] = order_received.get(key, 0) + _to_int(purchase_module, row.get("입고수량", 0))

    open_ids: list[str] = []
    for order_id in orders["발주ID"].astype(str).tolist():
        rows = order_items[order_items["발주ID"].astype(str) == order_id]
        if rows.empty:
            continue
        received = received_by_order.get(order_id, {})
        if any(received.get(_item_key(row), 0) < _to_int(purchase_module, row.get("수량", 0)) for _, row in rows.iterrows()):
            open_ids.append(order_id)

    return (
        orders[orders["발주ID"].astype(str).isin(open_ids)].copy(),
        order_items[order_items["발주ID"].astype(str).isin(open_ids)].copy(),
    )


def register(purchase_module, data) -> None:
    st = purchase_module.st
    open_orders, open_items = _open_orders(purchase_module, data["orders"], data["order_items"])
    if open_orders.empty:
        st.markdown("## 거래명세서 등록")
        st.info("입고가 남아 있는 발주서가 없습니다.")
        return
    purchase_module.page_statement_register(open_orders, open_items)


def _matching_order_ids_by_product(statement_items, aliases, keyword: str) -> set[str]:
    keyword = str(keyword or "").strip()
    if not keyword:
        return set()
    alias_codes = purchases._matching_product_codes(aliases, keyword)
    items = statement_items.copy()
    for col in ["명세서ID", "제품코드", "정식제품명"]:
        if col not in items.columns:
            items[col] = ""
    mask = items["정식제품명"].astype(str).str.contains(keyword, case=False, na=False, regex=False)
    if alias_codes:
        mask = mask | items["제품코드"].astype(str).isin(alias_codes)
    return set(items.loc[mask, "명세서ID"].astype(str))


def _statement_display_table(items: pd.DataFrame, purchase_module):
    rows = items.copy()
    for col in ["정식제품명", "규격", "입고수량", "단위", "포장단위", "매입단가", "출고단가", "상품금액"]:
        if col not in rows.columns:
            rows[col] = ""
    rows["수량"] = rows["입고수량"].apply(lambda v: _to_int(purchase_module, v))
    rows["포장단위"] = rows.apply(lambda r: str(r.get("포장단위", "") or r.get("단위", "")), axis=1)
    rows["매입단가"] = rows["매입단가"].apply(lambda v: f"{_to_int(purchase_module, v):,}원")
    rows["상품금액"] = rows.apply(
        lambda r: f"{(_to_int(purchase_module, r.get('상품금액', 0)) or (_to_int(purchase_module, r.get('입고수량', 0)) * _to_int(purchase_module, r.get('매입단가', 0)))):,}원",
        axis=1,
    )
    rows["매출단가"] = rows.apply(
        lambda r: f"{(_to_int(purchase_module, r.get('출고단가', 0)) or int(round(_to_int(purchase_module, r.get('매입단가', 0)) * 1.3))):,}원",
        axis=1,
    )
    rows = rows.reset_index(drop=True)
    rows.insert(0, "No.", range(1, len(rows) + 1))
    display = rows[["No.", "정식제품명", "규격", "수량", "포장단위", "매입단가", "상품금액", "매출단가"]]
    return display.style.set_properties(subset=["매출단가"], **{"background-color": "#f3f4f6", "color": "#4b5563"})


def _editable_items(items: pd.DataFrame, purchase_module) -> pd.DataFrame:
    columns = [
        "제품코드", "정식제품명", "규격", "단위", "발주수량", "입고수량", "매입단가",
        "제조번호", "유통기한",
    ]
    editable = items.copy().fillna("")
    for col in columns:
        if col not in editable.columns:
            editable[col] = ""
    for col in ["발주수량", "입고수량", "매입단가"]:
        editable[col] = editable[col].apply(lambda value: _to_int(purchase_module, value))
    for col in ["제조번호", "유통기한"]:
        editable[col] = editable[col].astype(str)
    return editable[columns].reset_index(drop=True)


def _save_statement_edit(
    purchase_module,
    statement_id: str,
    statements: pd.DataFrame,
    statement_items: pd.DataFrame,
    price_history: pd.DataFrame,
    statement_number: str,
    statement_date,
    freight: int,
    memo: str,
    edited_items: pd.DataFrame,
) -> None:
    statement_id = str(statement_id or "").strip()
    mask = statements["명세서ID"].astype(str).str.strip() == statement_id
    if int(mask.sum()) != 1:
        raise ValueError("수정할 거래명세서를 한 건으로 확인할 수 없습니다.")

    clean_items = edited_items.copy().fillna("")
    clean_items["정식제품명"] = clean_items["정식제품명"].astype(str).str.strip()
    clean_items = clean_items[clean_items["정식제품명"] != ""].reset_index(drop=True)
    if clean_items.empty:
        raise ValueError("거래명세서에는 품목이 한 개 이상 있어야 합니다.")

    date_text = pd.to_datetime(statement_date).strftime("%Y-%m-%d")
    now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    updated = statements.copy()
    updated.loc[mask, "명세서번호"] = str(statement_number or "").strip()
    updated.loc[mask, "명세서일자"] = date_text
    updated.loc[mask, "운송비"] = int(freight)
    updated.loc[mask, "운송비입력여부"] = "입력"
    updated.loc[mask, "메모"] = str(memo or "")
    updated.loc[mask, "수정일시"] = now_text

    item_rows = []
    price_rows = []
    for sequence, (_, row) in enumerate(clean_items.iterrows(), 1):
        quantity = max(0, _to_int(purchase_module, row.get("입고수량", 0)))
        purchase_price = max(0, _to_int(purchase_module, row.get("매입단가", 0)))
        sale_price = int(round(purchase_price * 1.3))
        product_amount = quantity * purchase_price
        product_code = str(row.get("제품코드", "") or "").strip()
        product_name = str(row.get("정식제품명", "") or "").strip()
        try:
            expiry = _normalize_expiry(row.get("유통기한", ""))
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        item_rows.append({
            "명세서ID": statement_id,
            "순번": sequence,
            "제품코드": product_code,
            "정식제품명": product_name,
            "규격": str(row.get("규격", "") or ""),
            "단위": str(row.get("단위", "") or ""),
            "발주수량": max(0, _to_int(purchase_module, row.get("발주수량", 0))),
            "입고수량": quantity,
            "매입단가": purchase_price,
            "상품금액": product_amount,
            "출고단가": sale_price,
            "가격적용여부": "적용",
            "제조번호": str(row.get("제조번호", "") or "").strip(),
            "유통기한": expiry,
        })
        price_rows.append({
            "가격ID": f"PRICE-{statement_id}-{sequence}",
            "명세서ID": statement_id,
            "명세서일자": date_text,
            "제품코드": product_code,
            "정식제품명": product_name,
            "매입단가": purchase_price,
            "출고단가": sale_price,
            "등록일시": now_text,
        })

    remaining_items = statement_items[
        statement_items["명세서ID"].astype(str).str.strip() != statement_id
    ].copy()
    updated_items = pd.concat([remaining_items, pd.DataFrame(item_rows)], ignore_index=True)
    remaining_prices = price_history[
        price_history["명세서ID"].astype(str).str.strip() != statement_id
    ].copy()
    updated_prices = pd.concat([remaining_prices, pd.DataFrame(price_rows)], ignore_index=True)

    purchase_module.save_table(purchase_module.STATEMENTS_FILE, updated, purchase_module.STATEMENT_COLUMNS)
    purchase_module.save_table(
        purchase_module.STATEMENT_ITEMS_FILE,
        updated_items,
        purchase_module.STATEMENT_ITEM_COLUMNS,
    )
    purchase_module.save_table(
        purchase_module.PRICE_HISTORY_FILE,
        updated_prices,
        purchase_module.PRICE_HISTORY_COLUMNS,
    )


def statement_list(purchase_module, data) -> None:
    st = purchase_module.st
    statements, statement_items, price_history, _ = purchase_module.load_purchase_data()
    orders = data["orders"].copy()
    order_items = data["order_items"]
    aliases = data["aliases"]

    st.markdown("## 거래명세서 내역")
    if statements.empty or orders.empty:
        st.info("등록된 거래명세서가 없습니다.")
        return

    st.markdown(
        """
<style>
.st-key-statement_history_filters { width: 100%; max-width: 100%; }
.st-key-statement_history_results { width: 100%; max-width: 100%; }
[class*="st-key-statement_order_content_"] { width: 30vw; max-width: 30vw; }
.statement-summary-title { font-size: 21px; font-weight: 800; margin: 22px 0 8px 0; }
.statement-total-box { font-size: 23px; font-weight: 800; padding: 10px 0 2px 0; }
.statement-total-detail { font-size: 14px; color: #6b7280; margin: 0 0 16px 0; }
@media (max-width: 1100px) {
    [class*="st-key-statement_order_content_"] { width: 100%; max-width: 100%; }
}
</style>
""",
        unsafe_allow_html=True,
    )

    orders["발주ID"] = orders["발주ID"].astype(str)
    orders["_order_date"] = pd.to_datetime(orders["발주일시"], errors="coerce").dt.date
    today = datetime.now().date()
    vendor_options = ["전체"] + sorted(orders["거래처명"].astype(str).replace("", pd.NA).dropna().unique().tolist())

    with st.container(key="statement_history_filters"):
        c1, c2, c3, c4 = st.columns([1, 1, 3, 5], gap="small")
        start_date = c1.date_input("시작", value=today, key="statement_history_start")
        end_date = c2.date_input("끝", value=today, key="statement_history_end")
        vendor = c3.selectbox("거래처별 검색", vendor_options, key="statement_history_vendor")
        keyword = c4.text_input("제품명/별칭 검색", placeholder="정식제품명 또는 별칭 입력", key="statement_history_keyword")

    if start_date > end_date:
        st.warning("시작일은 종료일보다 늦을 수 없습니다.")
        return

    matched_orders = orders[(orders["_order_date"] >= start_date) & (orders["_order_date"] <= end_date)].copy()
    if vendor != "전체":
        matched_orders = matched_orders[matched_orders["거래처명"].astype(str) == vendor]

    keyword_text = str(keyword or "").strip()
    if keyword_text:
        matching_statement_ids = _matching_order_ids_by_product(statement_items, aliases, keyword_text)
        matching_order_ids = set(
            statements[statements["명세서ID"].astype(str).isin(matching_statement_ids)]["발주ID"].astype(str)
        )
        matched_orders = matched_orders[matched_orders["발주ID"].isin(matching_order_ids)]

    linked_order_ids = set(statements["발주ID"].astype(str))
    matched_orders = matched_orders[matched_orders["발주ID"].isin(linked_order_ids)].sort_values("발주일시", ascending=False)
    if matched_orders.empty:
        st.info("검색 조건에 맞는 발주서가 없습니다.")
        return

    st.caption(f"검색 결과: 발주서 {len(matched_orders):,}건")
    with st.container(key="statement_history_results"):
        for _, order in matched_orders.iterrows():
            order_id = str(order.get("발주ID", ""))
            vendor_name = str(order.get("거래처명", ""))
            order_date = purchases._date_text(order.get("발주일시", ""))
            linked_statements = statements[statements["발주ID"].astype(str) == order_id].copy().sort_values(["명세서일자", "등록일시"])
            label = f"[{vendor_name}] {order_date} | {order_id}"

            with st.expander(label, expanded=False):
                with st.container(key=f"statement_order_content_{order_id}"):
                    st.markdown('<div class="statement-summary-title">1) 전체 발주 내용</div>', unsafe_allow_html=True)
                    order_rows = order_items[order_items["발주ID"].astype(str) == order_id]
                    st.dataframe(purchases._order_table(order_rows, purchase_module), use_container_width=True, hide_index=True)

                linked_ids = linked_statements["명세서ID"].astype(str).tolist()
                all_items = statement_items[statement_items["명세서ID"].astype(str).isin(linked_ids)].copy()
                total_received = all_items["입고수량"].apply(lambda v: _to_int(purchase_module, v)).sum() if not all_items.empty else 0
                product_amount = all_items["상품금액"].apply(lambda v: _to_int(purchase_module, v)).sum() if not all_items.empty else 0
                freight_amount = linked_statements["운송비"].apply(lambda v: _to_int(purchase_module, v)).sum()
                total_purchase = int(product_amount + freight_amount)

                st.markdown('<div class="statement-summary-title">2) 연결된 거래명세서</div>', unsafe_allow_html=True)
                m1, m2, m3, _ = st.columns([1, 1, 1, 3], gap="small")
                m1.metric("연결 거래명세서", f"{len(linked_statements):,}건")
                m2.metric("총 입고수량", f"{int(total_received):,}")
                m3.metric("총 매입금액", f"{total_purchase:,}원")

                for seq, (_, statement) in enumerate(linked_statements.iterrows(), 1):
                    statement_id = str(statement.get("명세서ID", ""))
                    statement_no = str(statement.get("명세서번호", "")) or str(seq)
                    statement_date = purchases._date_text(statement.get("명세서일자", ""))
                    st.markdown(f"### {seq}번 거래명세서 · 번호 {statement_no} · {statement_date}")
                    items = statement_items[statement_items["명세서ID"].astype(str) == statement_id].copy()
                    if items.empty:
                        st.info("이 거래명세서에는 저장된 품목이 없습니다.")
                        received_qty = item_amount = 0
                    else:
                        st.dataframe(_statement_display_table(items, purchase_module), use_container_width=True, hide_index=True)
                        received_qty = int(items["입고수량"].apply(lambda v: _to_int(purchase_module, v)).sum())
                        item_amount = int(items["상품금액"].apply(lambda v: _to_int(purchase_module, v)).sum())

                    freight = _to_int(purchase_module, statement.get("운송비", 0))
                    statement_total = item_amount + freight
                    t1, t2 = st.columns(2)
                    t1.markdown(f'<div class="statement-total-box">입고수량 합계&nbsp;&nbsp;{received_qty:,}</div>', unsafe_allow_html=True)
                    t2.markdown(f'<div class="statement-total-box">매입금액 합계&nbsp;&nbsp;{statement_total:,}원</div>', unsafe_allow_html=True)
                    t2.markdown(
                        f'<div class="statement-total-detail">상품금액 {item_amount:,}원 + 배송비 {freight:,}원</div>',
                        unsafe_allow_html=True,
                    )

                    edit_col, delete_col, _, confirm_col = st.columns([1, 1, 3, 1.2], gap="small")
                    with confirm_col:
                        confirmed = st.checkbox("삭제 확인", key=f"delete_statement_confirm_{statement_id}")
                    with edit_col:
                        if st.button("거래명세서 수정", key=f"edit_statement_{statement_id}", use_container_width=True):
                            st.session_state["editing_statement_id"] = statement_id
                    with delete_col:
                        if st.button("거래명세서 삭제", key=f"delete_statement_{statement_id}", disabled=not confirmed, use_container_width=True):
                            purchases._delete_statement(purchase_module, statement_id, statements, statement_items, price_history)
                            st.success(f"{statement_no}번 거래명세서를 삭제했습니다.")
                            st.rerun()

                    if st.session_state.get("editing_statement_id") == statement_id:
                        parsed_date = pd.to_datetime(statement.get("명세서일자", ""), errors="coerce")
                        initial_date = today if pd.isna(parsed_date) else parsed_date.date()
                        with st.form(key=f"edit_statement_form_{statement_id}"):
                            st.markdown("#### 거래명세서 수정")
                            f1, f2, f3 = st.columns([2, 2, 2])
                            edited_number = f1.text_input("명세서 번호", value=str(statement.get("명세서번호", "")))
                            edited_date = f2.date_input("명세서 일자", value=initial_date)
                            edited_freight = f3.number_input(
                                "배송비",
                                min_value=0,
                                step=100,
                                value=_to_int(purchase_module, statement.get("운송비", 0)),
                            )
                            edited_memo = st.text_area("메모", value=str(statement.get("메모", "") or ""))
                            st.markdown("##### 품목 수정")
                            st.caption("수량과 매입단가를 바꾸면 상품금액과 매출단가가 자동으로 다시 계산됩니다. 행을 추가하거나 삭제할 수도 있습니다.")
                            edited_items = st.data_editor(
                                _editable_items(items, purchase_module),
                                key=f"edit_statement_items_{statement_id}",
                                use_container_width=True,
                                hide_index=True,
                                num_rows="dynamic",
                                disabled=["제품코드", "발주수량"],
                                column_config={
                                    "입고수량": st.column_config.NumberColumn(min_value=0, step=1),
                                    "매입단가": st.column_config.NumberColumn(min_value=0, step=100, format="%d원"),
                                    "제조번호": st.column_config.TextColumn(),
                                    "유통기한": st.column_config.TextColumn(
                                        help="예: 2026-12-31, 20261231, 261231"
                                    ),
                                },
                            )
                            save_col, cancel_col = st.columns(2)
                            save_clicked = save_col.form_submit_button("수정 내용 저장", type="primary", use_container_width=True)
                            cancel_clicked = cancel_col.form_submit_button("취소", use_container_width=True)

                        if save_clicked:
                            try:
                                _save_statement_edit(
                                    purchase_module,
                                    statement_id,
                                    statements,
                                    statement_items,
                                    price_history,
                                    edited_number,
                                    edited_date,
                                    int(edited_freight),
                                    edited_memo,
                                    edited_items,
                                )
                            except ValueError as exc:
                                st.error(str(exc))
                            else:
                                st.session_state.pop("editing_statement_id", None)
                                st.success(f"{statement_no}번 거래명세서를 수정했습니다.")
                                st.rerun()
                        elif cancel_clicked:
                            st.session_state.pop("editing_statement_id", None)
                            st.rerun()

                    if seq < len(linked_statements):
                        st.markdown("---")
