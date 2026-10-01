"""단계별 품목 선택·입력을 지원하는 거래명세서 등록 화면.

"주문제품"(원래 발주한 제품명, 읽기전용)과 "입고제품"(실제로 들어온 제품명,
직접 수정 가능) 두 칸을 나란히 두고, 입고제품 이름이 주문제품과 다르면
그 제품을 최종 제품으로 저장한다. 입고제품 이름이 제품관리에 없으면
신규 제품으로 자동 등록하고, 저장 시 이 거래명세서의 거래처 별칭 관리에
(별칭=주문제품명, 연결제품=입고제품) 항목을 추가한다.
"""
from __future__ import annotations

import re
from datetime import datetime

import pandas as pd
from services.receipt_units import order_quantity, conversion_factor, convert_quantity
from services.statement_links import receipts_for_order, linked_order_ids, encode_order_ids, validate_links, save_statement_bundle

from ui.pages import catalog, statement_item_selection


def _to_int(purchase_module, value) -> int:
    return purchase_module.to_int(value)


def item_key(row) -> tuple:
    """입고수량을 원발주품목 기준으로 묶는 안정적인 식별키를 반환합니다.

    입고제품이 주문제품과 다른 행에는 실제 입고제품과 원발주제품 정보가
    함께 저장됩니다. 원발주제품코드가 비어 있더라도 원발주제품명/규격/단위가
    있으면 실제 입고제품 코드보다 원발주 텍스트 조합을 우선해야 발주 품목
    입고로 정상 집계됩니다.
    """
    original_code = str(row.get("원발주제품코드", "") or "").strip()
    original_name = str(row.get("원발주제품명", "") or "").strip()
    original_spec = str(row.get("원발주규격", "") or "").strip()
    original_unit = str(row.get("원발주단위", "") or "").strip()

    if original_code:
        return ("CODE", original_code)
    if original_name or original_spec or original_unit:
        return ("TEXT", original_name, original_spec, original_unit)

    code = str(row.get("제품코드", "") or "").strip()
    if code:
        return ("CODE", code)
    return (
        "TEXT",
        str(row.get("정식제품명", row.get("제품명", "")) or "").strip(),
        str(row.get("규격", "") or "").strip(),
        str(row.get("단위", row.get("포장단위", "")) or "").strip(),
    )


def _received_by_order(purchase_module, statements, statement_items, order_id: str) -> dict[tuple, int]:
    received: dict[tuple, int] = {}
    related = receipts_for_order(statements, statement_items, order_id)
    for _, row in related.iterrows():
        key = item_key(row)
        received[key] = received.get(key, 0) + order_quantity(row)
    return received


def _open_orders(purchase_module, orders, order_items):
    statements, statement_items, _, _ = purchase_module.load_purchase_data()
    open_ids = []
    for order_id in orders["발주ID"].astype(str).tolist():
        rows = order_items[order_items["발주ID"].astype(str) == order_id]
        if rows.empty:
            continue
        received = _received_by_order(purchase_module, statements, statement_items, order_id)
        if any(
            received.get(item_key(row), 0) < _to_int(purchase_module, row.get("수량", 0))
            for _, row in rows.iterrows()
        ):
            open_ids.append(order_id)
    return orders[orders["발주ID"].astype(str).isin(open_ids)].copy()


def _catalog(products: pd.DataFrame) -> tuple[list[str], dict[str, dict]]:
    rows = products.copy().fillna("")
    if "제품명" not in rows.columns:
        rows["제품명"] = rows.get("정식제품명", "")
    if "포장단위" not in rows.columns:
        rows["포장단위"] = rows.get("단위", "")
    rows["제품명"] = rows["제품명"].astype(str).str.strip()
    rows = rows[rows["제품명"] != ""].drop_duplicates(["제품코드", "제품명"], keep="first")
    lookup: dict[str, dict] = {}
    labels: list[str] = []
    for _, row in rows.iterrows():
        name = str(row.get("제품명", "") or "").strip()
        code = str(row.get("제품코드", "") or "").strip()
        label = f"{name} [{code}]" if code else name
        labels.append(label)
        lookup[label] = {
            "제품코드": code,
            "정식제품명": name,
            "규격": str(row.get("규격", "") or ""),
            "단위": str(row.get("포장단위", "") or ""),
        }
    return labels, lookup


def _product_name_lookup(products: pd.DataFrame) -> dict[str, dict]:
    """입고제품 이름으로 기존 제품을 찾기 위한 이름 기준 조회 테이블."""
    rows = catalog._normalize_products(products)
    lookup: dict[str, dict] = {}
    for _, row in rows.iterrows():
        name = str(row.get("제품명", "") or "").strip()
        if name and name not in lookup:
            lookup[name] = {
                "제품코드": str(row.get("제품코드", "") or ""),
                "규격": str(row.get("규격", "") or ""),
                "포장단위": str(row.get("포장단위", "") or ""),
            }
    return lookup


def _product_code_lookup(products: pd.DataFrame) -> dict[str, dict]:
    """제품코드로 기존 제품을 찾기 위한 코드 기준 조회 테이블."""
    rows = catalog._normalize_products(products)
    lookup: dict[str, dict] = {}
    for _, row in rows.iterrows():
        code = str(row.get("제품코드", "") or "").strip()
        if code and code not in lookup:
            lookup[code] = {
                "제품명": str(row.get("제품명", "") or ""),
                "규격": str(row.get("규격", "") or ""),
                "포장단위": str(row.get("포장단위", "") or ""),
            }
    return lookup


def _display_product_code(order_name: str, received_name: str, name_lookup: dict[str, dict]) -> str:
    """입고제품이 주문제품과 다를 때, 이름으로 찾으면 어떤 제품코드가 될지 미리 보여준다.

    직접 입력한 제품코드가 있으면 저장 시 이 값 대신 그 코드가 우선한다.
    같은 이름이면 원발주 제품코드와 같을 게 뻔하므로 표시하지 않는다.
    """
    order_name = str(order_name or "").strip()
    received_name = str(received_name or "").strip()
    if not received_name or received_name == order_name:
        return ""
    match = name_lookup.get(received_name)
    return match["제품코드"] if match else "(신규 등록)"


def _next_statement_number(statements: pd.DataFrame, order_id: str) -> int:
    if statements.empty:
        return 1
    linked = statements[statements.apply(lambda row: str(order_id) in linked_order_ids(row), axis=1)]
    numbers = []
    for value in linked.get("명세서번호", pd.Series(dtype=str)).tolist():
        try:
            numbers.append(int(float(str(value or "").strip())))
        except (TypeError, ValueError):
            continue
    return max(numbers) + 1 if numbers else 1


def _selection_rows(purchase_module, order_rows, statements, statement_items, selected_order):
    received_by_source = {}
    rows = []
    for source_index, (_, row) in enumerate(order_rows.reset_index(drop=True).iterrows()):
        source_order = str(row.get("발주ID", "") or selected_order)
        if source_order not in received_by_source:
            received_by_source[source_order] = _received_by_order(purchase_module, statements, statement_items, source_order)
        ordered_qty = _to_int(purchase_module, row.get("수량", 0))
        received_qty = received_by_source[source_order].get(item_key(row), 0)
        remaining = max(0, ordered_qty - received_qty)
        if remaining <= 0:
            continue
        rows.append({
            "선택": False,
            "품목번호": source_index,
            "입고발주ID": source_order,
            "발주일자": str(row.get("_발주일자", "") or ""),
            "제품코드": str(row.get("제품코드", "") or ""),
            "제품명": str(row.get("정식제품명", row.get("제품명", "")) or ""),
            "규격": str(row.get("규격", "") or ""),
            "포장단위": str(row.get("단위", row.get("포장단위", "")) or ""),
            "발주수량": ordered_qty,
            "누적입고": received_qty,
            "남은수량": remaining,
        })
    return pd.DataFrame(rows)


def _receipt_rows_state(st, selected_order: str) -> list[dict]:
    key = f"statement_receipt_rows_{selected_order}"
    rows = st.session_state.get(key)
    if not isinstance(rows, list):
        rows = []
        st.session_state[key] = rows
    return rows


def _receipt_row_version(st, selected_order: str) -> int:
    return int(st.session_state.get(f"statement_receipt_rows_version_{selected_order}", 0))


def _bump_receipt_row_version(st, selected_order: str) -> None:
    key = f"statement_receipt_rows_version_{selected_order}"
    st.session_state[key] = int(st.session_state.get(key, 0)) + 1


def _next_receipt_row_id(st, selected_order: str) -> int:
    key = f"statement_receipt_next_row_id_{selected_order}"
    next_id = int(st.session_state.get(key, 1))
    st.session_state[key] = next_id + 1
    return next_id


def _normalise_bool(value) -> bool:
    return bool(value) if not isinstance(value, str) else value.strip().lower() in {"y", "yes", "true", "1"}


def _freight_amount(value) -> int:
    try:
        return max(0, int(float(str(value or "0").replace(",", ""))))
    except (TypeError, ValueError):
        return 0


def _scaled_freight_value(value, operation: str) -> int:
    """운송비를 두 배 또는 절반으로 조정합니다."""
    amount = _freight_amount(value)
    if operation == "double":
        return amount * 2
    if operation == "half":
        return amount // 2
    raise ValueError("지원하지 않는 운송비 조정입니다.")


def _freight_input(st, container, selected_order: str) -> int:
    """직접 입력과 절반/두 배 단축 버튼을 함께 표시합니다."""
    freight_key = f"statement_freight_{selected_order}"
    if freight_key not in st.session_state:
        st.session_state[freight_key] = 0

    container.markdown("**운송비(배송비)**")
    minus_col, value_col, plus_col = container.columns([1, 3, 1], gap="small")
    if minus_col.button(
        "−",
        key=f"statement_freight_half_{selected_order}",
        help="현재 운송비를 절반으로 줄입니다.",
        use_container_width=True,
    ):
        st.session_state[freight_key] = _scaled_freight_value(
            st.session_state.get(freight_key, 0), "half"
        )
    if plus_col.button(
        "+",
        key=f"statement_freight_double_{selected_order}",
        help="현재 운송비를 2배로 늘립니다.",
        use_container_width=True,
    ):
        st.session_state[freight_key] = _scaled_freight_value(
            st.session_state.get(freight_key, 0), "double"
        )

    return int(
        value_col.number_input(
            "운송비(배송비)",
            min_value=0,
            step=1000,
            key=freight_key,
            label_visibility="collapsed",
        )
    )


def _sync_receipt_rows(st, purchase_module, selected_order: str, selected_lookup: dict[str, pd.Series]) -> list[dict]:
    rows = _receipt_rows_state(st, selected_order)
    selected_item_nos = set(selected_lookup)
    rows = [dict(row) for row in rows if str(row.get("품목번호", "")) in selected_item_nos]

    existing_item_nos = {str(row.get("품목번호", "")) for row in rows}
    for item_no, original in selected_lookup.items():
        if item_no not in existing_item_nos:
            rows.append({
                "행번호": _next_receipt_row_id(st, selected_order),
                "품목번호": int(item_no),
                "입고제품": str(original.get("제품명", "") or ""),
                "제품코드": "",
                "규격": str(original.get("규격", "") or ""),
                "입고수량": _to_int(purchase_module, original.get("남은수량", 0)),
                "매입단가": 0,
                "제조번호": "",
                "유통기한": "",
                "현재 가격 적용": True,
            })

    for row in rows:
        item_no = str(row.get("품목번호", ""))
        original = selected_lookup.get(item_no)
        if original is None:
            continue
        row["주문제품"] = str(original.get("제품명", "") or "")
        row["입고제품"] = str(row.get("입고제품", "") or original.get("제품명", "") or "")
        row["제품코드"] = str(row.get("제품코드", "") or "").strip()
        row["규격"] = str(row.get("규격", "") or original.get("규격", "") or "")
        row["복사/삭제"] = False
        row["입고수량"] = _to_int(purchase_module, row.get("입고수량", 0))
        row["매입단가"] = _to_int(purchase_module, row.get("매입단가", 0))
        row["제조번호"] = str(row.get("제조번호", "") or "")
        row["유통기한"] = str(row.get("유통기한", "") or "")
        row["현재 가격 적용"] = _normalise_bool(row.get("현재 가격 적용", True))

    st.session_state[f"statement_receipt_rows_{selected_order}"] = rows
    return rows


def _store_entered_rows(st, selected_order: str, entered: pd.DataFrame) -> list[dict]:
    rows = []
    if entered is not None and not entered.empty:
        for _, row in entered.iterrows():
            rows.append({
                "행번호": int(row.get("행번호", 0)),
                "품목번호": int(row.get("품목번호", 0)),
                "단위환산계수": conversion_factor(row),
                "입고단위": str(row.get("입고단위", "") or ""),
                "입고제품": str(row.get("입고제품", "") or "").strip(),
                "제품코드": str(row.get("제품코드", "") or "").strip(),
                "규격": str(row.get("규격", "") or "").strip(),
                "입고수량": int(float(row.get("입고수량", 0) or 0)),
                "매입단가": int(float(row.get("매입단가", 0) or 0)),
                "제조번호": str(row.get("제조번호", "") or "").strip(),
                "유통기한": str(row.get("유통기한", "") or "").strip(),
                "현재 가격 적용": _normalise_bool(row.get("현재 가격 적용", True)),
            })
    st.session_state[f"statement_receipt_rows_{selected_order}"] = rows
    return rows


def _normalize_expiry(value) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    digits = re.sub(r"\D", "", text)
    year = month = day = None
    if len(digits) == 8:
        year, month, day = int(digits[:4]), int(digits[4:6]), int(digits[6:8])
    elif len(digits) == 6:
        year, month, day = 2000 + int(digits[:2]), int(digits[2:4]), int(digits[4:6])
    else:
        parts = [part for part in re.split(r"[^0-9]+", text) if part]
        if len(parts) == 3:
            year = int(parts[0])
            year = 2000 + year if year < 100 else year
            month, day = int(parts[1]), int(parts[2])
    if year is None or month is None or day is None:
        raise ValueError(f"유통기한 형식을 확인하세요: {text}")
    try:
        return datetime(year, month, day).strftime("%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"유효하지 않은 유통기한입니다: {text}") from exc


def _render_unit_conversion(st, selected_order, selected_lookup):
    rows = _receipt_rows_state(st, selected_order)
    if not rows:
        return
    with st.expander("단위변환 · BOX → EA"):
        lookup = {int(row["행번호"]): row for row in rows}
        row_id = st.selectbox("변환할 입고행", list(lookup),
            format_func=lambda value: f"{value} · {lookup[value].get('입고제품', '')}",
            key=f"unit_row_{selected_order}")
        row = lookup[row_id]
        original = selected_lookup[str(int(row["품목번호"]))]
        source_unit = str(original.get("포장단위", "") or "발주단위")
        factor = conversion_factor(row)
        version = _receipt_row_version(st, selected_order)
        prefix = f"unit_{selected_order}_{row_id}_{version}"
        a, b, c = st.columns([1, 1, 1])
        quantity = a.number_input(f"변환할 수량 ({source_unit})", min_value=0.0,
            value=float(row.get("입고수량", 0)) / factor, step=1.0, key=prefix+"_qty")
        multiplier = b.number_input(f"1{source_unit}당 개수", min_value=1,
            value=factor if row.get("입고단위") else 100, step=1, key=prefix+"_factor")
        unit = c.text_input("입고단위", value=row.get("입고단위") or "EA", key=prefix+"_unit").strip()
        try:
            converted = convert_quantity(quantity, multiplier)
            st.caption(f"{quantity:g}{source_unit} × {multiplier} = {converted:,}{unit} · 매입단가는 1{unit} 기준으로 다시 입력하세요.")
            valid = bool(unit)
        except ValueError as exc:
            valid = False
            st.warning(str(exc))
        if st.button("단위변환 적용", disabled=not valid, key=prefix+"_apply"):
            row["입고수량"] = converted
            row["단위환산계수"] = int(multiplier)
            row["입고단위"] = unit
            row["매입단가"] = ""
            _bump_receipt_row_version(st, selected_order)
            st.rerun()
    for row in rows:
        if row.get("입고단위"):
            original = selected_lookup[str(int(row["품목번호"]))]
            st.caption(f"{row['행번호']}행 {row.get('입고제품', '')} · 1{original.get('포장단위', '')} = {conversion_factor(row)}{row['입고단위']} · 입고 {row['입고수량']:,}{row['입고단위']}")


def render(core_app, purchase_module, data) -> None:
    st = purchase_module.st
    orders = data["orders"].copy()
    order_items = data["order_items"].copy()
    products = data["products"].copy()
    statements, statement_items, price_history, _ = purchase_module.load_purchase_data()

    st.markdown("## 거래명세서 등록")
    st.caption("거래명세서에 적힌 품목을 선택한 뒤, 선택 품목의 입고정보를 아래 표에 입력하세요.")
    if orders.empty:
        st.info("등록된 발주서가 없습니다.")
        return

    open_orders = _open_orders(purchase_module, orders, order_items)
    if open_orders.empty:
        st.info("입고가 남아 있는 발주서가 없습니다.")
        return

    vendor_names = sorted(open_orders["거래처명"].astype(str).unique())
    vendor = st.selectbox("거래처", vendor_names, key="statement_register_vendor")
    vendor_orders = open_orders[open_orders["거래처명"].astype(str) == vendor].sort_values("발주일시")
    order_options = vendor_orders["발주ID"].astype(str).tolist()
    order_dates = {str(row["발주ID"]): str(row.get("발주일시", ""))[:10] for _, row in vendor_orders.iterrows()}
    selected_orders = st.multiselect(
        "연결할 발주서 (여러 개 선택 가능)", order_options,
        default=order_options[:1], format_func=lambda oid: f"{order_dates.get(oid, '')} · {oid}",
        key=f"statement_register_orders_{vendor}",
    )
    if not selected_orders:
        st.info("명세서에 연결할 발주서를 선택하세요.")
        return
    selected_order = "+".join(sorted(selected_orders))
    order_header = vendor_orders[vendor_orders["발주ID"].astype(str) == selected_orders[0]].iloc[0]
    order_rows = order_items[order_items["발주ID"].astype(str).isin(selected_orders)].copy()
    order_rows["_발주일자"] = order_rows["발주ID"].astype(str).map(order_dates)
    statement_number = max(_next_statement_number(statements, oid) for oid in selected_orders)
    with st.container(border=True):
        st.markdown("### 명세서 기본 정보")
        c1, c2, c3 = st.columns([1, 1, 2])
        c1.text_input("거래명세서 번호", value=str(statement_number), disabled=True)
        statement_date = c2.date_input("거래명세서 일자", value=datetime.now().date())
        memo = c3.text_area("메모", height=88)

    st.markdown("### 거래명세서에 적힌 품목 선택")
    selection_source = _selection_rows(
        purchase_module, order_rows, statements, statement_items, selected_order
    )
    if selection_source.empty:
        st.info("이 발주서에는 입고가 남은 품목이 없습니다.")
        return

    selection_editor = statement_item_selection.render(selection_source, selected_order)
    selected_items = selection_editor[selection_editor["선택"] == True].copy()  # noqa: E712
    selected_lookup = {str(int(row["품목번호"])): row for _, row in selected_items.iterrows()}

    st.markdown("### 선택 품목 입고정보 입력")
    st.caption(
        "입고제품은 기본적으로 주문제품과 같은 이름으로 채워집니다. 실제로 다른 제품이 들어왔다면 "
        "입고제품과 규격을 직접 수정하세요. 같은 제품이 제조번호·유통기한별로 나뉘어 들어오면 "
        "해당 행을 체크한 뒤 '선택 행 복사'를 누르세요."
    )

    receipt_rows = _sync_receipt_rows(st, purchase_module, selected_order, selected_lookup)
    if not receipt_rows:
        st.info("위 표에서 거래명세서에 적힌 품목을 선택하세요.")
        entered = pd.DataFrame()
    else:
        products_name_lookup = _product_name_lookup(products)
        editor_rows = []
        for row in receipt_rows:
            order_name = str(row.get("주문제품", "") or "")
            received_name = str(row.get("입고제품", "") or "") or order_name
            editor_rows.append({
                "복사/삭제": False,
                "행번호": int(row.get("행번호", 0)),
                "품목번호": int(row.get("품목번호", 0)),
                "단위환산계수": conversion_factor(row),
                "입고단위": str(row.get("입고단위", "") or ""),
                "입고발주ID": str(selected_lookup[str(int(row.get("품목번호", 0)))].get("입고발주ID", "")),
                "주문제품": order_name,
                "입고제품": received_name,
                "제품코드": str(row.get("제품코드", "") or ""),
                "제품코드_힌트": _display_product_code(order_name, received_name, products_name_lookup),
                "규격": str(row.get("규격", "") or ""),
                "입고수량": _to_int(purchase_module, row.get("입고수량", 0)),
                "매입단가": _to_int(purchase_module, row.get("매입단가", 0)),
                "제조번호": str(row.get("제조번호", "") or ""),
                "유통기한": str(row.get("유통기한", "") or ""),
                "현재 가격 적용": _normalise_bool(row.get("현재 가격 적용", True)),
            })
        entered = st.data_editor(
            pd.DataFrame(editor_rows), use_container_width=True, hide_index=True,
            disabled=["행번호", "품목번호", "주문제품", "입고발주ID"],
            column_config={
                "복사/삭제": st.column_config.CheckboxColumn("복사/삭제", width="small"),
                "행번호": None,
                "품목번호": None,
                "단위환산계수": None,
                "입고단위": st.column_config.TextColumn("입고단위", disabled=True),
                "주문제품": st.column_config.TextColumn("주문제품", width="medium"),
                "입고제품": st.column_config.TextColumn("입고제품", width="medium"),
                "제품코드": st.column_config.TextColumn(
                    "제품코드", width="small", help="같은 이름의 제품이 여러 개일 때만 직접 입력하세요."
                ),
                "제품코드_힌트": None,
                "규격": st.column_config.TextColumn("규격", width="small"),
                "입고수량": st.column_config.NumberColumn("입고수량", min_value=0, step=1, width="small"),
                "매입단가": st.column_config.NumberColumn("매입단가", min_value=0, step=100, width="small"),
                "제조번호": st.column_config.TextColumn("제조번호", width="small"),
                "유통기한": st.column_config.TextColumn("유통기한", width="small"),
                "현재 가격 적용": st.column_config.CheckboxColumn("현재 가격 적용", width="small"),
            },
            key=f"statement_receipt_input_{selected_order}_{_receipt_row_version(st, selected_order)}",
        )
        _store_entered_rows(st, selected_order, entered)

    _render_unit_conversion(st, selected_order, selected_lookup)

    split_col, delete_col, spacer_col, freight_col = st.columns([1.1, 1.1, 2.6, 1.5])
    selected_receipt_rows = entered[entered.get("복사/삭제", False) == True].copy() if not entered.empty else pd.DataFrame()  # noqa: E712

    if split_col.button("선택 행 복사", use_container_width=True, disabled=entered.empty, key=f"copy_receipt_row_{selected_order}"):
        if selected_receipt_rows.empty:
            st.warning("복사할 입고행을 체크하세요.")
        else:
            stored_rows = _store_entered_rows(st, selected_order, entered)
            selected_row_ids = {int(row.get("행번호", 0)) for _, row in selected_receipt_rows.iterrows()}
            for row in list(stored_rows):
                if int(row.get("행번호", 0)) not in selected_row_ids:
                    continue
                copied = dict(row)
                copied["행번호"] = _next_receipt_row_id(st, selected_order)
                copied["입고수량"] = 0
                copied["제조번호"] = ""
                copied["유통기한"] = ""
                stored_rows.append(copied)
            st.session_state[f"statement_receipt_rows_{selected_order}"] = stored_rows
            _bump_receipt_row_version(st, selected_order)
            st.rerun()

    if delete_col.button("선택 행 삭제", use_container_width=True, disabled=entered.empty, key=f"delete_receipt_row_{selected_order}"):
        if selected_receipt_rows.empty:
            st.warning("삭제할 입고행을 체크하세요.")
        else:
            stored_rows = _store_entered_rows(st, selected_order, entered)
            selected_row_ids = {int(row.get("행번호", 0)) for _, row in selected_receipt_rows.iterrows()}
            item_counts: dict[str, int] = {}
            for row in stored_rows:
                item_no = str(row.get("품목번호", ""))
                item_counts[item_no] = item_counts.get(item_no, 0) + 1
            next_rows = []
            blocked = False
            for row in stored_rows:
                row_id = int(row.get("행번호", 0))
                item_no = str(row.get("품목번호", ""))
                if row_id in selected_row_ids:
                    if item_counts.get(item_no, 0) <= 1:
                        blocked = True
                        next_rows.append(row)
                    else:
                        item_counts[item_no] -= 1
                else:
                    next_rows.append(row)
            st.session_state[f"statement_receipt_rows_{selected_order}"] = next_rows
            _bump_receipt_row_version(st, selected_order)
            if blocked:
                st.warning("품목별 최소 1개 입고행은 남겨야 합니다.")
            st.rerun()

    freight = _freight_input(st, freight_col, selected_order)
    freight_checked = freight_col.checkbox("운송비 무료", value=False, key=f"statement_freight_checked_{selected_order}")

    preview_rows = []
    expiry_errors = []
    quantity_by_item: dict[str, int] = {}
    remaining_by_item = {
        item_no: _to_int(purchase_module, original.get("남은수량", 0))
        for item_no, original in selected_lookup.items()
    }
    for _, row in entered.iterrows():
        item_no = str(int(row["품목번호"]))
        original = selected_lookup.get(item_no)
        if original is None:
            continue
        quantity = _to_int(purchase_module, row.get("입고수량", 0))
        if quantity <= 0:
            continue
        quantity_by_item[item_no] = quantity_by_item.get(item_no, 0) + order_quantity(row)

        order_product_name = str(original.get("제품명", "") or "").strip()
        order_product_code = str(original.get("제품코드", "") or "").strip()
        received_name = str(row.get("입고제품", "") or "").strip() or order_product_name
        received_spec = str(row.get("규격", "") or "").strip()
        typed_code = str(row.get("제품코드", "") or "").strip()
        is_substituted = received_name != order_product_name or (
            bool(typed_code) and typed_code != order_product_code
        )

        try:
            expiry = _normalize_expiry(row.get("유통기한", ""))
        except ValueError as exc:
            expiry_errors.append(str(exc))
            expiry = ""
        price = _to_int(purchase_module, row.get("매입단가", 0))
        preview_rows.append({
            "입고발주ID": str(original.get("입고발주ID", "")),
            "단위환산계수": conversion_factor(row),
            "입고단위": str(row.get("입고단위", "") or ""),
            "제품코드": typed_code,
            "정식제품명": received_name,
            "규격": received_spec,
            "단위": str(original.get("포장단위", "") or ""),
            "발주수량": _to_int(purchase_module, original.get("발주수량", 0)),
            "입고수량": quantity,
            "매입단가": price,
            "상품금액": quantity * price,
            "출고단가": purchase_module.calc_sell_price(price),
            "가격적용여부": "Y" if bool(row.get("현재 가격 적용", True)) else "N",
            "원발주제품코드": str(original.get("제품코드", "") or ""),
            "원발주제품명": order_product_name,
            "원발주규격": str(original.get("규격", "") or ""),
            "원발주단위": str(original.get("포장단위", "") or ""),
            "입고유형": "대체입고" if is_substituted else "정상입고",
            "대체사유": "",
            "제조번호": str(row.get("제조번호", "") or "").strip(),
            "유통기한": expiry,
        })

    quantity_notices = []
    for item_no, total_quantity in quantity_by_item.items():
        remaining = remaining_by_item.get(item_no, 0)
        if total_quantity > remaining:
            product_name = str(selected_lookup.get(item_no, {}).get("제품명", ""))
            quantity_notices.append(
                f"{product_name}의 입고수량 합계가 발주 남은수량을 초과했습니다 "
                f"(남은수량 {remaining:,}개 / 입력수량 {total_quantity:,}개). "
                "발주단위와 입고단위가 달라 발생할 수 있으며 저장은 계속 진행됩니다."
            )

    preview = pd.DataFrame(preview_rows)
    product_total = int(preview["상품금액"].sum()) if not preview.empty else 0
    a, b, c = st.columns(3)
    a.metric("상품 매입금액", f"{product_total:,}원")
    b.metric("운송비", f"{int(freight):,}원")
    c.metric("총 매입금액", f"{product_total + int(freight):,}원")

    if quantity_notices:
        st.info("\n".join(dict.fromkeys(quantity_notices)))

    if st.button("거래명세서 저장", type="primary", use_container_width=True):
        if expiry_errors:
            st.warning("\n".join(dict.fromkeys(expiry_errors)))
            return
        if preview.empty:
            st.warning("입고할 품목을 선택하고 입고수량을 입력하세요.")
            return
        if (preview["매입단가"] <= 0).any():
            st.warning("입고 품목의 매입단가를 입력하세요.")
            return

        working_products = catalog._normalize_products(products)
        name_lookup = _product_name_lookup(working_products)
        code_lookup = _product_code_lookup(working_products)
        products_changed = False
        alias_rows = []
        resolved_rows = []
        code_errors = []
        for row in preview.to_dict("records"):
            if row["입고유형"] != "대체입고":
                # 주문제품과 같은 이름이면 원발주 품목의 제품코드를 그대로 쓴다 —
                # 이름만으로 다시 찾으면 동명이품목이 있을 때 다른 코드를 고를 수 있다.
                row["제품코드"] = row["원발주제품코드"]
                if not str(row["규격"]).strip():
                    row["규격"] = row["원발주규격"]
                row["단위"] = row["원발주단위"]
                resolved_rows.append(row)
                continue

            received_name = str(row["정식제품명"]).strip()
            received_spec = str(row["규격"]).strip()
            typed_code = str(row.get("제품코드", "") or "").strip()

            if typed_code:
                # 같은 이름의 제품이 여러 개라서 직접 코드를 지정한 경우 — 이름 검색보다 우선한다.
                match = code_lookup.get(typed_code)
                if match is None:
                    code_errors.append(f"제품코드 '{typed_code}'를 제품 관리에서 찾을 수 없습니다 ({received_name}).")
                    continue
                row["제품코드"] = typed_code
                row["정식제품명"] = match["제품명"]
                if not received_spec:
                    row["규격"] = match["규격"]
                row["단위"] = match["포장단위"]
                resolved_rows.append(row)
                alias_rows.append({
                    "거래처명": order_header["거래처명"],
                    "별칭": row["원발주제품명"],
                    "제품코드": typed_code,
                })
                continue

            match = name_lookup.get(received_name)
            if match is None:
                new_code = catalog._next_auto_product_code(working_products["제품코드"].astype(str).tolist())
                new_row = pd.DataFrame([{
                    "전용거래처": catalog.COMMON_SCOPE,
                    "제품코드": new_code,
                    "제품명": received_name,
                    "규격": received_spec,
                    "포장단위": row["원발주단위"],
                }])
                working_products = pd.concat([working_products, new_row], ignore_index=True)
                match = {"제품코드": new_code, "규격": received_spec, "포장단위": row["원발주단위"]}
                name_lookup[received_name] = match
                code_lookup[new_code] = {"제품명": received_name, "규격": received_spec, "포장단위": row["원발주단위"]}
                products_changed = True
            row["제품코드"] = match["제품코드"]
            if not received_spec:
                row["규격"] = match["규격"]
            row["단위"] = match["포장단위"]
            resolved_rows.append(row)
            alias_rows.append({
                "거래처명": order_header["거래처명"],
                "별칭": row["원발주제품명"],
                "제품코드": match["제품코드"],
            })

        if code_errors:
            st.warning("\n".join(dict.fromkeys(code_errors)))
            return

        for row in resolved_rows:
            if row.get("입고단위"):
                row["단위"] = row["입고단위"]
        preview = pd.DataFrame(resolved_rows)
        validate_links(selected_orders, orders, order_header["거래처명"], preview)
        if products_changed:
            core_app.save_products(catalog._normalize_products(working_products))
        if alias_rows:
            combined_aliases = catalog._normalize_aliases(
                pd.concat([data["aliases"], pd.DataFrame(alias_rows)], ignore_index=True)
            )
            core_app.save_aliases(combined_aliases)

        sid = purchase_module.make_id("ST", statements["명세서ID"].tolist())
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        new_statement = pd.DataFrame([{
            "명세서ID": sid, "발주ID": selected_orders[0], "연결발주ID": encode_order_ids(selected_orders), "거래처명": order_header["거래처명"],
            "명세서번호": str(statement_number), "명세서일자": statement_date.strftime("%Y-%m-%d"),
            "운송비": int(freight), "운송비입력여부": "Y" if freight_checked or int(freight) > 0 else "N",
            "메모": memo.strip(), "등록일시": now, "수정일시": now,
        }])
        item_rows = []
        price_rows = []
        existing_price_ids = price_history["가격ID"].tolist()
        for index, row in preview.reset_index(drop=True).iterrows():
            item_rows.append({"명세서ID": sid, "순번": index + 1, **row.to_dict()})
            if str(row.get("가격적용여부", "")) == "Y":
                price_id = purchase_module.make_id("PR", existing_price_ids + [item.get("가격ID", "") for item in price_rows])
                price_rows.append({
                    "가격ID": price_id, "명세서ID": sid,
                    "명세서일자": statement_date.strftime("%Y-%m-%d"),
                    "제품코드": row["제품코드"], "정식제품명": row["정식제품명"],
                    "매입단가": _to_int(purchase_module, row["매입단가"]),
                    "출고단가": _to_int(purchase_module, row["출고단가"]), "등록일시": now,
                })
        save_statement_bundle(
            purchase_module,
            pd.concat([statements, new_statement], ignore_index=True),
            pd.concat([statement_items, pd.DataFrame(item_rows)], ignore_index=True),
            pd.concat([price_history, pd.DataFrame(price_rows)], ignore_index=True) if price_rows else price_history,
        )
        for key in [
            f"statement_receipt_rows_{selected_order}",
            f"statement_receipt_rows_version_{selected_order}",
            f"statement_receipt_next_row_id_{selected_order}",
        ]:
            st.session_state.pop(key, None)
        st.success(f"{statement_number}번 거래명세서를 저장했습니다: {sid}")
        st.rerun()
