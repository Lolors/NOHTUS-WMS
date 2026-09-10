"""반품 처리를 포함한 거래명세서 내역 화면."""
from __future__ import annotations

from datetime import datetime

import pandas as pd

from ui.month_grid import render_month_grid
from ui.pages import purchase_enhancements, purchases
from ui.pages.statement_register_substitution import _catalog
from ui.style_utils import map_cells


def _to_int(purchase_module, value) -> int:
    return purchase_module.to_int(value)


def _return_marker(quantity: int, amount: int) -> str:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"반품:{quantity}:{amount}:{stamp}"


def _return_info(value) -> tuple[bool, int, int]:
    text = str(value or "").strip()
    if not text.startswith("반품:"):
        return False, 0, 0
    parts = text.split(":", 3)
    if len(parts) < 3:
        return True, 0, 0
    try:
        quantity = int(float(parts[1] or 0))
    except (TypeError, ValueError):
        quantity = 0
    try:
        amount = int(float(parts[2] or 0))
    except (TypeError, ValueError):
        amount = 0
    return True, quantity, amount


def _item_key(row) -> tuple:
    return purchase_enhancements._item_key(row)


def _return_editor(order_rows, linked_items, purchase_module) -> pd.DataFrame:
    rows = []
    for _, order_row in order_rows.reset_index(drop=True).iterrows():
        key = _item_key(order_row)
        received_quantity = 0
        returned_quantity = 0
        for _, item in linked_items.iterrows():
            if _item_key(item) != key:
                continue
            returned, original_quantity, _ = _return_info(item.get("가격적용여부", ""))
            if returned:
                returned_quantity += original_quantity
            else:
                received_quantity += _to_int(purchase_module, item.get("입고수량", 0))
        rows.append({
            "반품": False,
            "제품코드": str(order_row.get("제품코드", "") or ""),
            "정식제품명": str(order_row.get("정식제품명", order_row.get("제품명", "")) or ""),
            "규격": str(order_row.get("규격", "") or ""),
            "포장단위": str(order_row.get("단위", order_row.get("포장단위", "")) or ""),
            "발주수량": _to_int(purchase_module, order_row.get("수량", 0)),
            "현재 입고수량": received_quantity,
            "반품처리수량": returned_quantity,
        })
    return pd.DataFrame(rows)


def _process_returns(
    purchase_module,
    linked_statement_ids: list[str],
    statement_items: pd.DataFrame,
    selected_rows: pd.DataFrame,
) -> int:
    selected_keys = {
        _item_key(row)
        for _, row in selected_rows.iterrows()
        if bool(row.get("반품", False))
    }
    if not selected_keys:
        raise ValueError("반품할 품목을 체크하세요.")

    updated = statement_items.copy()
    changed = 0
    for index, row in updated.iterrows():
        if str(row.get("명세서ID", "")) not in linked_statement_ids:
            continue
        if _item_key(row) not in selected_keys:
            continue
        already_returned, _, _ = _return_info(row.get("가격적용여부", ""))
        if already_returned:
            continue
        quantity = _to_int(purchase_module, row.get("입고수량", 0))
        amount = _to_int(purchase_module, row.get("상품금액", 0))
        if quantity <= 0 and amount <= 0:
            continue
        updated.at[index, "가격적용여부"] = _return_marker(quantity, amount)
        updated.at[index, "입고수량"] = 0
        updated.at[index, "상품금액"] = 0
        changed += 1

    if changed <= 0:
        raise ValueError("선택한 품목에 반품 처리할 입고 내역이 없습니다.")

    purchase_module.save_table(
        purchase_module.STATEMENT_ITEMS_FILE,
        updated,
        purchase_module.STATEMENT_ITEM_COLUMNS,
    )
    return changed


def _statement_display_table(items: pd.DataFrame, purchase_module):
    rows = items.copy().fillna("")
    for col in [
        "정식제품명", "규격", "입고수량", "단위", "포장단위",
        "매입단가", "출고단가", "상품금액", "가격적용여부",
    ]:
        if col not in rows.columns:
            rows[col] = ""

    display_rows = []
    for _, row in rows.iterrows():
        returned, original_quantity, original_amount = _return_info(row.get("가격적용여부", ""))
        quantity = original_quantity if returned else _to_int(purchase_module, row.get("입고수량", 0))
        amount = -original_amount if returned else _to_int(purchase_module, row.get("상품금액", 0))
        purchase_price = _to_int(purchase_module, row.get("매입단가", 0))
        sale_price = _to_int(purchase_module, row.get("출고단가", 0)) or int(round(purchase_price * 1.3))
        display_rows.append({
            "정식제품명": str(row.get("정식제품명", "")),
            "규격": str(row.get("규격", "")),
            "수량": quantity,
            "포장단위": str(row.get("포장단위", "") or row.get("단위", "")),
            "매입단가": f"{purchase_price:,}원",
            "상품금액": f"{amount:,}원",
            "매출단가": f"{sale_price:,}원",
            "상태": "반품" if returned else "입고",
        })

    display = pd.DataFrame(display_rows)
    display.insert(0, "No.", range(1, len(display) + 1))

    def style_status(value):
        if str(value) == "반품":
            return "background-color: #fee2e2; color: #991b1b; font-weight: 700;"
        return ""

    styler = display.style.set_properties(
        subset=["매출단가"],
        **{"background-color": "#f3f4f6", "color": "#4b5563"},
    )
    return map_cells(styler, style_status, subset=["상태"])


def _returned_amount(items: pd.DataFrame) -> int:
    total = 0
    for _, row in items.iterrows():
        returned, _, amount = _return_info(row.get("가격적용여부", ""))
        if returned:
            total += amount
    return total


def _render_statement_edit(
    purchase_module,
    st,
    today,
    statement,
    statement_id: str,
    statement_no: str,
    items: pd.DataFrame,
    statements: pd.DataFrame,
    statement_items: pd.DataFrame,
    price_history: pd.DataFrame,
    products: pd.DataFrame,
) -> None:
    """거래명세서 내역 수정 화면. 거래명세서 등록 화면과 같은 선택 행 복사/삭제,
    대체품 입고/취소 기능을 제공한다."""
    parsed_date = pd.to_datetime(statement.get("명세서일자", ""), errors="coerce")
    initial_date = today if pd.isna(parsed_date) else parsed_date.date()

    rows_key = f"stmt_edit_rows_{statement_id}"
    row_seq_key = f"stmt_edit_row_seq_{statement_id}"
    version_key = f"stmt_edit_version_{statement_id}"
    sub_form_key = f"stmt_edit_show_sub_form_{statement_id}"
    sub_cancel_key = f"stmt_edit_show_sub_cancel_{statement_id}"
    session_keys = (rows_key, row_seq_key, version_key, sub_form_key, sub_cancel_key)

    if rows_key not in st.session_state:
        init_rows = []
        next_id = 1
        for _, row in items.reset_index(drop=True).iterrows():
            init_rows.append({
                "행번호": next_id,
                "제품코드": str(row.get("제품코드", "") or ""),
                "정식제품명": str(row.get("정식제품명", "") or ""),
                "규격": str(row.get("규격", "") or ""),
                "단위": str(row.get("단위", "") or ""),
                "발주수량": _to_int(purchase_module, row.get("발주수량", 0)),
                "입고수량": _to_int(purchase_module, row.get("입고수량", 0)),
                "매입단가": _to_int(purchase_module, row.get("매입단가", 0)),
                "제조번호": str(row.get("제조번호", "") or ""),
                "유통기한": str(row.get("유통기한", "") or ""),
                "원발주제품코드": str(row.get("원발주제품코드", "") or ""),
                "원발주제품명": str(row.get("원발주제품명", "") or ""),
                "원발주규격": str(row.get("원발주규격", "") or ""),
                "원발주단위": str(row.get("원발주단위", "") or ""),
                "입고유형": str(row.get("입고유형", "") or ""),
                "대체사유": str(row.get("대체사유", "") or ""),
            })
            next_id += 1
        st.session_state[rows_key] = init_rows
        st.session_state[row_seq_key] = next_id
        st.session_state[version_key] = 0

    st.markdown("#### 거래명세서 수정")
    f1, f2, f3 = st.columns([2, 2, 2])
    edited_number = f1.text_input(
        "명세서 번호", value=str(statement.get("명세서번호", "")), key=f"stmt_edit_number_{statement_id}"
    )
    edited_date = f2.date_input("명세서 일자", value=initial_date, key=f"stmt_edit_date_{statement_id}")
    edited_freight = f3.number_input(
        "배송비",
        min_value=0,
        step=100,
        value=_to_int(purchase_module, statement.get("운송비", 0)),
        key=f"stmt_edit_freight_{statement_id}",
    )
    edited_memo = st.text_area(
        "메모", value=str(statement.get("메모", "") or ""), key=f"stmt_edit_memo_{statement_id}"
    )

    st.markdown("##### 품목 수정")
    st.caption("같은 제품이 제조번호·유통기한별로 나뉘어 들어오면 해당 행을 체크한 뒤 '선택 행 복사'를 누르세요.")

    current_rows = st.session_state[rows_key]
    substituted = [row for row in current_rows if row.get("입고유형") == "대체입고"]
    if substituted:
        badge_rows = "".join(
            '<div style="display:flex;align-items:center;gap:8px;margin:5px 0;">'
            '<span style="display:inline-flex;align-items:center;padding:3px 10px;'
            'border-radius:999px;background:#dcfce7;color:#15803d;font-size:12px;'
            'font-weight:700;line-height:1.4;white-space:nowrap;">대체품</span>'
            f'<span style="font-size:14px;"><b>{row["정식제품명"]}</b> '
            f'<span style="color:#6b7280;">(원발주: {row["원발주제품명"]})</span></span></div>'
            for row in substituted
        )
        st.markdown(
            '<div style="padding:8px 12px;border:1px solid #dcfce7;border-radius:10px;'
            'background:#f0fdf4;margin:4px 0 10px 0;">' + badge_rows + "</div>",
            unsafe_allow_html=True,
        )

    editor_rows = [
        {
            "복사/삭제": False,
            "행번호": row["행번호"],
            "정식제품명": row["정식제품명"],
            "규격": row["규격"],
            "발주수량": row["발주수량"],
            "입고수량": row["입고수량"],
            "매입단가": row["매입단가"],
            "제조번호": row["제조번호"],
            "유통기한": row["유통기한"],
        }
        for row in current_rows
    ]
    edited = st.data_editor(
        pd.DataFrame(editor_rows),
        use_container_width=True,
        hide_index=True,
        disabled=["행번호", "정식제품명", "규격", "발주수량"],
        column_config={
            "복사/삭제": st.column_config.CheckboxColumn("복사/삭제", width="small"),
            "행번호": None,
            "정식제품명": st.column_config.TextColumn("제품명", width="large"),
            "규격": st.column_config.TextColumn("규격", width="small"),
            "발주수량": st.column_config.NumberColumn("발주수량", width="small"),
            "입고수량": st.column_config.NumberColumn("입고수량", min_value=0, step=1, width="small"),
            "매입단가": st.column_config.NumberColumn("매입단가", min_value=0, step=100, width="small"),
            "제조번호": st.column_config.TextColumn("제조번호", width="small"),
            "유통기한": st.column_config.TextColumn(
                "유통기한", width="small", help="예: 2026-12-31, 20261231, 261231"
            ),
        },
        key=f"stmt_edit_items_{statement_id}_{st.session_state[version_key]}",
    )

    by_id = {row["행번호"]: row for row in current_rows}
    for _, erow in edited.iterrows():
        target = by_id.get(int(erow.get("행번호")))
        if target is None:
            continue
        target["입고수량"] = _to_int(purchase_module, erow.get("입고수량", 0))
        target["매입단가"] = _to_int(purchase_module, erow.get("매입단가", 0))
        target["제조번호"] = str(erow.get("제조번호", "") or "")
        target["유통기한"] = str(erow.get("유통기한", "") or "")
    st.session_state[rows_key] = current_rows

    selected_ids = {
        int(erow.get("행번호"))
        for _, erow in edited.iterrows()
        if bool(erow.get("복사/삭제", False))
    }

    copy_col, delete_col, sub_col, sub_cancel_col = st.columns(4)

    if copy_col.button(
        "선택 행 복사", use_container_width=True, disabled=edited.empty, key=f"stmt_edit_copy_{statement_id}"
    ):
        if not selected_ids:
            st.warning("복사할 품목을 체크하세요.")
        else:
            rows = st.session_state[rows_key]
            next_id = st.session_state[row_seq_key]
            new_rows = []
            for row in rows:
                new_rows.append(row)
                if row["행번호"] in selected_ids:
                    copied = dict(row)
                    copied["행번호"] = next_id
                    copied["입고수량"] = 0
                    copied["제조번호"] = ""
                    copied["유통기한"] = ""
                    new_rows.append(copied)
                    next_id += 1
            st.session_state[rows_key] = new_rows
            st.session_state[row_seq_key] = next_id
            st.session_state[version_key] += 1
            st.rerun()

    if delete_col.button(
        "선택 행 삭제", use_container_width=True, disabled=edited.empty, key=f"stmt_edit_delete_{statement_id}"
    ):
        if not selected_ids:
            st.warning("삭제할 품목을 체크하세요.")
        else:
            rows = [row for row in st.session_state[rows_key] if row["행번호"] not in selected_ids]
            if not rows:
                st.warning("거래명세서에는 품목이 한 개 이상 있어야 합니다.")
            else:
                st.session_state[rows_key] = rows
                st.session_state[version_key] += 1
                st.rerun()

    if sub_col.button(
        "대체품 입고",
        use_container_width=True,
        disabled=len(selected_ids) != 1,
        key=f"stmt_edit_sub_{statement_id}",
    ):
        st.session_state[sub_form_key] = True
        st.session_state[sub_cancel_key] = False

    if sub_cancel_col.button(
        "대체품 입고 취소",
        use_container_width=True,
        disabled=not substituted,
        key=f"stmt_edit_sub_cancel_{statement_id}",
    ):
        st.session_state[sub_cancel_key] = True
        st.session_state[sub_form_key] = False

    product_labels, product_lookup = _catalog(products)

    if st.session_state.get(sub_form_key, False):
        with st.container(border=True):
            st.markdown("###### 대체품 입고 설정")
            if len(selected_ids) != 1:
                st.warning("대체할 행을 하나만 체크한 뒤 다시 눌러주세요.")
            elif not product_labels:
                st.warning("제품 관리에 등록된 제품이 없어 대체제품을 선택할 수 없습니다.")
            else:
                target_id = next(iter(selected_ids))
                keyword = st.text_input(
                    "대체제품 검색",
                    placeholder="제품명 또는 제품코드 일부 입력",
                    key=f"stmt_edit_sub_search_{statement_id}",
                )
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
                    replacement_label = st.selectbox(
                        "어떤 제품으로 대체하나요?", filtered_labels, key=f"stmt_edit_sub_target_{statement_id}"
                    )
                reason = st.text_input(
                    "대체사유",
                    placeholder="예: 거래처 재고 부족으로 다른 브랜드 대체",
                    key=f"stmt_edit_sub_reason_{statement_id}",
                )
                confirm_col, close_col, _ = st.columns([1, 1, 3])
                if confirm_col.button(
                    "확인", type="primary", use_container_width=True, key=f"stmt_edit_sub_confirm_{statement_id}"
                ):
                    if replacement_label is None:
                        st.warning("대체제품을 선택하세요.")
                    elif not str(reason or "").strip():
                        st.warning("대체사유를 입력하세요.")
                    else:
                        rows = st.session_state[rows_key]
                        for row in rows:
                            if row["행번호"] == target_id:
                                replacement = product_lookup[replacement_label]
                                if row.get("입고유형") != "대체입고":
                                    row["원발주제품코드"] = row["제품코드"]
                                    row["원발주제품명"] = row["정식제품명"]
                                    row["원발주규격"] = row["규격"]
                                    row["원발주단위"] = row["단위"]
                                row["제품코드"] = str(replacement.get("제품코드", ""))
                                row["정식제품명"] = str(replacement.get("정식제품명", ""))
                                row["규격"] = str(replacement.get("규격", ""))
                                row["단위"] = str(replacement.get("단위", ""))
                                row["입고유형"] = "대체입고"
                                row["대체사유"] = str(reason).strip()
                                break
                        st.session_state[rows_key] = rows
                        st.session_state[sub_form_key] = False
                        st.session_state[version_key] += 1
                        st.rerun()
                if close_col.button("닫기", use_container_width=True, key=f"stmt_edit_sub_close_{statement_id}"):
                    st.session_state[sub_form_key] = False
                    st.rerun()

    if st.session_state.get(sub_cancel_key, False):
        with st.container(border=True):
            st.markdown("###### 대체품 입고 취소")
            if not substituted:
                st.info("취소할 대체품 입고 내역이 없습니다.")
            else:
                lookup = {row["행번호"]: row for row in substituted}
                cancel_id = st.selectbox(
                    "취소할 대체품을 선택하세요.",
                    list(lookup),
                    format_func=lambda rid: f'{lookup[rid]["원발주제품명"]} → {lookup[rid]["정식제품명"]}',
                    key=f"stmt_edit_sub_cancel_target_{statement_id}",
                )
                confirm_col, close_col, _ = st.columns([1, 1, 3])
                if confirm_col.button(
                    "취소 확인",
                    type="primary",
                    use_container_width=True,
                    key=f"stmt_edit_sub_cancel_confirm_{statement_id}",
                ):
                    rows = st.session_state[rows_key]
                    for row in rows:
                        if row["행번호"] == cancel_id:
                            row["제품코드"] = row["원발주제품코드"]
                            row["정식제품명"] = row["원발주제품명"]
                            row["규격"] = row["원발주규격"]
                            row["단위"] = row["원발주단위"]
                            row["원발주제품코드"] = ""
                            row["원발주제품명"] = ""
                            row["원발주규격"] = ""
                            row["원발주단위"] = ""
                            row["입고유형"] = ""
                            row["대체사유"] = ""
                            break
                    st.session_state[rows_key] = rows
                    st.session_state[sub_cancel_key] = False
                    st.session_state[version_key] += 1
                    st.rerun()
                if close_col.button(
                    "닫기", use_container_width=True, key=f"stmt_edit_sub_cancel_close_{statement_id}"
                ):
                    st.session_state[sub_cancel_key] = False
                    st.rerun()

    save_col, cancel_col = st.columns(2)
    if save_col.button(
        "수정 내용 저장", type="primary", use_container_width=True, key=f"stmt_edit_save_{statement_id}"
    ):
        try:
            purchase_enhancements._save_statement_edit(
                purchase_module,
                statement_id,
                statements,
                statement_items,
                price_history,
                edited_number,
                edited_date,
                int(edited_freight),
                edited_memo,
                pd.DataFrame(st.session_state[rows_key]),
            )
        except ValueError as exc:
            st.error(str(exc))
        else:
            for key in session_keys:
                st.session_state.pop(key, None)
            st.session_state.pop("editing_statement_id", None)
            st.success(f"{statement_no}번 거래명세서를 수정했습니다.")
            st.rerun()
    if cancel_col.button("취소", use_container_width=True, key=f"stmt_edit_cancel_{statement_id}"):
        for key in session_keys:
            st.session_state.pop(key, None)
        st.session_state.pop("editing_statement_id", None)
        st.rerun()


def _render_order_detail(
    purchase_module,
    st,
    today,
    order,
    matched_statements: pd.DataFrame,
    statement_items: pd.DataFrame,
    order_items: pd.DataFrame,
    statements: pd.DataFrame,
    price_history: pd.DataFrame,
    products: pd.DataFrame,
) -> None:
    order_id = str(order.get("발주ID", ""))
    vendor_name = str(order.get("거래처명", ""))
    order_date = purchases._date_text(order.get("발주일시", ""))
    linked_statements = matched_statements[
        matched_statements["발주ID"].astype(str) == order_id
    ].copy().sort_values(["명세서일자", "등록일시"])
    linked_ids = linked_statements["명세서ID"].astype(str).tolist()
    all_items = statement_items[
        statement_items["명세서ID"].astype(str).isin(linked_ids)
    ].copy()
    order_rows = order_items[order_items["발주ID"].astype(str) == order_id].copy()

    st.markdown(f"## [{vendor_name}] 발주 {order_date} · {order_id}")

    st.markdown(
        '<div class="statement-summary-title">1) 전체 발주 내용</div>',
        unsafe_allow_html=True,
    )
    if order_rows.empty:
        st.info("저장된 발주 품목이 없습니다.")
    else:
        return_editor = st.data_editor(
            _return_editor(order_rows, all_items, purchase_module),
            key=f"return_items_{order_id}",
            use_container_width=True,
            hide_index=True,
            disabled=[
                "제품코드", "정식제품명", "규격", "포장단위",
                "발주수량", "현재 입고수량", "반품처리수량",
            ],
            column_config={
                "반품": st.column_config.CheckboxColumn("반품 선택"),
                "정식제품명": st.column_config.TextColumn(width="large"),
            },
        )
        return_col, _ = st.columns([1, 3])
        if return_col.button(
            "선택 품목 반품",
            key=f"process_return_{order_id}",
            type="primary",
            use_container_width=True,
        ):
            try:
                changed = _process_returns(
                    purchase_module,
                    linked_ids,
                    statement_items,
                    return_editor,
                )
            except ValueError as exc:
                st.error(str(exc))
            else:
                st.success(f"선택 품목의 입고내역 {changed:,}건을 반품 처리했습니다.")
                st.rerun()

    current_product_amount = (
        all_items["상품금액"].apply(lambda value: _to_int(purchase_module, value)).sum()
        if not all_items.empty else 0
    )
    returned_amount = _returned_amount(all_items)
    freight_amount = linked_statements["운송비"].apply(
        lambda value: _to_int(purchase_module, value)
    ).sum()
    total_received = (
        all_items["입고수량"].apply(lambda value: _to_int(purchase_module, value)).sum()
        if not all_items.empty else 0
    )
    total_purchase = int(current_product_amount + freight_amount)

    st.markdown(
        '<div class="statement-summary-title">2) 연결된 거래명세서</div>',
        unsafe_allow_html=True,
    )
    m1, m2, m3, _ = st.columns([1, 1, 2, 2], gap="small")
    m1.metric("연결 거래명세서", f"{len(linked_statements):,}건")
    m2.metric("총 입고수량", f"{int(total_received):,}")
    m3.metric("총 매입금액", f"{total_purchase:,}원")
    if returned_amount:
        st.caption(f"반품 차감액 {returned_amount:,}원 반영됨")

    for seq, (_, statement) in enumerate(linked_statements.iterrows(), 1):
        statement_id = str(statement.get("명세서ID", ""))
        statement_no = str(statement.get("명세서번호", "")) or str(seq)
        statement_date = purchases._date_text(statement.get("명세서일자", ""))
        st.markdown(
            f"### {seq}번 거래명세서 · 번호 {statement_no} · {statement_date}"
        )
        items = statement_items[
            statement_items["명세서ID"].astype(str) == statement_id
        ].copy()
        statement_returned = _returned_amount(items)
        has_returns = statement_returned > 0
        if items.empty:
            st.info("이 거래명세서에는 저장된 품목이 없습니다.")
            received_qty = item_amount = 0
        else:
            st.dataframe(
                _statement_display_table(items, purchase_module),
                use_container_width=True,
                hide_index=True,
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
        detail_text = f"상품금액 {item_amount + statement_returned:,}원 + 배송비 {freight:,}원"
        if statement_returned:
            detail_text += f" - 반품 {statement_returned:,}원"
        t2.markdown(
            f'<div class="statement-total-detail">{detail_text}</div>',
            unsafe_allow_html=True,
        )

        edit_col, delete_col, confirm_col, _ = st.columns([1, 1, 1.2, 3], gap="small")
        with confirm_col:
            confirmed = st.checkbox(
                "삭제 확인", key=f"delete_statement_confirm_{statement_id}"
            )
        with edit_col:
            if st.button(
                "거래명세서 수정",
                key=f"edit_statement_{statement_id}",
                use_container_width=True,
                disabled=has_returns,
            ):
                st.session_state["editing_statement_id"] = statement_id
        with delete_col:
            if st.button(
                "거래명세서 삭제",
                key=f"delete_statement_{statement_id}",
                disabled=not confirmed,
                use_container_width=True,
            ):
                purchases._delete_statement(
                    purchase_module,
                    statement_id,
                    statements,
                    statement_items,
                    price_history,
                )
                st.session_state.pop("statement_history_list_select", None)
                st.success(f"{statement_no}번 거래명세서를 삭제했습니다.")
                st.rerun()
        if has_returns:
            st.caption("반품 내역이 있는 거래명세서는 반품 기록 보호를 위해 직접 수정할 수 없습니다.")

        if st.session_state.get("editing_statement_id") == statement_id and not has_returns:
            _render_statement_edit(purchase_module, st, today, statement, statement_id, statement_no, items, statements, statement_items, price_history, products)

        if seq < len(linked_statements):
            st.markdown("---")


def render(purchase_module, data) -> None:
    st = purchase_module.st
    statements, statement_items, price_history, _ = purchase_module.load_purchase_data()
    orders = data["orders"].copy()
    order_items = data["order_items"]
    aliases = data["aliases"]
    products = data["products"]

    st.markdown("## 거래명세서 내역")
    if statements.empty or orders.empty:
        st.info("등록된 거래명세서가 없습니다.")
        return

    st.markdown(
        """
<style>
[data-testid="stMain"] {
    overflow-y: scroll !important;
    scrollbar-gutter: stable !important;
}
.statement-summary-title { font-size: 21px; font-weight: 800; margin: 22px 0 8px 0; }
.statement-total-box { font-size: 23px; font-weight: 800; padding: 10px 0 2px 0; }
.statement-total-detail { font-size: 14px; color: #6b7280; margin: 0 0 16px 0; }
</style>
""",
        unsafe_allow_html=True,
    )

    orders["발주ID"] = orders["발주ID"].astype(str)
    statements = statements.copy()
    statements["발주ID"] = statements["발주ID"].astype(str)
    statements["_statement_date"] = pd.to_datetime(
        statements["명세서일자"], errors="coerce"
    ).dt.date
    today = datetime.now().date()

    vendor_options = ["전체"] + sorted(
        statements["거래처명"].astype(str).replace("", pd.NA).dropna().unique().tolist()
    )

    panel_result: dict = {}

    def _side_panel() -> None:
        c1, c2 = st.columns(2, gap="small")
        vendor = c1.selectbox("거래처별 검색", vendor_options, key="statement_history_vendor")
        keyword = c2.text_input(
            "제품명/별칭 검색",
            placeholder="정식제품명 또는 별칭 입력",
            key="statement_history_keyword",
        )

        year_val = st.session_state.get("statement_history_year", today.year)
        month_val = st.session_state.get("statement_history_month", today.month)

        matched = statements[
            (statements["_statement_date"].apply(lambda v: v.year if pd.notna(v) else None) == year_val)
            & (statements["_statement_date"].apply(lambda v: v.month if pd.notna(v) else None) == month_val)
        ].copy()
        if vendor != "전체":
            matched = matched[matched["거래처명"].astype(str) == vendor]
        keyword_text = str(keyword or "").strip()
        if keyword_text:
            matching_ids = purchase_enhancements._matching_order_ids_by_product(
                statement_items, aliases, keyword_text
            )
            matched = matched[matched["명세서ID"].astype(str).isin(matching_ids)]
        matched = matched.sort_values(["명세서일자", "등록일시"], ascending=False)
        panel_result["matched"] = matched

        st.caption(f"등록된 거래명세서 {len(matched):,}건")
        if matched.empty:
            st.info("검색 조건에 맞는 거래명세서가 없습니다.")
            return

        list_rows = []
        for _, row in matched.iterrows():
            list_rows.append({
                "거래처": str(row.get("거래처명", "")),
                "명세서일자": purchases._date_text(row.get("명세서일자", "")),
                "번호": str(row.get("명세서번호", "")) or "-",
                "발주ID": str(row.get("발주ID", "")),
                "_명세서ID": str(row.get("명세서ID", "")),
            })
        list_df = pd.DataFrame(list_rows)

        # 체크(선택)하면 다른 행은 자동으로 선택 해제되도록 데이터프레임 단일 행 선택을 사용한다.
        event = st.dataframe(
            list_df.drop(columns=["_명세서ID"]),
            hide_index=True,
            use_container_width=True,
            height=320,
            on_select="rerun",
            selection_mode="single-row",
            key="statement_history_list_select",
        )
        selected_positions = (
            list(event.selection.rows) if event and getattr(event, "selection", None) else []
        )
        panel_result["selected_id"] = (
            str(list_df.iloc[selected_positions[0]]["_명세서ID"]) if selected_positions else None
        )

    with st.container(border=True):
        render_month_grid(
            st,
            "statement_history",
            default_year=today.year,
            default_month=today.month,
            scale=0.25,
            year_font_scale=6,
            side_content=_side_panel,
        )

    matched_statements = panel_result.get("matched", pd.DataFrame())
    selected_id = panel_result.get("selected_id")
    if not selected_id or matched_statements.empty:
        return

    selected_rows = matched_statements[matched_statements["명세서ID"].astype(str) == selected_id]
    if selected_rows.empty:
        return

    order_id = str(selected_rows.iloc[0].get("발주ID", ""))
    order_rows_match = orders[orders["발주ID"] == order_id]
    if order_rows_match.empty:
        st.warning("연결된 발주서를 찾을 수 없습니다.")
        return

    st.markdown("---")
    _render_order_detail(
        purchase_module,
        st,
        today,
        order_rows_match.iloc[0],
        matched_statements,
        statement_items,
        order_items,
        statements,
        price_history,
        products,
    )
