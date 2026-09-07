"""단계별 품목 선택·입력과 검색형 대체입고를 지원하는 거래명세서 등록 화면."""
from __future__ import annotations

import html
import re
from datetime import datetime

import pandas as pd


def _to_int(purchase_module, value) -> int:
    return purchase_module.to_int(value)


def item_key(row) -> tuple:
    """입고수량을 원발주품목 기준으로 묶는 안정적인 식별키를 반환합니다.

    대체입고 행에는 실제 입고제품과 원발주제품 정보가 함께 저장됩니다.
    원발주제품코드가 비어 있더라도 원발주제품명/규격/단위가 있으면 실제
    대체제품 코드보다 원발주 텍스트 조합을 우선해야 발주 품목 입고로
    정상 집계됩니다.
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
    linked_ids = statements.loc[
        statements["발주ID"].astype(str) == str(order_id), "명세서ID"
    ].astype(str).tolist()
    received: dict[tuple, int] = {}
    if not linked_ids:
        return received
    related = statement_items[statement_items["명세서ID"].astype(str).isin(linked_ids)]
    for _, row in related.iterrows():
        key = item_key(row)
        received[key] = received.get(key, 0) + _to_int(purchase_module, row.get("입고수량", 0))
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


def _next_statement_number(statements: pd.DataFrame, order_id: str) -> int:
    linked = statements[statements["발주ID"].astype(str) == str(order_id)]
    numbers = []
    for value in linked.get("명세서번호", pd.Series(dtype=str)).tolist():
        try:
            numbers.append(int(float(str(value or "").strip())))
        except (TypeError, ValueError):
            continue
    return max(numbers) + 1 if numbers else 1


def _selection_rows(purchase_module, order_rows, statements, statement_items, selected_order):
    received = _received_by_order(purchase_module, statements, statement_items, selected_order)
    rows = []
    for source_index, (_, row) in enumerate(order_rows.reset_index(drop=True).iterrows()):
        ordered_qty = _to_int(purchase_module, row.get("수량", 0))
        received_qty = received.get(item_key(row), 0)
        remaining = max(0, ordered_qty - received_qty)
        if remaining <= 0:
            continue
        rows.append({
            "선택": False,
            "품목번호": source_index,
            "제품코드": str(row.get("제품코드", "") or ""),
            "제품명": str(row.get("정식제품명", row.get("제품명", "")) or ""),
            "규격": str(row.get("규격", "") or ""),
            "포장단위": str(row.get("단위", row.get("포장단위", "")) or ""),
            "발주수량": ordered_qty,
            "누적입고": received_qty,
            "남은수량": remaining,
        })
    return pd.DataFrame(rows)


def _substitution_state(st, selected_order: str) -> dict[str, dict]:
    key = f"statement_substitution_state_{selected_order}"
    state = st.session_state.get(key)
    if not isinstance(state, dict):
        state = {}
        st.session_state[key] = state
    return state


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


def _actual_for_item(original, substitution: dict | None) -> dict:
    if substitution:
        return substitution.get("제품", {})
    return {
        "제품코드": str(original.get("제품코드", "") or ""),
        "정식제품명": str(original.get("제품명", "") or ""),
        "규격": str(original.get("규격", "") or ""),
        "단위": str(original.get("포장단위", "") or ""),
    }


def _sync_receipt_rows(st, purchase_module, selected_order: str, selected_lookup: dict[str, pd.Series], substitution_state: dict[str, dict]) -> list[dict]:
    rows = _receipt_rows_state(st, selected_order)
    selected_item_nos = set(selected_lookup)
    rows = [dict(row) for row in rows if str(row.get("품목번호", "")) in selected_item_nos]

    existing_item_nos = {str(row.get("품목번호", "")) for row in rows}
    for item_no, original in selected_lookup.items():
        if item_no not in existing_item_nos:
            rows.append({
                "행번호": _next_receipt_row_id(st, selected_order),
                "품목번호": int(item_no),
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
        actual = _actual_for_item(original, substitution_state.get(item_no))
        row["제품명"] = str(actual.get("정식제품명", "") or original.get("제품명", ""))
        row["규격"] = str(actual.get("규격", "") or original.get("규격", ""))
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


def _render_substitution_badges(st, substitution_state: dict[str, dict], selected_lookup: dict[str, pd.Series]) -> None:
    rows = []
    for item_no, substitution in substitution_state.items():
        original = selected_lookup.get(str(item_no))
        if original is None:
            continue
        actual = substitution.get("제품", {})
        original_name = html.escape(str(original.get("제품명", "") or ""))
        actual_name = html.escape(str(actual.get("정식제품명", "") or ""))
        rows.append(
            '<div style="display:flex;align-items:center;gap:8px;margin:5px 0;">'
            '<span style="display:inline-flex;align-items:center;padding:3px 10px;'
            'border-radius:999px;background:#dcfce7;color:#15803d;font-size:12px;'
            'font-weight:700;line-height:1.4;white-space:nowrap;">대체품</span>'
            f'<span style="font-size:14px;"><b>{actual_name}</b> '
            f'<span style="color:#6b7280;">(원발주: {original_name})</span></span></div>'
        )
    if rows:
        st.markdown(
            '<div style="padding:8px 12px;border:1px solid #dcfce7;border-radius:10px;'
            'background:#f0fdf4;margin:4px 0 10px 0;">' + "".join(rows) + "</div>",
            unsafe_allow_html=True,
        )


def render(purchase_module, data) -> None:
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

    vendor_map = open_orders.set_index("발주ID")["거래처명"].astype(str).to_dict()
    order_options = open_orders.sort_values("발주일시", ascending=False)["발주ID"].astype(str).tolist()
    selected_order = st.selectbox(
        "연결할 발주서", order_options,
        format_func=lambda oid: f'[{vendor_map.get(oid, "")}] {oid}',
        key="statement_register_order",
    )
    order_header = open_orders[open_orders["발주ID"].astype(str) == selected_order].iloc[0]
    order_rows = order_items[order_items["발주ID"].astype(str) == selected_order].copy()

    product_labels, product_lookup = _catalog(products)
    if not product_labels:
        st.warning("제품 관리에 등록된 제품이 없어 대체제품을 선택할 수 없습니다.")
        return

    statement_number = _next_statement_number(statements, selected_order)
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

    selection_editor = st.data_editor(
        selection_source, use_container_width=True, hide_index=True,
        disabled=["품목번호", "제품코드", "제품명", "규격", "포장단위", "발주수량", "누적입고", "남은수량"],
        column_config={
            "선택": st.column_config.CheckboxColumn("선택", width="small"),
            "품목번호": None,
            "제품코드": st.column_config.TextColumn("제품코드", width="small"),
            "제품명": st.column_config.TextColumn("제품명", width="large"),
            "규격": st.column_config.TextColumn("규격", width="small"),
            "포장단위": st.column_config.TextColumn("포장단위", width="small"),
            "발주수량": st.column_config.NumberColumn("발주수량", width="small"),
            "누적입고": st.column_config.NumberColumn("누적입고", width="small"),
            "남은수량": st.column_config.NumberColumn("남은수량", width="small"),
        },
        key=f"statement_item_selection_{selected_order}",
    )
    selected_items = selection_editor[selection_editor["선택"] == True].copy()  # noqa: E712
    selected_lookup = {str(int(row["품목번호"])): row for _, row in selected_items.iterrows()}

    substitution_state = _substitution_state(st, selected_order)
    substitution_state = {key: value for key, value in substitution_state.items() if key in selected_lookup}
    st.session_state[f"statement_substitution_state_{selected_order}"] = substitution_state

    st.markdown("### 선택 품목 입고정보 입력")
    st.caption("같은 제품이 제조번호·유통기한별로 나뉘어 들어오면 해당 행을 체크한 뒤 '선택 행 복사'를 누르세요.")
    _render_substitution_badges(st, substitution_state, selected_lookup)

    receipt_rows = _sync_receipt_rows(st, purchase_module, selected_order, selected_lookup, substitution_state)
    if not receipt_rows:
        st.info("위 표에서 거래명세서에 적힌 품목을 선택하세요.")
        entered = pd.DataFrame()
    else:
        editor_rows = []
        for row in receipt_rows:
            editor_rows.append({
                "복사/삭제": False,
                "행번호": int(row.get("행번호", 0)),
                "품목번호": int(row.get("품목번호", 0)),
                "제품명": str(row.get("제품명", "") or ""),
                "규격": str(row.get("규격", "") or ""),
                "입고수량": _to_int(purchase_module, row.get("입고수량", 0)),
                "매입단가": _to_int(purchase_module, row.get("매입단가", 0)),
                "제조번호": str(row.get("제조번호", "") or ""),
                "유통기한": str(row.get("유통기한", "") or ""),
                "현재 가격 적용": _normalise_bool(row.get("현재 가격 적용", True)),
            })
        entered = st.data_editor(
            pd.DataFrame(editor_rows), use_container_width=True, hide_index=True,
            disabled=["행번호", "품목번호", "제품명", "규격"],
            column_config={
                "복사/삭제": st.column_config.CheckboxColumn("복사/삭제", width="small"),
                "행번호": None,
                "품목번호": None,
                "제품명": st.column_config.TextColumn("제품명", width="large"),
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

    split_col, delete_col, substitute_col, cancel_col, spacer_col, freight_col = st.columns([1.1, 1.1, 1.2, 1.4, 1.4, 1.5])
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

    if substitute_col.button("대체품 입고", use_container_width=True, disabled=selected_items.empty, key=f"open_substitution_{selected_order}"):
        st.session_state[f"show_substitution_form_{selected_order}"] = True
        st.session_state[f"show_substitution_cancel_{selected_order}"] = False

    if cancel_col.button("대체품 입고 취소", use_container_width=True, disabled=not bool(substitution_state), key=f"open_substitution_cancel_{selected_order}"):
        st.session_state[f"show_substitution_cancel_{selected_order}"] = True
        st.session_state[f"show_substitution_form_{selected_order}"] = False

    freight = _freight_input(st, freight_col, selected_order)
    freight_checked = freight_col.checkbox("운송비 무료", value=False, key=f"statement_freight_checked_{selected_order}")

    if st.session_state.get(f"show_substitution_form_{selected_order}", False):
        with st.container(border=True):
            st.markdown("#### 대체품 입고 설정")
            source_options = list(selected_lookup)
            source_item_no = st.selectbox(
                "어떤 품목을 대체하나요?", source_options,
                format_func=lambda item_no: str(selected_lookup[item_no].get("제품명", "")),
                key=f"substitution_source_{selected_order}",
            )
            keyword = st.text_input("대체제품 검색", placeholder="제품명 또는 제품코드 일부 입력", key=f"substitution_search_{selected_order}")
            normalized_keyword = str(keyword or "").strip().casefold()
            filtered_labels = [
                label for label in product_labels
                if not normalized_keyword
                or normalized_keyword in label.casefold()
                or normalized_keyword in str(product_lookup[label].get("규격", "")).casefold()
            ]
            replacement_label = None
            if not filtered_labels:
                st.warning("검색 결과가 없습니다.")
            else:
                replacement_label = st.selectbox("어떤 제품으로 대체하나요?", filtered_labels, key=f"substitution_target_{selected_order}")
            reason = st.text_input("대체사유", placeholder="예: 거래처 재고 부족으로 다른 브랜드 대체", key=f"substitution_reason_{selected_order}")
            confirm_col, close_col, _ = st.columns([1, 1, 3])
            if confirm_col.button("확인", type="primary", use_container_width=True):
                if replacement_label is None:
                    st.warning("대체제품을 선택하세요.")
                elif not str(reason or "").strip():
                    st.warning("대체사유를 입력하세요.")
                else:
                    substitution_state[str(source_item_no)] = {"제품": product_lookup[replacement_label], "대체사유": str(reason).strip()}
                    st.session_state[f"statement_substitution_state_{selected_order}"] = substitution_state
                    st.session_state[f"show_substitution_form_{selected_order}"] = False
                    _bump_receipt_row_version(st, selected_order)
                    st.rerun()
            if close_col.button("닫기", use_container_width=True):
                st.session_state[f"show_substitution_form_{selected_order}"] = False
                st.rerun()

    if st.session_state.get(f"show_substitution_cancel_{selected_order}", False):
        with st.container(border=True):
            st.markdown("#### 대체품 입고 취소")
            cancel_options = list(substitution_state)
            cancel_item_no = st.selectbox(
                "취소할 대체품을 선택하세요.", cancel_options,
                format_func=lambda item_no: (
                    f'{selected_lookup[item_no].get("제품명", "")} → '
                    f'{substitution_state[item_no].get("제품", {}).get("정식제품명", "")}'
                ),
                key=f"substitution_cancel_target_{selected_order}",
            )
            confirm_col, close_col, _ = st.columns([1, 1, 3])
            if confirm_col.button("취소 확인", type="primary", use_container_width=True):
                substitution_state.pop(str(cancel_item_no), None)
                st.session_state[f"statement_substitution_state_{selected_order}"] = substitution_state
                st.session_state[f"show_substitution_cancel_{selected_order}"] = False
                _bump_receipt_row_version(st, selected_order)
                st.rerun()
            if close_col.button("닫기", use_container_width=True, key=f"close_substitution_cancel_{selected_order}"):
                st.session_state[f"show_substitution_cancel_{selected_order}"] = False
                st.rerun()

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
        quantity_by_item[item_no] = quantity_by_item.get(item_no, 0) + quantity
        substitution = substitution_state.get(item_no)
        actual = _actual_for_item(original, substitution)
        try:
            expiry = _normalize_expiry(row.get("유통기한", ""))
        except ValueError as exc:
            expiry_errors.append(str(exc))
            expiry = ""
        price = _to_int(purchase_module, row.get("매입단가", 0))
        preview_rows.append({
            **actual,
            "발주수량": _to_int(purchase_module, original.get("발주수량", 0)),
            "입고수량": quantity,
            "매입단가": price,
            "상품금액": quantity * price,
            "출고단가": purchase_module.calc_sell_price(price),
            "가격적용여부": "Y" if bool(row.get("현재 가격 적용", True)) else "N",
            "원발주제품코드": str(original.get("제품코드", "") or ""),
            "원발주제품명": str(original.get("제품명", "") or ""),
            "원발주규격": str(original.get("규격", "") or ""),
            "원발주단위": str(original.get("포장단위", "") or ""),
            "입고유형": "대체입고" if substitution else "정상입고",
            "대체사유": str(substitution.get("대체사유", "") or "") if substitution else "",
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

        sid = purchase_module.make_id("ST", statements["명세서ID"].tolist())
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        new_statement = pd.DataFrame([{
            "명세서ID": sid, "발주ID": selected_order, "거래처명": order_header["거래처명"],
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
        purchase_module.save_table(
            purchase_module.STATEMENTS_FILE,
            pd.concat([statements, new_statement], ignore_index=True),
            purchase_module.STATEMENT_COLUMNS,
        )
        purchase_module.save_table(
            purchase_module.STATEMENT_ITEMS_FILE,
            pd.concat([statement_items, pd.DataFrame(item_rows)], ignore_index=True),
            purchase_module.STATEMENT_ITEM_COLUMNS,
        )
        if price_rows:
            purchase_module.save_table(
                purchase_module.PRICE_HISTORY_FILE,
                pd.concat([price_history, pd.DataFrame(price_rows)], ignore_index=True),
                purchase_module.PRICE_HISTORY_COLUMNS,
            )
        for key in [
            f"statement_substitution_state_{selected_order}",
            f"show_substitution_form_{selected_order}",
            f"show_substitution_cancel_{selected_order}",
            f"statement_receipt_rows_{selected_order}",
            f"statement_receipt_rows_version_{selected_order}",
            f"statement_receipt_next_row_id_{selected_order}",
        ]:
            st.session_state.pop(key, None)
        st.success(f"{statement_number}번 거래명세서를 저장했습니다: {sid}")
        st.rerun()
