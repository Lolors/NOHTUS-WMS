"""발주 관련 화면 구현.

기존 app_layers의 페이지 함수를 호출하지 않고, 현재 적용된 검색·출력·DB 저장
기능을 조합해 UI 계층에서 직접 화면을 구성합니다.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from ui.style_utils import map_cells


def _normalise_items(core_app, rows: pd.DataFrame) -> list[dict]:
    if rows is None or rows.empty:
        return []
    result = []
    for _, row in rows.iterrows():
        unit = str(row.get("단위", row.get("포장단위", "")) or "")
        result.append({
            "제품코드": str(row.get("제품코드", "") or ""),
            "정식제품명": str(row.get("정식제품명", row.get("제품명", "")) or ""),
            "검색별칭": str(row.get("검색별칭", "") or ""),
            "규격": str(row.get("규격", "") or ""),
            "단위": unit,
            "포장단위": unit,
            "수량": core_app.safe_int(row.get("수량", 0)),
        })
    return result


def _add_or_merge_item(items: list[dict], new_item: dict) -> list[dict]:
    code = str(new_item.get("제품코드", "") or "")
    name = str(new_item.get("정식제품명", "") or "")
    for item in items:
        same_code = code and str(item.get("제품코드", "")) == code
        same_name = not code and str(item.get("정식제품명", "")) == name
        if same_code or same_name:
            item["수량"] = int(item.get("수량", 0)) + int(new_item.get("수량", 0))
            return items
    items.append(new_item)
    return items


def _vendor_panel(st, vendor) -> None:
    st.markdown(
        f"""
<div class="vendor-card">
    <div class="vendor-name">{vendor.get('거래처명', '')}</div>
    <div class="info-row"><div class="info-label">담당자</div><div>{vendor.get('담당자', '')}</div></div>
    <div class="info-row"><div class="info-label">연락처</div><div>{vendor.get('연락처', '')}</div></div>
    <div class="info-row"><div class="info-label">주소</div><div>{vendor.get('배송지', '')}</div></div>
</div>
""",
        unsafe_allow_html=True,
    )


def write(core_app, data) -> None:
    st = core_app.st
    vendors = data["vendors"]
    products = data["products"]
    aliases = data["aliases"]
    drafts_df = data["drafts"]
    draft_items = data["draft_items"]
    orders_df = data["orders"]
    saved_items = data["order_items"]

    st.markdown("## 발주 작성")
    if vendors.empty:
        st.warning("먼저 거래처를 등록하세요.")
        return

    left, right = st.columns([1.12, 1], gap="medium")
    with left:
        vendor_names = vendors["거래처명"].astype(str).tolist()
        loaded_vendor = st.session_state.get("loaded_vendor_name", "")
        default_index = vendor_names.index(loaded_vendor) if loaded_vendor in vendor_names else 0
        vendor_name = st.selectbox("거래처", vendor_names, index=default_index, key="order_vendor")
        vendor = vendors[vendors["거래처명"].astype(str) == vendor_name].iloc[0]
        _vendor_panel(st, vendor)

        latest = orders_df[orders_df["거래처명"].astype(str) == vendor_name].copy()
        if not latest.empty:
            latest = latest.sort_values("발주일시", ascending=False).iloc[0]
            if st.button("최근 발주 복사", use_container_width=True):
                rows = saved_items[saved_items["발주ID"].astype(str) == str(latest["발주ID"])]
                st.session_state.order_items = _normalise_items(core_app, rows)
                st.rerun()

        with st.container(border=True):
            st.markdown("### 제품 검색")
            keyword = st.text_input("검색", value="", placeholder="예: 마취크림", key="order_product_search")
            result = core_app.search_products(keyword, vendor_name, products, aliases)
            selected = None
            if keyword and result.empty:
                st.warning("검색 결과가 없습니다.")
            elif not result.empty:
                view_cols = [
                    c for c in ["별칭(검색어)", "정식제품명", "제품코드", "규격", "단위"]
                    if c in result.columns
                ]
                st.dataframe(result[view_cols].head(30), use_container_width=True, hide_index=True, height=180)
                selected_index = st.selectbox(
                    "제품 선택",
                    list(result.index[:30]),
                    format_func=lambda i: f'{result.loc[i, "별칭(검색어)"]} → {result.loc[i, "정식제품명"]}',
                    key="order_product_pick",
                )
                selected = result.loc[selected_index]

            if selected is not None:
                c1, c2 = st.columns([3, 1])
                c1.markdown(
                    f'**{selected.get("정식제품명", "")}**  \n'
                    f'{selected.get("규격", "")} / {selected.get("단위", "")}'
                )
                qty = c2.number_input("수량", min_value=1, value=1, step=1, key="order_add_qty")
                if st.button("선택 제품 추가", type="primary", use_container_width=True):
                    item = {
                        "제품코드": selected.get("제품코드", ""),
                        "정식제품명": selected.get("정식제품명", ""),
                        "검색별칭": selected.get("별칭(검색어)", ""),
                        "규격": selected.get("규격", ""),
                        "단위": selected.get("단위", ""),
                        "포장단위": selected.get("단위", ""),
                        "수량": int(qty),
                    }
                    st.session_state.order_items = _add_or_merge_item(st.session_state.order_items, item)
                    st.rerun()

        with st.container(border=True):
            st.markdown("### 발주 품목")
            if not st.session_state.order_items:
                st.info("발주 품목이 없습니다.")
            else:
                edit = pd.DataFrame(st.session_state.order_items)
                edit["삭제"] = False
                for col in ["제품코드", "정식제품명", "규격", "단위", "수량"]:
                    if col not in edit.columns:
                        edit[col] = ""
                edited = st.data_editor(
                    edit[["삭제", "제품코드", "정식제품명", "규격", "단위", "수량"]],
                    use_container_width=True,
                    hide_index=True,
                    disabled=["제품코드", "정식제품명", "규격", "단위"],
                    column_config={
                        "삭제": st.column_config.CheckboxColumn("삭제"),
                        "수량": st.column_config.NumberColumn("수량", min_value=0, step=1),
                    },
                    key="order_items_editor_v1",
                )
                remaining = []
                for idx, row in edited.iterrows():
                    if bool(row.get("삭제", False)):
                        continue
                    original = dict(st.session_state.order_items[idx])
                    original["수량"] = core_app.safe_int(row.get("수량", 0))
                    remaining.append(original)
                if st.button("품목 변경사항 적용", use_container_width=True):
                    st.session_state.order_items = remaining
                    st.rerun()
                count, total = core_app.calc_totals(remaining)
                st.caption(f"총 {count:,}개 품목 / 총 수량 {total:,}")

        with st.container(border=True):
            order_date = st.date_input(
                "발주일자",
                value=st.session_state.get("order_date", datetime.now().date()),
                key="order_date",
            )
            request_note = st.text_area(
                "요청사항",
                value=st.session_state.get("loaded_request_note", ""),
                key="order_request_note",
            )
            c1, c2, c3 = st.columns(3)
            if c1.button("임시저장", use_container_width=True):
                draft_id = core_app.save_draft(vendor_name, request_note, st.session_state.order_items)
                st.success(f"임시저장 완료: {draft_id}")
            if c2.button("발주완료", type="primary", use_container_width=True):
                if not st.session_state.order_items:
                    st.warning("발주 품목을 추가하세요.")
                else:
                    order_id = core_app.save_order(vendor_name, request_note, st.session_state.order_items)
                    st.success(f"발주 완료: {order_id}")
            export_path = core_app.create_excel(
                vendor,
                st.session_state.order_items,
                request_note,
                order_date.strftime("%Y-%m-%d"),
            )
            with open(export_path, "rb") as file:
                c3.download_button("엑셀 저장", file, file_name=Path(export_path).name, use_container_width=True)

        if not drafts_df.empty:
            with st.expander("임시저장 불러오기"):
                draft_id = st.selectbox(
                    "임시저장",
                    drafts_df["임시ID"].astype(str).tolist(),
                    key="order_draft_pick",
                )
                if st.button("선택 임시저장 불러오기", key="order_load_draft"):
                    header = drafts_df[drafts_df["임시ID"].astype(str) == draft_id].iloc[0]
                    rows = draft_items[draft_items["임시ID"].astype(str) == draft_id]
                    st.session_state.order_items = _normalise_items(core_app, rows)
                    st.session_state.loaded_vendor_name = str(header.get("거래처명", ""))
                    st.session_state.loaded_request_note = str(header.get("요청사항", ""))
                    st.rerun()

    with right:
        with st.container(border=True):
            preview_date = st.session_state.get("order_date", datetime.now().date())
            core_app.render_purchase_preview(
                vendor,
                st.session_state.order_items,
                st.session_state.get("order_request_note", ""),
                preview_date.strftime("%Y-%m-%d"),
            )


def drafts(core_app, data) -> None:
    st = core_app.st
    headers = data["drafts"]
    items = data["draft_items"]
    st.markdown("## 임시저장 목록")
    if headers.empty:
        st.info("임시저장된 발주서가 없습니다.")
        return
    st.dataframe(headers, use_container_width=True, hide_index=True)
    selected = st.selectbox("임시저장 선택", headers["임시ID"].astype(str).tolist())
    c1, c2 = st.columns(2)
    if c1.button("불러오기", use_container_width=True):
        header = headers[headers["임시ID"].astype(str) == selected].iloc[0]
        rows = items[items["임시ID"].astype(str) == selected]
        st.session_state.order_items = _normalise_items(core_app, rows)
        st.session_state.loaded_vendor_name = str(header.get("거래처명", ""))
        st.session_state.loaded_request_note = str(header.get("요청사항", ""))
        st.session_state.current_page = "발주 작성"
        st.rerun()
    if c2.button("삭제", use_container_width=True):
        core_app.delete_draft(selected)
        st.success("삭제했습니다.")
        st.rerun()


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


def _receipt_status_map(core_app, purchase_module, order_items: pd.DataFrame) -> dict[str, str]:
    """발주서별 입고 진행 상태를 계산합니다."""
    if purchase_module is None or order_items.empty:
        return {}

    statements, statement_items, _, _ = purchase_module.load_purchase_data()
    ordered_by_order: dict[str, dict[tuple, int]] = {}
    for _, row in order_items.iterrows():
        order_id = str(row.get("발주ID", "") or "").strip()
        if not order_id:
            continue
        key = _item_key(row)
        ordered_qty = core_app.safe_int(row.get("수량", 0))
        order_bucket = ordered_by_order.setdefault(order_id, {})
        order_bucket[key] = order_bucket.get(key, 0) + ordered_qty

    received_by_order: dict[str, dict[tuple, int]] = {}
    if not statements.empty and not statement_items.empty:
        statement_order = statements.set_index("명세서ID")["발주ID"].astype(str).to_dict()
        for _, row in statement_items.iterrows():
            statement_id = str(row.get("명세서ID", "") or "").strip()
            order_id = str(statement_order.get(statement_id, "") or "").strip()
            if not order_id:
                continue
            key = _item_key(row)
            received_qty = purchase_module.to_int(row.get("입고수량", 0))
            order_bucket = received_by_order.setdefault(order_id, {})
            order_bucket[key] = order_bucket.get(key, 0) + received_qty

    status_by_order: dict[str, str] = {}
    for order_id, ordered in ordered_by_order.items():
        received = received_by_order.get(order_id, {})
        total_received = sum(received.get(key, 0) for key in ordered)
        if total_received <= 0:
            status_by_order[order_id] = "발주완료"
            continue
        all_received = all(received.get(key, 0) >= qty for key, qty in ordered.items() if qty > 0)
        status_by_order[order_id] = "입고완료" if all_received else "부분입고"
    return status_by_order


def _status_cell_style(value) -> str:
    """발주서 목록의 상태 셀 배경색을 반환합니다."""
    status = str(value or "").strip()
    if status == "입고완료":
        return "background-color: #d9f99d; color: #111827; font-weight: 700;"
    if status == "부분입고":
        return "background-color: #fde68a; color: #111827; font-weight: 700;"
    return ""


def _style_status_column(frame: pd.DataFrame):
    if "상태" not in frame.columns:
        return frame
    return map_cells(frame.style, _status_cell_style, subset=["상태"])


def _receipt_review(core_app, purchase_module, order_id: str, order_items: pd.DataFrame) -> None:
    st = core_app.st
    statements, statement_items, _, _ = purchase_module.load_purchase_data()
    linked = statements[statements["발주ID"].astype(str) == str(order_id)] if not statements.empty else statements
    linked_ids = linked["명세서ID"].astype(str).tolist() if not linked.empty else []
    received_rows = (
        statement_items[statement_items["명세서ID"].astype(str).isin(linked_ids)]
        if linked_ids else statement_items.iloc[0:0]
    )
    received = {}
    for _, row in received_rows.iterrows():
        key = _item_key(row)
        received[key] = received.get(key, 0) + purchase_module.to_int(row.get("입고수량", 0))

    review_rows = []
    for _, row in order_items.iterrows():
        ordered_qty = purchase_module.to_int(row.get("수량", 0))
        received_qty = received.get(_item_key(row), 0)
        if received_qty <= 0:
            status = "미입고"
        elif received_qty < ordered_qty:
            status = "입고가 덜 됨"
        elif received_qty == ordered_qty:
            status = "입고완료"
        else:
            status = "초과입고"
        review_rows.append({
            "제품명": row.get("정식제품명", row.get("제품명", "")),
            "규격": row.get("규격", ""),
            "포장단위": row.get("단위", row.get("포장단위", "")),
            "발주수량": ordered_qty,
            "거래명세서 확인수량": received_qty,
            "상태": status,
        })

    review = pd.DataFrame(review_rows)
    st.markdown("### 입고 검수 요약")
    if review.empty:
        st.info("발주 품목이 없습니다.")
        return

    partial = review.loc[review["상태"] == "입고가 덜 됨", "제품명"].astype(str).tolist()
    missing = review.loc[review["상태"] == "미입고", "제품명"].astype(str).tolist()
    over = review.loc[review["상태"] == "초과입고", "제품명"].astype(str).tolist()
    messages = []
    if partial:
        messages.append("입고가 덜 된 품목은 " + ", ".join(partial) + "입니다.")
    if missing:
        messages.append("아직 입고되지 않은 품목은 " + ", ".join(missing) + "입니다.")
    if over:
        messages.append("발주수량보다 많이 확인된 품목은 " + ", ".join(over) + "입니다.")
    if not messages:
        messages.append("모든 발주 품목의 입고가 거래명세서로 확인되었습니다.")
    st.info("\n\n".join(messages))
    st.dataframe(review, use_container_width=True, hide_index=True)


def order_list(core_app, data, purchase_module=None) -> None:
    st = core_app.st
    vendors = data["vendors"]
    headers = data["orders"]
    items = data["order_items"]
    st.markdown("## 발주서 목록")
    if headers.empty:
        st.info("발주서가 없습니다.")
        return

    display_headers = headers.copy()
    if "상태" not in display_headers.columns:
        display_headers["상태"] = "발주완료"
    status_by_order = _receipt_status_map(core_app, purchase_module, items)
    if status_by_order:
        display_headers["상태"] = display_headers.apply(
            lambda row: status_by_order.get(str(row.get("발주ID", "")), str(row.get("상태", "발주완료") or "발주완료")),
            axis=1,
        )

    st.dataframe(_style_status_column(display_headers), use_container_width=True, hide_index=True)
    vendor_map = headers.set_index("발주ID")["거래처명"].astype(str).to_dict()
    selected = st.selectbox(
        "발주서 선택",
        headers["발주ID"].astype(str).tolist(),
        format_func=lambda oid: f'[{vendor_map.get(oid, "")}] {oid}',
    )
    header = headers[headers["발주ID"].astype(str) == selected].iloc[0]
    detail = items[items["발주ID"].astype(str) == selected].copy()
    if not detail.empty:
        cols = [c for c in ["제품코드", "정식제품명", "규격", "단위", "수량"] if c in detail.columns]
        st.dataframe(detail[cols], use_container_width=True, hide_index=True)

    c1, c2, c3 = st.columns(3)
    if c1.button("복사하여 새 발주", use_container_width=True):
        st.session_state.order_items = _normalise_items(core_app, detail)
        st.session_state.loaded_vendor_name = str(header.get("거래처명", ""))
        st.session_state.loaded_request_note = str(header.get("요청사항", ""))
        st.session_state.current_page = "발주 작성"
        st.rerun()
    if c2.button("삭제", use_container_width=True):
        core_app.delete_order(selected)
        st.success("발주서와 연결 데이터가 삭제되었습니다.")
        st.rerun()

    vendor_row = vendors[vendors["거래처명"].astype(str) == str(header.get("거래처명", ""))]
    if not vendor_row.empty:
        export = core_app.create_excel(
            vendor_row.iloc[0],
            _normalise_items(core_app, detail),
            header.get("요청사항", ""),
        )
        with open(export, "rb") as file:
            c3.download_button("엑셀 다운로드", file, file_name=Path(export).name, use_container_width=True)

    if purchase_module is not None:
        _receipt_review(core_app, purchase_module, selected, detail)


def recent(core_app, data) -> None:
    st = core_app.st
    headers = data["orders"]
    items = data["order_items"]
    st.markdown("## 최근 발주 내역")
    if headers.empty:
        st.info("발주 이력이 없습니다.")
        return
    view = headers.copy().sort_values("발주일시", ascending=False).head(30)
    if "상태" not in view.columns:
        view["상태"] = "발주완료"
    status_by_order = _receipt_status_map(core_app, None, items)
    if status_by_order:
        view["상태"] = view.apply(
            lambda row: status_by_order.get(str(row.get("발주ID", "")), str(row.get("상태", "발주완료") or "발주완료")),
            axis=1,
        )
    st.dataframe(_style_status_column(view), use_container_width=True, hide_index=True)
