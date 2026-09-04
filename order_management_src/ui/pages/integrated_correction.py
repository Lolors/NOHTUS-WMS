"""발주서부터 연결 거래명세서까지 한 번에 바로잡는 화면."""
from __future__ import annotations

from datetime import datetime

import pandas as pd


ORDER_ITEM_COLUMNS = ["제품코드", "정식제품명", "검색별칭", "규격", "단위", "수량"]
STATEMENT_COLUMNS = [
    "명세서ID", "명세서번호", "명세서일자", "운송비", "운송비입력여부", "메모", "등록일시"
]
STATEMENT_ITEM_COLUMNS = [
    "명세서ID", "제품코드", "정식제품명", "규격", "단위", "발주수량", "입고수량",
    "매입단가", "상품금액", "출고단가", "가격적용여부", "제조번호", "유통기한", "입고유형",
    "대체사유", "원발주제품코드", "원발주제품명", "원발주규격", "원발주단위",
]


def _ensure_columns(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    result = frame.copy().fillna("")
    for column in columns:
        if column not in result.columns:
            result[column] = ""
    return result[columns]


def _order_options(headers: pd.DataFrame) -> tuple[list[str], dict[str, str]]:
    labels = []
    lookup = {}
    working = headers.copy()
    working["_date"] = pd.to_datetime(working["발주일시"], errors="coerce")
    for _, row in working.sort_values("_date", ascending=False).iterrows():
        order_id = str(row.get("발주ID", ""))
        date_text = "" if pd.isna(row["_date"]) else row["_date"].strftime("%Y-%m-%d")
        label = f'[{row.get("거래처명", "")}] {date_text} · {order_id}'
        labels.append(label)
        lookup[label] = order_id
    return labels, lookup


def render(core_app, data, purchase_module) -> None:
    st = core_app.st
    orders = data["orders"].copy()
    order_items = data["order_items"].copy()
    vendors = data["vendors"].copy()
    statements, statement_items, _, _ = purchase_module.load_purchase_data()

    st.markdown("## 통합 수정")
    st.warning(
        "이 화면은 과거 자료를 대량으로 바로잡을 때만 사용하세요. "
        "저장하면 선택한 발주서와 연결 거래명세서가 한 번에 변경됩니다."
    )
    if orders.empty:
        st.info("수정할 발주서가 없습니다.")
        return

    search = st.text_input(
        "발주서 검색", placeholder="거래처명 또는 발주ID 일부 입력", key="correction_search"
    )
    filtered = orders.copy()
    keyword = str(search or "").strip()
    if keyword:
        filtered = filtered[
            filtered["거래처명"].astype(str).str.contains(keyword, case=False, na=False, regex=False)
            | filtered["발주ID"].astype(str).str.contains(keyword, case=False, na=False, regex=False)
        ]
    options, lookup = _order_options(filtered)
    if not options:
        st.info("검색 조건에 맞는 발주서가 없습니다.")
        return

    selected_label = st.selectbox("수정할 발주서", options, key="correction_order")
    order_id = lookup[selected_label]
    header = orders[orders["발주ID"].astype(str) == order_id].iloc[0]
    selected_order_items = order_items[order_items["발주ID"].astype(str) == order_id]
    linked_statements = statements[statements["발주ID"].astype(str) == order_id]
    linked_ids = set(linked_statements["명세서ID"].astype(str))
    linked_items = statement_items[statement_items["명세서ID"].astype(str).isin(linked_ids)]

    st.caption(
        f"발주 품목 {len(selected_order_items):,}개 · "
        f"거래명세서 {len(linked_statements):,}건 · 명세서 품목 {len(linked_items):,}개"
    )

    with st.form(f"integrated_correction_form_{order_id}"):
        st.markdown("### 1. 발주서 기본정보")
        ordered_at = pd.to_datetime(header.get("발주일시", ""), errors="coerce")
        if pd.isna(ordered_at):
            ordered_at = pd.Timestamp.now()
        c1, c2, c3 = st.columns([1, 2, 3], gap="small")
        order_date = c1.date_input("발주일자", value=ordered_at.date())
        vendor_names = vendors["거래처명"].astype(str).tolist()
        current_vendor = str(header.get("거래처명", ""))
        vendor_index = vendor_names.index(current_vendor) if current_vendor in vendor_names else 0
        vendor_name = c2.selectbox("거래처", vendor_names, index=vendor_index)
        request_note = c3.text_input("요청사항", value=str(header.get("요청사항", "") or ""))

        st.markdown("### 2. 발주 품목")
        st.caption("행 추가·삭제와 제품명, 규격, 수량 등의 일괄 수정이 가능합니다.")
        edited_order_items = st.data_editor(
            _ensure_columns(selected_order_items, ORDER_ITEM_COLUMNS),
            use_container_width=True,
            hide_index=True,
            num_rows="dynamic",
            key=f"correction_order_items_{order_id}",
            column_config={
                "수량": st.column_config.NumberColumn(min_value=0, step=1),
            },
        )

        st.markdown("### 3. 연결 거래명세서")
        st.caption("거래처명은 위에서 선택한 거래처로 모든 명세서에 자동 반영됩니다.")
        statement_view = _ensure_columns(linked_statements, STATEMENT_COLUMNS)
        if not statement_view.empty:
            statement_view["명세서일자"] = pd.to_datetime(
                statement_view["명세서일자"], errors="coerce"
            ).dt.date
        edited_statements = st.data_editor(
            statement_view,
            use_container_width=True,
            hide_index=True,
            key=f"correction_statements_{order_id}",
            num_rows="dynamic",
            disabled=["명세서ID", "등록일시"],
            column_config={
                "명세서일자": st.column_config.DateColumn(format="YYYY-MM-DD"),
                "운송비": st.column_config.NumberColumn(min_value=0, step=1000),
                "운송비입력여부": st.column_config.SelectboxColumn(options=["Y", "N"]),
            },
        )

        st.markdown("### 4. 거래명세서 품목")
        st.caption(
            "일반 품목의 상품금액은 저장 시 입고수량 × 매입단가로 다시 계산됩니다. "
            "반품 기록의 상품금액은 기존 값을 보존합니다."
        )
        edited_statement_items = st.data_editor(
            _ensure_columns(linked_items, STATEMENT_ITEM_COLUMNS),
            use_container_width=True,
            hide_index=True,
            num_rows="dynamic",
            key=f"correction_statement_items_{order_id}",
            column_config={
                "명세서ID": st.column_config.SelectboxColumn(
                    options=linked_statements["명세서ID"].astype(str).tolist()
                ),
                "발주수량": st.column_config.NumberColumn(min_value=0, step=1),
                "입고수량": st.column_config.NumberColumn(min_value=0, step=1),
                "매입단가": st.column_config.NumberColumn(min_value=0, step=100),
                "상품금액": st.column_config.NumberColumn(step=100),
                "출고단가": st.column_config.NumberColumn(min_value=0, step=100),
                "가격적용여부": st.column_config.TextColumn(
                    help="일반 품목은 Y/N, 반품 기록은 기존 값을 유지하세요."
                ),
            },
        )

        confirm = st.checkbox(
            "선택한 발주서와 연결 거래명세서를 위 내용으로 한 번에 변경합니다."
        )
        submitted = st.form_submit_button(
            "통합 수정 저장", type="primary", use_container_width=True, disabled=not confirm
        )

    if submitted:
        corrected_time = datetime.combine(order_date, ordered_at.time().replace(microsecond=0))
        corrected_header = {
            "발주일시": corrected_time,
            "거래처명": vendor_name,
            "요청사항": request_note,
            "상태": str(header.get("상태", "발주완료") or "발주완료"),
        }
        try:
            core_app.correction_service.save_bundle(
                order_id,
                corrected_header,
                edited_order_items,
                edited_statements,
                edited_statement_items,
            )
        except ValueError as exc:
            st.error(str(exc))
        except Exception as exc:
            st.error(f"통합 수정 저장 중 오류가 발생했습니다: {exc}")
        else:
            st.success(f"발주서와 연결 거래명세서를 모두 수정했습니다: {order_id}")
            st.rerun()
