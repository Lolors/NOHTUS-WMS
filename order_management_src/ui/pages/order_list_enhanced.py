"""행 클릭과 검색 필터를 제공하는 발주서 목록 화면."""
from __future__ import annotations

import calendar
from datetime import datetime
from pathlib import Path

import pandas as pd

from ui.month_grid import render_month_grid
from ui.pages import orders


def _selected_rows(event) -> list[int]:
    """Streamlit 버전에 따라 다른 선택 이벤트 형태를 안전하게 읽습니다."""
    if event is None:
        return []
    selection = getattr(event, "selection", None)
    if selection is None and isinstance(event, dict):
        selection = event.get("selection", {})
    if isinstance(selection, dict):
        return list(selection.get("rows", []) or [])
    return list(getattr(selection, "rows", []) or [])


def _filter_orders(headers, items, start_date, end_date, vendor_name, keyword):
    """기간·거래처·품목 일부 일치 조건으로 발주서를 필터링합니다."""
    filtered = headers.copy()
    filtered["_ordered_date"] = pd.to_datetime(
        filtered.get("발주일시", ""), errors="coerce"
    ).dt.date
    filtered = filtered[
        (filtered["_ordered_date"] >= start_date)
        & (filtered["_ordered_date"] <= end_date)
    ]

    if vendor_name != "전체":
        filtered = filtered[filtered["거래처명"].astype(str) == vendor_name]

    keyword_text = str(keyword or "").strip()
    if keyword_text:
        item_rows = items.copy()
        for column in ["발주ID", "제품코드", "정식제품명", "규격"]:
            if column not in item_rows.columns:
                item_rows[column] = ""
        match = (
            item_rows["제품코드"].astype(str).str.contains(
                keyword_text, case=False, na=False, regex=False
            )
            | item_rows["정식제품명"].astype(str).str.contains(
                keyword_text, case=False, na=False, regex=False
            )
            | item_rows["규격"].astype(str).str.contains(
                keyword_text, case=False, na=False, regex=False
            )
        )
        matching_order_ids = set(item_rows.loc[match, "발주ID"].astype(str))
        filtered = filtered[
            filtered["발주ID"].astype(str).isin(matching_order_ids)
        ]

    return filtered.drop(columns=["_ordered_date"], errors="ignore")


def _sort_orders(headers: pd.DataFrame) -> pd.DataFrame:
    """미입고 발주를 먼저, 같은 상태 안에서는 최신순으로 정렬합니다."""
    result = headers.copy()
    result["_status_priority"] = (result["상태"].astype(str) != "발주완료").astype(int)
    return (
        result.sort_values(
            ["_status_priority", "발주일시"],
            ascending=[True, False],
        )
        .drop(columns=["_status_priority"])
        .reset_index(drop=True)
    )


def render(core_app, data, purchase_module=None) -> None:
    st = core_app.st
    vendors = data["vendors"]
    headers = data["orders"]
    items = data["order_items"]

    st.markdown("## 발주서 목록")
    if headers.empty:
        st.info("발주서가 없습니다.")
        return

    today = datetime.now().date()
    working_headers = headers.copy()
    if "상태" not in working_headers.columns:
        working_headers["상태"] = "발주완료"

    status_by_order = orders._receipt_status_map(core_app, purchase_module, items)
    if status_by_order:
        working_headers["상태"] = working_headers.apply(
            lambda row: status_by_order.get(
                str(row.get("발주ID", "")),
                str(row.get("상태", "발주완료") or "발주완료"),
            ),
            axis=1,
        )

    vendor_options = ["전체"] + sorted(
        working_headers["거래처명"].astype(str).replace("", pd.NA).dropna().unique().tolist()
    )
    with st.container(border=True):
        year, month = render_month_grid(st, "order_list", default_year=today.year, default_month=today.month)
        vendor_col, keyword_col = st.columns([1.5, 3], gap="small")
        vendor_name = vendor_col.selectbox(
            "거래처",
            vendor_options,
            key="order_list_vendor",
        )
        keyword = keyword_col.text_input(
            "발주 품목 검색",
            placeholder="제품명, 제품코드 또는 규격 일부 입력",
            key="order_list_product_keyword",
        )

    start_date = pd.Timestamp(year=year, month=month, day=1).date()
    end_date = pd.Timestamp(
        year=year, month=month, day=calendar.monthrange(year, month)[1]
    ).date()

    filtered_headers = _filter_orders(
        working_headers,
        items,
        start_date,
        end_date,
        vendor_name,
        keyword,
    )
    if filtered_headers.empty:
        st.info("검색 조건에 맞는 발주서가 없습니다.")
        return

    display_headers = _sort_orders(filtered_headers)

    st.caption(
        f"검색 결과 {len(display_headers):,}건 · 발주ID가 있는 행을 클릭하면 아래에 내용이 표시됩니다."
    )
    event = st.dataframe(
        orders._style_status_column(display_headers),
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="order_list_row_selection",
    )

    selected_rows = _selected_rows(event)
    if not selected_rows:
        st.info("내용을 확인할 발주서 행을 선택하세요.")
        return

    row_index = selected_rows[0]
    if row_index < 0 or row_index >= len(display_headers):
        st.warning("선택한 발주서를 확인할 수 없습니다.")
        return

    selected = str(display_headers.iloc[row_index].get("발주ID", ""))
    header_rows = headers[headers["발주ID"].astype(str) == selected]
    if header_rows.empty:
        st.warning("선택한 발주서가 현재 목록에 없습니다.")
        return

    header = header_rows.iloc[0]
    detail = items[items["발주ID"].astype(str) == selected].copy()
    st.markdown(f"### 선택한 발주서 · {selected}")
    if detail.empty:
        st.info("저장된 발주 품목이 없습니다.")
    else:
        cols = [
            column
            for column in ["제품코드", "정식제품명", "규격", "단위", "수량"]
            if column in detail.columns
        ]
        st.dataframe(detail[cols], use_container_width=True, hide_index=True)

    c1, c2, c3, c4 = st.columns(4)
    if c1.button("수정", type="primary", use_container_width=True, key=f"edit_order_{selected}"):
        st.session_state.order_items = orders._normalise_items(core_app, detail)
        st.session_state.loaded_vendor_name = str(header.get("거래처명", ""))
        st.session_state.loaded_request_note = str(header.get("요청사항", ""))
        ordered_at = pd.to_datetime(header.get("발주일시", ""), errors="coerce")
        if not pd.isna(ordered_at):
            st.session_state["order_date"] = ordered_at.date()
        st.session_state["order_management_editing_order_id"] = selected
        st.session_state.pop("order_excel_export", None)
        st.session_state.current_page = "발주 작성"
        st.rerun()

    if c2.button("복사하여 새 발주", use_container_width=True, key=f"copy_order_{selected}"):
        st.session_state.order_items = orders._normalise_items(core_app, detail)
        st.session_state.loaded_vendor_name = str(header.get("거래처명", ""))
        st.session_state.loaded_request_note = str(header.get("요청사항", ""))
        st.session_state.pop("order_management_editing_order_id", None)
        st.session_state.current_page = "발주 작성"
        st.rerun()

    if c3.button("삭제", use_container_width=True, key=f"delete_order_{selected}"):
        core_app.delete_order(selected)
        st.success("발주서와 연결 데이터가 삭제되었습니다.")
        st.rerun()

    vendor_row = vendors[
        vendors["거래처명"].astype(str) == str(header.get("거래처명", ""))
    ]
    if not vendor_row.empty:
        export = core_app.create_excel(
            vendor_row.iloc[0],
            orders._normalise_items(core_app, detail),
            header.get("요청사항", ""),
        )
        with open(export, "rb") as file:
            c4.download_button(
                "엑셀 다운로드",
                file,
                file_name=Path(export).name,
                use_container_width=True,
                key=f"download_order_{selected}",
            )

    if purchase_module is not None:
        orders._receipt_review(core_app, purchase_module, selected, detail)
