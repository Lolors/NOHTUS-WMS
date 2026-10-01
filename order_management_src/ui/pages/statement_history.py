"""반품 처리를 포함한 거래명세서 내역 화면."""
from __future__ import annotations

from datetime import datetime
import html
import re
import streamlit as st
import streamlit.components.v2 as components

import pandas as pd
from services.receipt_units import conversion_factor

from services.statement_links import linked_order_ids, validate_links, reassign_receipt_source
from services.statement_returns import return_info as _return_info, return_marker as _return_marker, return_values, quantity_value
from ui.month_grid import render_month_grid
from ui.pages import catalog, purchase_enhancements, purchases
from ui.pages.statement_register_substitution import (
    _product_code_lookup,
    _product_name_lookup,
)
from ui.style_utils import map_cells


def _to_int(purchase_module, value) -> int:
    return purchase_module.to_int(value)


def _item_key(row) -> tuple:
    return purchase_enhancements._item_key(row)


def _return_editor(order_rows, linked_items, purchase_module) -> pd.DataFrame:
    rows = []
    for _, item in linked_items.iterrows():
        _, returned_quantity, _ = _return_info(item.get("가격적용여부", ""))
        received = _to_int(purchase_module, item.get("입고수량", 0))
        rows.append({
            "반품": False,
            "명세서ID": str(item.get("명세서ID", "")),
            "순번": _to_int(purchase_module, item.get("순번", 0)),
            "정식제품명": str(item.get("정식제품명", "") or ""),
            "제조번호": str(item.get("제조번호", "") or ""),
            "유통기한": str(item.get("유통기한", "") or ""),
            "총 입고수량": received + returned_quantity,
            "현재 입고수량": received,
            "반품처리수량": returned_quantity,
            "반품수량": returned_quantity,
        })
    return pd.DataFrame(rows)


def _process_returns(purchase_module, linked_statement_ids, statement_items, selected_rows) -> int:
    selected = selected_rows[selected_rows["반품"] == True]  # noqa: E712
    if selected.empty:
        raise ValueError("반품 수량을 변경할 품목을 체크하세요.")
    updated = statement_items.copy()
    changed = 0
    seen = set()
    for _, selection in selected.iterrows():
        sid = str(selection.get("명세서ID", ""))
        sequence = quantity_value(selection.get("순번", 0), "품목 순번")
        key = (sid, sequence)
        if key in seen or sid not in linked_statement_ids:
            raise ValueError("선택한 입고 내역을 확인할 수 없습니다. 새로고침 후 다시 선택하세요.")
        seen.add(key)
        mask = (updated["명세서ID"].astype(str) == sid) & (updated["순번"].apply(lambda v: _to_int(purchase_module, v)) == sequence)
        if int(mask.sum()) != 1:
            raise ValueError("선택한 입고 내역을 한 건으로 확인할 수 없습니다.")
        index = updated.index[mask][0]
        row = updated.loc[index]
        _, old_return, old_amount = _return_info(row.get("가격적용여부", ""))
        quantity = _to_int(purchase_module, row.get("입고수량", 0)) + old_return
        amount = _to_int(purchase_module, row.get("상품금액", 0)) + old_amount
        requested = quantity_value(selection.get("반품수량"))
        net_qty, net_amount, marker = return_values(quantity, amount, requested)
        if requested == old_return:
            continue
        updated.at[index, "입고수량"] = net_qty
        updated.at[index, "상품금액"] = net_amount
        updated.at[index, "가격적용여부"] = marker
        changed += 1
    if not changed:
        raise ValueError("변경할 반품수량을 입력하세요. 반품 취소는 0을 입력하세요.")
    purchase_module.save_table(purchase_module.STATEMENT_ITEMS_FILE, updated, purchase_module.STATEMENT_ITEM_COLUMNS)
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
        quantity = _to_int(purchase_module, row.get("입고수량", 0))
        amount = _to_int(purchase_module, row.get("상품금액", 0))
        purchase_price = _to_int(purchase_module, row.get("매입단가", 0))
        sale_price = _to_int(purchase_module, row.get("출고단가", 0)) or int(round(purchase_price * 1.3))
        display_rows.append({
            "정식제품명": str(row.get("정식제품명", "")),
            "규격": str(row.get("규격", "")),
            "수량": quantity,
            "포장단위": str(row.get("포장단위", "") or row.get("단위", "")),
            "매입단가": f"{purchase_price:,}원",
            "매입총액": f"{amount:,}원",
            "매출단가": f"{sale_price:,}원",
            "상태": ("부분반품" if quantity else "반품") if returned else "입고",
        })

    display = pd.DataFrame(display_rows, columns=[
        "상태", "정식제품명", "규격", "수량", "포장단위",
        "매입단가", "매입총액", "매출단가",
    ])
    display.insert(0, "No.", range(1, len(display) + 1))

    def style_status(value):
        if str(value) in {"반품", "부분반품"}:
            return "background-color: #fee2e2; color: #991b1b; font-weight: 700;"
        return ""

    styler = display.style.set_properties(
        subset=["매출단가"],
        **{"background-color": "#f3f4f6", "color": "#4b5563"},
    )
    return map_cells(styler, style_status, subset=["상태"])


def _statement_display_html(items: pd.DataFrame, purchase_module) -> str:
    display = _statement_display_table(items, purchase_module).data
    originals = items.fillna("").reset_index(drop=True)
    headers = ''.join(f'<th>{html.escape(str(column))}</th>' for column in display.columns)
    body = []
    for position, (_, row) in enumerate(display.iterrows()):
        cells = []
        for column, value in row.items():
            text = html.escape(str(value))
            attrs = ''
            if column in {"제품명", "정식제품명"}:
                original_name = str(originals.iloc[position].get("원발주제품명", "") or "").strip()
                if original_name and original_name != str(value).strip():
                    attrs = f' title="{html.escape("발주제품명: " + original_name, quote=True)}" class="statement-received-product"'
            elif column == "상태" and str(value) in {"반품", "부분반품"}:
                attrs = ' class="statement-return-status"'
            elif column == "매출단가":
                attrs = ' class="statement-sale-price"'
            cells.append(f'<td{attrs}>{text}</td>')
        body.append('<tr>' + ''.join(cells) + '</tr>')
    return (
        '<style>'
        '.statement-detail-wrap {width:100%;overflow-x:auto;}'
        '.statement-detail-table {width:100%;border-collapse:collapse;font-size:14px;}'
        '.statement-detail-table th,.statement-detail-table td {padding:9px 10px;border-bottom:1px solid #e5e7eb;text-align:left;}'
        '.statement-detail-table th {background:#f8fafc;white-space:nowrap;}'
        '.statement-received-product {cursor:help;}'
        '.statement-return-status {background:#fee2e2;color:#991b1b;font-weight:700;}'
        '.statement-sale-price {background:#f3f4f6;color:#4b5563;}'
        '</style><div class="statement-detail-wrap"><table class="statement-detail-table">'
        f'<thead><tr>{headers}</tr></thead><tbody>{"".join(body)}</tbody></table></div>'
    )


def _returned_amount(items: pd.DataFrame) -> int:
    total = 0
    for _, row in items.iterrows():
        returned, _, amount = _return_info(row.get("가격적용여부", ""))
        if returned:
            total += amount
    return total


def _render_statement_edit(
    core_app,
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
    aliases: pd.DataFrame,
    order_id: str,
    order_rows: pd.DataFrame,
    orders=None,
    all_order_items=None,
) -> None:
    """거래명세서 내역 수정 화면. 거래명세서 등록 화면과 같은 주문제품/입고제품
    입력과 선택 행 복사/삭제 기능을 제공한다."""
    parsed_date = pd.to_datetime(statement.get("명세서일자", ""), errors="coerce")
    initial_date = today if pd.isna(parsed_date) else parsed_date.date()

    rows_key = f"stmt_edit_rows_{statement_id}"
    row_seq_key = f"stmt_edit_row_seq_{statement_id}"
    version_key = f"stmt_edit_version_{statement_id}"
    session_keys = (rows_key, row_seq_key, version_key)

    if rows_key not in st.session_state:
        init_rows = []
        next_id = 1
        for _, row in items.reset_index(drop=True).iterrows():
            _, returned_qty, returned_amount = _return_info(row.get("가격적용여부", ""))
            gross_qty = _to_int(purchase_module, row.get("입고수량", 0)) + returned_qty
            has_original = any(str(row.get(field, "") or "").strip() for field in ("원발주제품코드", "원발주제품명", "원발주규격", "원발주단위"))
            init_rows.append({
                "행번호": next_id,
                "입고발주ID": str(row.get("입고발주ID", "") or statement.get("발주ID", "")),
                "_original_order_id": str(row.get("입고발주ID", "") or statement.get("발주ID", "")),
                "제품코드": str(row.get("제품코드", "") or ""),
                "정식제품명": str(row.get("정식제품명", "") or ""),
                "규격": str(row.get("규격", "") or ""),
                "단위": str(row.get("단위", "") or ""),
                "발주수량": _to_int(purchase_module, row.get("발주수량", 0)),
                "입고수량": gross_qty,
                "반품수량": returned_qty,
                "단위환산계수": conversion_factor(row),
                "_original_quantity": gross_qty,
                "_original_amount": _to_int(purchase_module, row.get("상품금액", 0)) + returned_amount,
                "_original_price": _to_int(purchase_module, row.get("매입단가", 0)),
                "매입단가": _to_int(purchase_module, row.get("매입단가", 0)),
                "제조번호": str(row.get("제조번호", "") or ""),
                "유통기한": str(row.get("유통기한", "") or ""),
                "원발주제품코드": str(row.get("원발주제품코드", "") or (row.get("제품코드", "") if not has_original else "") or ""),
                "원발주제품명": str(row.get("원발주제품명", "") or (row.get("정식제품명", "") if not has_original else "") or ""),
                "원발주규격": str(row.get("원발주규격", "") or (row.get("규격", "") if not has_original else "") or ""),
                "원발주단위": str(row.get("원발주단위", "") or (row.get("단위", "") if not has_original else "") or ""),
                "입고유형": str(row.get("입고유형", "") or ""),
                "대체사유": str(row.get("대체사유", "") or ""),
            })
            next_id += 1
        st.session_state[rows_key] = init_rows
        st.session_state[row_seq_key] = next_id
        st.session_state.setdefault(version_key, 0)

    st.markdown("#### 거래명세서 수정")
    f1, f2, f3, f4 = st.columns([0.7, 1.2, 1.2, 4.9], gap="small")
    edited_number = f1.text_input(
        "명세서 번호", value=str(statement.get("명세서번호", "")), key=f"stmt_edit_number_{statement_id}"
    )
    edited_date = f2.date_input("명세서 일자", value=initial_date, format="YYYY/MM/DD", key=f"stmt_edit_date_{statement_id}")
    edited_freight = f3.number_input(
        "배송비",
        min_value=0,
        step=100,
        value=_to_int(purchase_module, statement.get("운송비", 0)),
        key=f"stmt_edit_freight_{statement_id}",
    )
    edited_memo = f4.text_input(
        "메모", value=str(statement.get("메모", "") or ""), key=f"stmt_edit_memo_{statement_id}"
    )

    current_links = linked_order_ids(statement)
    if orders is None:
        eligible_orders = pd.DataFrame([{"발주ID": oid, "거래처명": statement.get("거래처명", ""), "발주일시": ""} for oid in current_links])
    else:
        eligible_orders = orders[orders["거래처명"].astype(str) == str(statement.get("거래처명", ""))].copy()
    order_labels = {str(row["발주ID"]): f"{purchases._date_text(row.get('발주일시', ''))} · {row['발주ID']}" for _, row in eligible_orders.iterrows()}
    with st.expander("연결 발주서 / 품목 배분", expanded=len(current_links) > 1):
        edited_links = st.multiselect(
            "연결할 발주서", list(order_labels), default=[oid for oid in current_links if oid in order_labels],
            format_func=lambda oid: order_labels.get(oid, oid), key=f"stmt_edit_links_{statement_id}",
        )
        st.caption("아래 품목의 입고 발주를 지정하세요. 같은 품목을 여러 발주에 나눌 때는 행을 복사한 뒤 각 행의 수량과 발주를 지정하세요. 배송비는 명세서에 한 번만 적용됩니다.")

    st.markdown("##### 품목 수정")
    st.caption("총 입고수량은 반품 전 수량입니다. 반품은 아래 반품 내역 영역에서 관리하세요.")

    current_rows = st.session_state[rows_key]
    for row in current_rows:
        if conversion_factor(row) != 1:
            st.caption(f"{row['정식제품명']}: 1{row.get('원발주단위', '')} = {conversion_factor(row)}{row.get('단위', '')} · 수량과 매입단가는 {row.get('단위', '')} 기준")

    editor_rows = [
        {
            "복사/삭제": False,
            "행번호": row["행번호"],
            "입고발주ID": row.get("입고발주ID", order_id),
            "주문제품": str(row.get("원발주제품명", "") or row["정식제품명"]),
            "입고제품": row["정식제품명"],
            "제품코드": str(row.get("제품코드", "") or ""),
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
        disabled=["행번호", "주문제품", "발주수량"],
        column_config={
            "복사/삭제": st.column_config.CheckboxColumn("복사/삭제", width="small"),
            "행번호": None,
            "입고발주ID": st.column_config.SelectboxColumn("입고 발주", options=list(order_labels), required=True, width="medium"),
            "주문제품": st.column_config.TextColumn("주문제품", width="medium"),
            "입고제품": st.column_config.TextColumn("입고제품", width="medium"),
            "제품코드": st.column_config.TextColumn(
                "제품코드", width="small", help="같은 이름의 제품이 여러 개일 때만 직접 입력하세요."
            ),
            "규격": st.column_config.TextColumn("규격", width="small"),
            "발주수량": st.column_config.NumberColumn("발주수량", width="small"),
            "입고수량": st.column_config.NumberColumn("총 입고수량", min_value=0, step=1, width="small", help="반품 전 수량입니다."),
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
        order_product_name = str(target.get("원발주제품명", "") or target["정식제품명"])
        order_product_code = str(target.get("원발주제품코드", "") or "")
        received_name = str(erow.get("입고제품", "") or "").strip() or order_product_name
        typed_code = str(erow.get("제품코드", "") or "").strip()
        target["입고발주ID"] = str(erow.get("입고발주ID", "") or "")
        target["정식제품명"] = received_name
        target["제품코드"] = typed_code
        target["규격"] = str(erow.get("규격", "") or "")
        target["입고수량"] = erow.get("입고수량", 0)
        target["매입단가"] = _to_int(purchase_module, erow.get("매입단가", 0))
        target["제조번호"] = str(erow.get("제조번호", "") or "")
        target["유통기한"] = str(erow.get("유통기한", "") or "")
        target["입고유형"] = (
            "대체입고"
            if received_name != order_product_name or (typed_code and typed_code != order_product_code)
            else "정상입고"
        )
        if not target.get("원발주제품명"):
            target["원발주제품코드"] = target.get("원발주제품코드", "") or ""
            target["원발주제품명"] = order_product_name
            target["원발주규격"] = target.get("원발주규격", "")
            target["원발주단위"] = target.get("원발주단위", "")
    st.session_state[rows_key] = current_rows

    selected_ids = {
        int(erow.get("행번호"))
        for _, erow in edited.iterrows()
        if bool(erow.get("복사/삭제", False))
    }

    copy_col, delete_col, save_col, cancel_col = st.columns([1, 1, 1.3, 0.7], gap="small")

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
                    copied["반품수량"] = 0
                    for field in ("_original_quantity", "_original_amount", "_original_price"):
                        copied.pop(field, None)
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
        elif any(row["행번호"] in selected_ids and row.get("반품수량", 0) > 0 for row in current_rows):
            st.warning("반품이 있는 품목은 아래 반품 내역에서 반품을 취소한 뒤 삭제하세요.")
        else:
            rows = [row for row in st.session_state[rows_key] if row["행번호"] not in selected_ids]
            if not rows:
                st.warning("거래명세서에는 품목이 한 개 이상 있어야 합니다.")
            else:
                st.session_state[rows_key] = rows
                st.session_state[version_key] += 1
                st.rerun()

    if save_col.button(
        "수정 내용 저장", type="primary", use_container_width=True, key=f"stmt_edit_save_{statement_id}"
    ):
        try:
            working_products = catalog._normalize_products(products)
            name_lookup = _product_name_lookup(working_products)
            code_lookup = _product_code_lookup(working_products)
            products_changed = False
            alias_rows = []
            resolved_rows = []
            code_errors = []
            vendor_name = str(statement.get("거래처명", "") or "")
            for row in st.session_state[rows_key]:
                row = reassign_receipt_source(row, all_order_items) if all_order_items is not None else dict(row)
                row["_converted_unit"] = row.get("단위", "") if conversion_factor(row) != 1 else ""
                order_product_name = str(row.get("원발주제품명", "") or row["정식제품명"]).strip()
                received_name = str(row.get("정식제품명", "") or "").strip() or order_product_name
                if row.get("입고유형") != "대체입고":
                    row["제품코드"] = row.get("원발주제품코드", "")
                    if not str(row.get("규격", "")).strip():
                        row["규격"] = row.get("원발주규격", "")
                    row["단위"] = row.get("단위", "") or row.get("원발주단위", "")
                    resolved_rows.append(row)
                    continue

                received_spec = str(row.get("규격", "") or "").strip()
                typed_code = str(row.get("제품코드", "") or "").strip()

                if typed_code:
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
                        "거래처명": vendor_name,
                        "별칭": order_product_name,
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
                        "포장단위": row.get("원발주단위", "") or row.get("단위", ""),
                    }])
                    working_products = pd.concat([working_products, new_row], ignore_index=True)
                    match = {"제품코드": new_code, "규격": received_spec, "포장단위": row.get("원발주단위", "") or row.get("단위", "")}
                    name_lookup[received_name] = match
                    code_lookup[new_code] = {"제품명": received_name, "규격": received_spec, "포장단위": row.get("원발주단위", "") or row.get("단위", "")}
                    products_changed = True
                row["제품코드"] = match["제품코드"]
                if not received_spec:
                    row["규격"] = match["규격"]
                row["단위"] = match["포장단위"]
                resolved_rows.append(row)
                alias_rows.append({
                    "거래처명": vendor_name,
                    "별칭": order_product_name,
                    "제품코드": match["제품코드"],
                })

            if code_errors:
                st.warning("\n".join(dict.fromkeys(code_errors)))
                return

            for row in resolved_rows:
                if row.get("_converted_unit"):
                    row["단위"] = row["_converted_unit"]
            validate_links(edited_links, eligible_orders, statement.get("거래처명", ""), pd.DataFrame(resolved_rows))
            for row in resolved_rows:
                return_values(row.get("입고수량", 0), 0, row.get("반품수량", 0))

            if products_changed:
                core_app.save_products(catalog._normalize_products(working_products))
            if alias_rows:
                combined_aliases = catalog._normalize_aliases(
                    pd.concat([aliases, pd.DataFrame(alias_rows)], ignore_index=True)
                )
                core_app.save_aliases(combined_aliases)

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
                pd.DataFrame(resolved_rows),
                linked_orders=edited_links,
            )
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.session_state.pop(f"stmt_edit_links_{statement_id}", None)
            for key in session_keys:
                st.session_state.pop(key, None)
            st.session_state.pop("editing_statement_id", None)
            st.success(f"{statement_no}번 거래명세서를 수정했습니다.")
            st.rerun()
    if cancel_col.button("취소", use_container_width=True, key=f"stmt_edit_cancel_{statement_id}"):
        st.session_state.pop(f"stmt_edit_links_{statement_id}", None)
        for key in session_keys:
            st.session_state.pop(key, None)
        st.session_state.pop("editing_statement_id", None)
        st.rerun()


def _render_statement_returns(st, purchase_module, statement_id, items, statement_items):
    st.markdown("##### 반품 내역")
    returned_rows = []
    for _, row in items.iterrows():
        _, returned_qty, returned_amount = _return_info(row.get("가격적용여부", ""))
        if returned_qty <= 0:
            continue
        returned_rows.append({
            "제품명": str(row.get("정식제품명", "") or ""),
            "규격": str(row.get("규격", "") or ""),
            "제조번호": str(row.get("제조번호", "") or ""),
            "유통기한": str(row.get("유통기한", "") or ""),
            "반품수량": returned_qty,
            "반품금액": f"{returned_amount:,}원",
        })
    if returned_rows:
        st.dataframe(pd.DataFrame(returned_rows), hide_index=True, use_container_width=True)
    else:
        st.caption("반품 내역이 없습니다.")
    if returned_rows:
        try:
            from nohtus.auth import can_access_page
            from nohtus.pages.customer_returns import open_statement_return
        except ModuleNotFoundError as exc:
            if exc.name != "nohtus":
                raise
        else:
            if can_access_page("반품 입고"):
                st.button("WMS 반품 입고", key=f"wms_customer_return_{statement_id}",
                          on_click=open_statement_return, args=(str(statement_id),),
                          help="실물 도착 후 입고 사업장을 선택해 반품 입고합니다. 매입금액은 변경하지 않습니다.")
    if items.empty:
        return
    if st.session_state.get("editing_statement_id") == statement_id:
        st.caption("명세서 수정을 저장하거나 취소하면 반품을 추가·수정할 수 있습니다.")
        return
    with st.expander("반품 추가 / 수정"):
        st.caption("변경할 행을 선택하고 최종 반품수량을 입력하세요. 0을 입력하면 반품이 취소됩니다.")
        version_key = f"statement_return_version_{statement_id}"
        rows = _return_editor(None, items, purchase_module)
        selected = st.data_editor(
            rows, hide_index=True, use_container_width=True,
            key=f"statement_return_editor_{statement_id}_{st.session_state.get(version_key, 0)}",
            disabled=[col for col in rows.columns if col not in {"반품", "반품수량"}],
            column_config={
                "반품": st.column_config.CheckboxColumn("선택"),
                "명세서ID": None, "순번": None,
                "정식제품명": st.column_config.TextColumn("제품명", width="large"),
                "반품수량": st.column_config.NumberColumn("반품수량", min_value=0, step=1, required=True),
            },
        )
        if st.button("반품 변경 저장", type="primary", key=f"statement_return_save_{statement_id}"):
            try:
                _process_returns(purchase_module, [statement_id], statement_items, selected)
            except ValueError as exc:
                st.error(str(exc))
            else:
                st.session_state[version_key] = st.session_state.get(version_key, 0) + 1
                st.session_state.pop(f"stmt_edit_rows_{statement_id}", None)
                st.session_state.pop(f"stmt_edit_row_seq_{statement_id}", None)
                st.session_state[f"stmt_edit_version_{statement_id}"] = st.session_state.get(f"stmt_edit_version_{statement_id}", 0) + 1
                st.rerun()


def _render_order_detail(
    core_app,
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
    aliases: pd.DataFrame,
    orders=None,
) -> None:
    order_id = str(order.get("발주ID", ""))
    vendor_name = str(order.get("거래처명", ""))
    order_date = purchases._date_text(order.get("발주일시", ""))
    linked_statements = matched_statements[
        matched_statements.apply(lambda row: order_id in linked_order_ids(row), axis=1)
    ].copy().sort_values(["명세서일자", "등록일시"])
    linked_ids = linked_statements["명세서ID"].astype(str).tolist()
    all_items = statement_items[
        statement_items["명세서ID"].astype(str).isin(linked_ids)
    ].copy()
    order_rows = order_items[order_items["발주ID"].astype(str) == order_id].copy()

    if any(len(linked_order_ids(row)) > 1 for _, row in linked_statements.iterrows()):
        st.markdown(f"## [{vendor_name}] 합산 거래명세서")
    else:
        st.markdown(f"## [{vendor_name}] 발주 {order_date} · {order_id}")

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
        '<div class="statement-summary-title">연결된 거래명세서</div>',
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
        links = linked_order_ids(statement)
        if len(links) > 1:
            st.caption("연결 발주서: " + " · ".join(links))
        st.markdown(
            f"### {seq}번 거래명세서 · 번호 {statement_no} · {statement_date}"
        )
        items = statement_items[
            statement_items["명세서ID"].astype(str) == statement_id
        ].copy()
        statement_returned = _returned_amount(items)
        if items.empty:
            st.info("이 거래명세서에는 저장된 품목이 없습니다.")
            received_qty = item_amount = 0
        else:
            visible_items = items.loc[
                items.apply(lambda row: _to_int(purchase_module, row.get("입고수량", 0)) > 0
                            or not _return_info(row.get("가격적용여부", ""))[0], axis=1)
            ]
            if visible_items.empty:
                st.caption("모든 품목이 반품되었습니다. 아래 반품 내역에서 확인하세요.")
            else:
                st.markdown(_statement_display_html(visible_items, purchase_module), unsafe_allow_html=True)
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
                st.session_state.pop("statement_history_selected_id", None)
                st.success(f"{statement_no}번 거래명세서를 삭제했습니다.")
                st.rerun()
        if st.session_state.get("editing_statement_id") == statement_id:
            _render_statement_edit(
                core_app, purchase_module, st, today, statement, statement_id, statement_no, items,
                statements, statement_items, price_history, products, aliases, order_id, order_rows, orders=orders, all_order_items=order_items,
            )

        _render_statement_returns(st, purchase_module, statement_id, items, statement_items)

        if seq < len(linked_statements):
            st.markdown("---")



@st.cache_resource
def _get_statement_list_component():
    return components.component(
        "statement_history_badge_list",
        html='<div class="statement-list-root"></div>',
        css="""
        .statement-list-root { height:320px; overflow:auto; border:1px solid #e2e8f0; border-radius:8px; }
        table { width:100%; table-layout:fixed; border-collapse:collapse; font-size:13px; color:#1e293b; }
        th { position:sticky; top:0; background:#f8fafc; font-weight:700; z-index:1; }
        th,td { padding:10px 5px; text-align:left; border-bottom:1px solid #e2e8f0; }
        th,.number { white-space:nowrap; }
        .date { font-size:12px; overflow-wrap:anywhere; }
        tr[data-id] { cursor:pointer; }
        tr[data-id]:hover { background:#f1f5f9; }
        tr.selected { background:#eff6ff; box-shadow:inset 3px 0 #2563eb; }
        tr:focus-visible { outline:2px solid #2563eb; outline-offset:-2px; }
        .product-count { display:inline-block; border-radius:999px; background:#ecfccb; color:#365314; border:1px solid #d9f99d; padding:3px 8px; font-weight:750; font-size:12px; white-space:nowrap; margin-right:7px; }
        .vendor { overflow-wrap:anywhere; }
        .products { line-height:1.7; overflow-wrap:anywhere; }
        """,
        js="""
        export default function(component) {
            const root = component.parentElement.querySelector('.statement-list-root');
            root.innerHTML = component.data;
            const select = (event) => {
                if (event.type === 'keydown' && !['Enter', ' '].includes(event.key)) return;
                const row = event.target.closest('tr[data-id]');
                if (!row || !root.contains(row)) return;
                if (event.type === 'keydown') event.preventDefault();
                component.setTriggerValue('selected', row.dataset.id);
            };
            root.addEventListener('click', select);
            root.addEventListener('keydown', select);
            return () => {
                root.removeEventListener('click', select);
                root.removeEventListener('keydown', select);
            };
        }
        """,
    )


def _statement_list_html(list_rows, selected_id=None):
    rows = []
    for row in list_rows:
        sid = str(row["_명세서ID"])
        summary = str(row["포함된 제품"])
        match = re.fullmatch(r"\[(\d+)품목\] (.*)", summary, flags=re.DOTALL)
        count, names = match.groups() if match else ("0", summary)
        cells = ''.join(
            f'<td class="{kind}">{html.escape(str(row[column]))}</td>'
            for column, kind in [("발주일자", "date"), ("명세서일자", "date"), ("거래처", "vendor"), ("번호", "number")]
        )
        cells += f'<td class="products"><span class="product-count">{count}품목</span>{html.escape(names)}</td>'
        selected = sid == selected_id
        rows.append(f'<tr data-id="{html.escape(sid, quote=True)}" tabindex="0" role="button" aria-pressed="{str(selected).lower()}" class="{"selected" if selected else ""}">{cells}</tr>')
    return '<table><colgroup><col style="width:102px"><col style="width:102px"><col style="width:18%"><col style="width:46px"><col></colgroup><thead><tr><th>발주일자</th><th>명세서 일자</th><th>거래처</th><th>번호</th><th>포함된 제품</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table>'


def _statement_product_summaries(statement_items: pd.DataFrame) -> dict[str, str]:
    if statement_items.empty:
        return {}
    rows = statement_items.copy().fillna("")
    rows["명세서ID"] = rows["명세서ID"].astype(str)
    if "순번" in rows.columns:
        rows = rows.assign(_sequence=pd.to_numeric(rows["순번"], errors="coerce")).sort_values("_sequence", kind="stable")
    summaries = {}
    for statement_id, items in rows.groupby("명세서ID", sort=False):
        names = list(dict.fromkeys(name for name in items["정식제품명"].astype(str).str.strip() if name))
        summary = names[0] if names else ""
        if len(names) > 1:
            summary += f" 그 외 {len(names) - 1}품목"
        summaries[statement_id] = f"[{len(names)}품목] {summary or '-'}"
    return summaries


def render(core_app, purchase_module, data) -> None:
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

    order_dates = {
        str(row.get("발주ID", "")): purchases._date_text(row.get("발주일시", ""))
        for _, row in orders.iterrows()
    }
    product_summaries = _statement_product_summaries(statement_items)
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
        matched["_latest_order_date"] = matched.apply(
            lambda row: max(
                (order_dates.get(oid, "") for oid in linked_order_ids(row)), default=""
            ), axis=1,
        ) if not matched.empty else pd.Series(dtype=str)
        matched = matched.sort_values(
            ["_latest_order_date", "명세서일자", "등록일시"], ascending=False, kind="stable"
        )
        panel_result["matched"] = matched

        st.caption(f"등록된 거래명세서 {len(matched):,}건")
        if matched.empty:
            st.info("검색 조건에 맞는 거래명세서가 없습니다.")
            return

        list_rows = []
        for _, row in matched.iterrows():
            list_rows.append({
                "발주일자": ", ".join(sorted(set(order_dates.get(oid, "-") for oid in linked_order_ids(row)), reverse=True)),
                "명세서일자": purchases._date_text(row.get("명세서일자", "")),
                "거래처": str(row.get("거래처명", "")),
                "번호": str(row.get("명세서번호", "")) or "-",
                "포함된 제품": product_summaries.get(str(row.get("명세서ID", "")), "[0품목] -"),
                "_명세서ID": str(row.get("명세서ID", "")),
            })
        selected_key = "statement_history_selected_id"
        visible_ids = {row["_명세서ID"] for row in list_rows}
        selected_id = st.session_state.get(selected_key)
        if selected_id not in visible_ids:
            st.session_state.pop(selected_key, None)
            selected_id = None
        event = _get_statement_list_component()(
            data=_statement_list_html(list_rows, selected_id),
            key="statement_history_badge_list", on_selected_change=lambda: None,
        )
        if event.selected in visible_ids and event.selected != selected_id:
            st.session_state[selected_key] = event.selected
            st.rerun()
        panel_result["selected_id"] = selected_id

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
        core_app,
        purchase_module,
        st,
        today,
        order_rows_match.iloc[0],
        selected_rows,
        statement_items,
        order_items,
        statements,
        price_history,
        products,
        aliases,
        orders=orders,
    )
