"""발주 검색, 선택 발주일자 저장, 거래명세서 입력 흐름을 보정하는 실행 런처."""

from datetime import date, datetime

import pandas as pd

import app_purchase_management as purchase

base_app = purchase.base_app
ORIGINAL_TEXT_INPUT = base_app.st.text_input


def text_input_without_default_sample(label, *args, **kwargs):
    """발주 검색창의 예시값 '마취크림'을 실제 입력값으로 사용하지 않습니다."""
    if label == "검색" and kwargs.get("value") == "마취크림":
        kwargs["value"] = ""
        kwargs.setdefault("key", "product_search_keyword")
    return ORIGINAL_TEXT_INPUT(label, *args, **kwargs)


def _empty_result():
    return pd.DataFrame(columns=[
        "별칭(검색어)", "제품코드", "정식제품명", "규격", "단위", "점수", "매칭구분"
    ])


def _sort_results(rows):
    """실제 별칭 일치 결과를 제품명 직접검색보다 항상 먼저 정렬합니다."""
    if not rows:
        return _empty_result()

    result = pd.DataFrame(rows)
    result["검색우선순위"] = result["매칭구분"].map({"별칭": 0, "제품명": 1}).fillna(2)
    result = result.sort_values(
        ["검색우선순위", "점수", "정식제품명"],
        ascending=[True, False, True],
    )
    result = result.drop_duplicates("제품코드", keep="first").head(30)
    return result.drop(columns=["검색우선순위"]).reset_index(drop=True)


def search_products(keyword, vendor_name, products, aliases):
    """빠른 포함검색을 우선하고, 별칭 결과를 제품명 직접검색보다 먼저 보여줍니다."""
    keyword = str(keyword or "").strip()
    if not keyword:
        return _empty_result()

    keyword_lower = keyword.casefold()
    active = products.copy().fillna("")
    alias_df = aliases.copy().fillna("")
    alias_df = alias_df[alias_df["거래처명"].isin([vendor_name, "전체", ""])]

    product_lookup = active.drop_duplicates("제품코드").set_index("제품코드", drop=False)
    rows = []

    if not alias_df.empty:
        alias_text = alias_df["별칭"].astype(str).str.strip()
        alias_mask = alias_text.str.casefold().str.contains(keyword_lower, regex=False, na=False)
        for _, alias_row in alias_df[alias_mask].head(30).iterrows():
            code = str(alias_row.get("제품코드", "")).strip()
            if not code or code not in product_lookup.index:
                continue
            p = product_lookup.loc[code]
            alias = str(alias_row.get("별칭", "")).strip()
            rows.append({
                "별칭(검색어)": alias,
                "제품코드": p["제품코드"],
                "정식제품명": p["정식제품명"],
                "규격": p["규격"],
                "단위": p["단위"],
                "점수": 130 if alias.casefold() == keyword_lower else 110,
                "매칭구분": "별칭",
            })

    product_name = active["정식제품명"].astype(str).str.strip()
    product_code = active["제품코드"].astype(str).str.strip()
    direct_mask = (
        product_name.str.casefold().str.contains(keyword_lower, regex=False, na=False)
        | product_code.str.casefold().str.contains(keyword_lower, regex=False, na=False)
    )
    for _, p in active[direct_mask].head(30).iterrows():
        official = str(p.get("정식제품명", "")).strip()
        code = str(p.get("제품코드", "")).strip()
        exact = official.casefold() == keyword_lower or code.casefold() == keyword_lower
        rows.append({
            "별칭(검색어)": "제품명 직접검색",
            "제품코드": p["제품코드"],
            "정식제품명": p["정식제품명"],
            "규격": p["규격"],
            "단위": p["단위"],
            "점수": 120 if exact else 100,
            "매칭구분": "제품명",
        })

    if rows:
        return _sort_results(rows)

    if len(keyword) < 2:
        return _empty_result()

    fuzzy_rows = []
    for _, alias_row in alias_df.head(500).iterrows():
        alias = str(alias_row.get("별칭", "")).strip()
        code = str(alias_row.get("제품코드", "")).strip()
        if not alias or not code or code not in product_lookup.index:
            continue
        score = base_app.fuzz.partial_ratio(keyword, alias)
        if score >= 70:
            p = product_lookup.loc[code]
            fuzzy_rows.append({
                "별칭(검색어)": alias,
                "제품코드": p["제품코드"],
                "정식제품명": p["정식제품명"],
                "규격": p["규격"],
                "단위": p["단위"],
                "점수": score + 10,
                "매칭구분": "별칭",
            })

    for _, p in active.head(1000).iterrows():
        official = str(p.get("정식제품명", "")).strip()
        if not official:
            continue
        score = base_app.fuzz.partial_ratio(keyword, official)
        if score >= 70:
            fuzzy_rows.append({
                "별칭(검색어)": "제품명 직접검색",
                "제품코드": p["제품코드"],
                "정식제품명": p["정식제품명"],
                "규격": p["규격"],
                "단위": p["단위"],
                "점수": score,
                "매칭구분": "제품명",
            })

    return _sort_results(fuzzy_rows)


def _selected_order_date():
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


def save_order_with_selected_date(vendor_name, request_note, order_items):
    """선택한 발주일자로 발주ID와 발주일시를 생성해 저장합니다."""
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
    order_id = f"PO-{selected_datetime.strftime('%Y%m%d-%H%M%S')}"

    existing_ids = set(orders["발주ID"].astype(str).tolist())
    if order_id in existing_ids:
        suffix = 2
        candidate = f"{order_id}-{suffix}"
        while candidate in existing_ids:
            suffix += 1
            candidate = f"{order_id}-{suffix}"
        order_id = candidate

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


def _next_statement_number(statements, order_id):
    """선택한 발주서에 연결된 다음 거래명세서 번호를 반환합니다."""
    related = statements[statements["발주ID"].astype(str) == str(order_id)]
    numbers = pd.to_numeric(related["명세서번호"], errors="coerce").dropna().astype(int).tolist()
    return max(numbers) + 1 if numbers else 1


def page_statement_register_simple(orders, order_items_saved):
    """품목 선택, 입고수량, 매입단가만 입력하는 간단한 거래명세서 등록 화면입니다."""
    purchase.ensure_purchase_files()
    statements, statement_items, price_history, _ = purchase.load_purchase_data()

    base_app.st.markdown("## 거래명세서 등록")
    base_app.st.caption("발주 품목 중 실제로 들어온 품목만 선택하고 입고수량과 매입단가를 입력하세요.")

    if orders.empty:
        base_app.st.info("등록된 발주서가 없습니다.")
        return

    ordered = orders.copy().sort_values("발주일시", ascending=False)
    order_ids = ordered["발주ID"].astype(str).tolist()
    vendor_map = ordered.set_index("발주ID")["거래처명"].astype(str).to_dict()
    selected_order = base_app.st.selectbox(
        "연결할 발주서",
        order_ids,
        format_func=lambda oid: f'[{vendor_map.get(oid, "")}] {oid}',
    )

    order_header = ordered[ordered["발주ID"].astype(str) == str(selected_order)].iloc[0]
    order_rows = order_items_saved[order_items_saved["발주ID"].astype(str) == str(selected_order)].copy()
    if order_rows.empty:
        base_app.st.warning("이 발주서에는 품목이 없습니다.")
        return

    statement_number = _next_statement_number(statements, selected_order)
    received = purchase.get_received_by_order(statement_items, statements, selected_order)

    order_rows["발주수량"] = order_rows["수량"].apply(purchase.to_int)
    order_rows["누적입고수량"] = order_rows["제품코드"].map(lambda code: int(received.get(code, 0)))
    order_rows["남은발주수량"] = order_rows["발주수량"] - order_rows["누적입고수량"]
    order_rows["남은발주수량"] = order_rows["남은발주수량"].clip(lower=0)
    order_rows["선택"] = False
    order_rows["입고수량"] = 0
    order_rows["매입단가"] = 0
    order_rows["가격적용여부"] = True

    with base_app.st.container(border=True):
        c1, c2, c3 = base_app.st.columns(3)
        c1.text_input("거래명세서 번호", value=str(statement_number), disabled=True)
        statement_date = c2.date_input("거래명세서 일자", value=datetime.now().date())
        freight = c3.number_input("운송비(배송비)", min_value=0, value=0, step=1000)
        freight_checked = base_app.st.checkbox(
            "운송비 입력 완료",
            value=False,
            help="실제 운송비가 0원이어도 체크하면 누락으로 보지 않습니다.",
        )
        memo = base_app.st.text_area("메모", height=70)

    edit_cols = [
        "선택", "정식제품명", "규격", "단위", "남은발주수량", "입고수량", "매입단가", "가격적용여부"
    ]
    edited = base_app.st.data_editor(
        order_rows[edit_cols],
        use_container_width=True,
        hide_index=True,
        disabled=["정식제품명", "규격", "단위", "남은발주수량"],
        column_config={
            "선택": base_app.st.column_config.CheckboxColumn("입고 품목 선택"),
            "남은발주수량": base_app.st.column_config.NumberColumn("현재 남은 수량", min_value=0),
            "입고수량": base_app.st.column_config.NumberColumn("이번 입고수량", min_value=0, step=1),
            "매입단가": base_app.st.column_config.NumberColumn("매입단가", min_value=0, step=100),
            "가격적용여부": base_app.st.column_config.CheckboxColumn("현재 가격 적용"),
        },
        key=f"simple_statement_items_{selected_order}_{statement_number}",
    )

    working = order_rows.copy()
    for col in ["선택", "입고수량", "매입단가", "가격적용여부"]:
        working[col] = edited[col].values
    working["등록후남은수량"] = (
        working["남은발주수량"] - working["입고수량"].apply(purchase.to_int)
    ).clip(lower=0)

    selected_rows = working[working["선택"] == True].copy()
    if not selected_rows.empty:
        remain_view = selected_rows[["정식제품명", "남은발주수량", "입고수량", "등록후남은수량"]].copy()
        base_app.st.markdown("### 선택 품목 입고 후 남은 수량")
        base_app.st.dataframe(remain_view, use_container_width=True, hide_index=True)

    selected_rows["상품금액"] = selected_rows["입고수량"].apply(purchase.to_int) * selected_rows["매입단가"].apply(purchase.to_int)
    product_total = int(selected_rows["상품금액"].sum()) if not selected_rows.empty else 0
    total_qty = int(selected_rows["입고수량"].apply(purchase.to_int).sum()) if not selected_rows.empty else 0

    m1, m2, m3 = base_app.st.columns(3)
    m1.metric("이번 입고수량", f"{total_qty:,}개")
    m2.metric("상품 매입금액", f"{product_total:,}원")
    m3.metric("총 매입금액", f"{product_total + int(freight):,}원")

    if base_app.st.button("거래명세서 저장", type="primary", use_container_width=True):
        if selected_rows.empty:
            base_app.st.warning("입고된 품목을 하나 이상 선택하세요.")
            return
        if (selected_rows["입고수량"].apply(purchase.to_int) <= 0).any():
            base_app.st.warning("선택한 품목의 입고수량을 입력하세요.")
            return
        if (selected_rows["매입단가"].apply(purchase.to_int) <= 0).any():
            base_app.st.warning("선택한 품목의 매입단가를 입력하세요.")
            return
        if (selected_rows["입고수량"].apply(purchase.to_int) > selected_rows["남은발주수량"].apply(purchase.to_int)).any():
            base_app.st.warning("이번 입고수량이 남은 발주수량보다 큰 품목이 있습니다.")
            return

        sid = purchase.make_id("ST", statements["명세서ID"].tolist())
        now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        new_statement = pd.DataFrame([{
            "명세서ID": sid,
            "발주ID": selected_order,
            "거래처명": order_header["거래처명"],
            "명세서번호": str(statement_number),
            "명세서일자": statement_date.strftime("%Y-%m-%d"),
            "운송비": int(freight),
            "운송비입력여부": "Y" if freight_checked or int(freight) > 0 else "N",
            "메모": memo.strip(),
            "등록일시": now_text,
            "수정일시": now_text,
        }])

        item_rows = []
        price_rows = []
        existing_price_ids = price_history["가격ID"].tolist()
        for idx, row in selected_rows.reset_index(drop=True).iterrows():
            buy_price = purchase.to_int(row["매입단가"])
            qty = purchase.to_int(row["입고수량"])
            sell_price = purchase.calc_sell_price(buy_price)
            item_rows.append({
                "명세서ID": sid,
                "순번": idx + 1,
                "제품코드": row["제품코드"],
                "정식제품명": row["정식제품명"],
                "규격": row["규격"],
                "단위": row["단위"],
                "발주수량": purchase.to_int(row["발주수량"]),
                "입고수량": qty,
                "매입단가": buy_price,
                "상품금액": qty * buy_price,
                "출고단가": sell_price,
                "가격적용여부": "Y" if bool(row.get("가격적용여부", True)) else "N",
            })
            if bool(row.get("가격적용여부", True)):
                price_id = purchase.make_id("PR", existing_price_ids + [p.get("가격ID", "") for p in price_rows])
                price_rows.append({
                    "가격ID": price_id,
                    "명세서ID": sid,
                    "명세서일자": statement_date.strftime("%Y-%m-%d"),
                    "제품코드": row["제품코드"],
                    "정식제품명": row["정식제품명"],
                    "매입단가": buy_price,
                    "출고단가": sell_price,
                    "등록일시": now_text,
                })

        purchase.save_table(
            purchase.STATEMENTS_FILE,
            pd.concat([statements, new_statement], ignore_index=True),
            purchase.STATEMENT_COLUMNS,
        )
        purchase.save_table(
            purchase.STATEMENT_ITEMS_FILE,
            pd.concat([statement_items, pd.DataFrame(item_rows)], ignore_index=True),
            purchase.STATEMENT_ITEM_COLUMNS,
        )
        if price_rows:
            purchase.save_table(
                purchase.PRICE_HISTORY_FILE,
                pd.concat([price_history, pd.DataFrame(price_rows)], ignore_index=True),
                purchase.PRICE_HISTORY_COLUMNS,
            )

        base_app.st.success(f"거래명세서 {statement_number}번을 저장했습니다: {sid}")
        base_app.st.rerun()


base_app.st.text_input = text_input_without_default_sample
base_app.search_products = search_products
base_app.save_order = save_order_with_selected_date
purchase.page_statement_register = page_statement_register_simple


if __name__ == "__main__":
    purchase.main()
