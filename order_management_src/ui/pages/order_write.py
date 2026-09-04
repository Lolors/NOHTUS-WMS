"""발주 작성 전용 화면."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from ui.export_cache import export_fingerprint, get_or_create_excel
from ui.pages.orders import _add_or_merge_item, _normalise_items, _vendor_panel


_ORDER_FORM_RESET_KEYS = [
    "loaded_vendor_name",
    "loaded_request_note",
    "order_product_search",
    "order_product_pick",
    "order_items_editor_v2",
]


def _reset_order_form_state(st) -> None:
    """발주완료 후 작성 화면에 남은 입력값을 초기화합니다."""
    st.session_state.order_items = []
    st.session_state["order_request_note"] = ""
    st.session_state["order_add_qty"] = 1
    st.session_state["order_date"] = datetime.now().date()
    st.session_state.pop("order_excel_export", None)
    for key in _ORDER_FORM_RESET_KEYS:
        st.session_state.pop(key, None)


def _latest_product_order(core_app, vendor_name, product_code, orders_df, saved_items):
    """같은 거래처·제품의 가장 최근 발주일과 수량을 반환합니다."""
    vendor_name = str(vendor_name or "").strip()
    product_code = str(product_code or "").strip()
    if not vendor_name or not product_code or orders_df.empty or saved_items.empty:
        return None

    vendor_orders = orders_df[orders_df["거래처명"].astype(str) == vendor_name].copy()
    if vendor_orders.empty:
        return None

    vendor_orders["발주ID"] = vendor_orders["발주ID"].astype(str)
    vendor_orders["_ordered_at"] = pd.to_datetime(vendor_orders["발주일시"], errors="coerce")
    order_dates = vendor_orders.set_index("발주ID")["_ordered_at"].to_dict()

    items = saved_items.copy()
    items = items[
        (items["발주ID"].astype(str).isin(vendor_orders["발주ID"]))
        & (items["제품코드"].astype(str).str.strip() == product_code)
    ].copy()
    if items.empty:
        return None

    items["_ordered_at"] = items["발주ID"].astype(str).map(order_dates)
    items["_quantity"] = items["수량"].apply(lambda value: core_app.safe_int(value, 0))
    latest_date = items["_ordered_at"].max()
    latest_rows = items[items["_ordered_at"] == latest_date]
    quantity = int(latest_rows["_quantity"].sum())
    order_id = str(latest_rows.iloc[0].get("발주ID", ""))
    return {
        "date": "" if pd.isna(latest_date) else latest_date.strftime("%Y-%m-%d"),
        "quantity": quantity,
        "order_id": order_id,
    }


def _render_latest_product_order_card(st, latest_product_order) -> None:
    """거래처 선택 영역 안에 선택 제품의 최근 발주 수량 카드를 표시합니다."""
    with st.container(border=True):
        if latest_product_order is None:
            st.markdown(
                """
                <div style="text-align:center; padding:8px 0;">
                    <div style="font-size:1rem; font-weight:700;">최근 발주 수량</div>
                    <div style="margin-top:8px; color:#6b7280;">이전 발주 이력 없음</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"""
                <div style="text-align:center; padding:8px 0;">
                    <div style="font-size:1rem; font-weight:700;">최근 발주 수량</div>
                    <div style="font-size:2rem; font-weight:800; margin-top:6px;">
                        {latest_product_order['quantity']:,}개
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def _render_excel_export(st, core_app, vendor, order_items, request_note: str, order_date_text: str, column) -> None:
    """엑셀 파일을 명시적으로 생성하고 같은 내용이면 기존 파일을 재사용합니다."""
    fingerprint = export_fingerprint(vendor, order_items, request_note, order_date_text, "excel")
    if column.button("엑셀 생성", use_container_width=True):
        if not order_items:
            st.warning("엑셀로 저장할 발주 품목이 없습니다.")
        else:
            export_path = get_or_create_excel(core_app, vendor, order_items, request_note, order_date_text)
            st.session_state["order_excel_export"] = {
                "fingerprint": fingerprint,
                "path": str(export_path),
            }
            st.success(f"엑셀 생성 완료: {Path(export_path).name}")

    export_state = st.session_state.get("order_excel_export", {})
    if export_state.get("fingerprint") != fingerprint:
        column.caption("엑셀 생성 후 다운로드할 수 있습니다.")
        return

    export_path = Path(str(export_state.get("path", "")))
    if not export_path.exists():
        column.caption("엑셀 파일을 다시 생성하세요.")
        return

    with open(export_path, "rb") as file:
        column.download_button(
            "엑셀 다운로드",
            file,
            file_name=export_path.name,
            use_container_width=True,
        )


def render(core_app, data) -> None:
    st = core_app.st
    vendors = data["vendors"]
    products = data["products"]
    aliases = data["aliases"]
    drafts_df = data["drafts"]
    draft_items = data["draft_items"]
    orders_df = data["orders"]
    saved_items = data["order_items"]

    if st.session_state.pop("reset_order_form_after_save", False):
        _reset_order_form_state(st)

    st.markdown(
        """
<style>
.st-key-order_date { transform: translateY(6px); }
</style>
""",
        unsafe_allow_html=True,
    )
    title_col, date_col, _ = st.columns(
        [0.85, 1.25, 5], gap="small", vertical_alignment="center"
    )
    title_col.markdown("## 발주 작성")
    order_date = date_col.date_input(
        "발주일자",
        value=st.session_state.get("order_date", datetime.now().date()),
        key="order_date",
        label_visibility="collapsed",
        help="발주일자",
    )
    if st.session_state.pop("order_saved_success", False):
        saved_order_id = st.session_state.pop("last_saved_order_id", "")
        st.success(f"발주 완료: {saved_order_id}")

    if vendors.empty:
        st.warning("먼저 거래처를 등록하세요.")
        return

    workspace, preview = st.columns([1.12, 1], gap="medium")

    with workspace:
        vendor_col, search_col = st.columns([0.9, 1.1], gap="small")
        selected = None
        latest_product_slot = None

        with vendor_col:
            with st.container(border=True):
                st.markdown("### 거래처 선택")
                vendor_names = vendors["거래처명"].astype(str).tolist()
                loaded_vendor = st.session_state.get("loaded_vendor_name", "")
                default_index = vendor_names.index(loaded_vendor) if loaded_vendor in vendor_names else 0
                vendor_name = st.selectbox(
                    "거래처",
                    vendor_names,
                    index=default_index,
                    key="order_vendor",
                    label_visibility="collapsed",
                )
                vendor = vendors[vendors["거래처명"].astype(str) == vendor_name].iloc[0]
                _vendor_panel(st, vendor)

                latest = orders_df[orders_df["거래처명"].astype(str) == vendor_name].copy()
                if not latest.empty:
                    latest = latest.sort_values("발주일시", ascending=False).iloc[0]
                    if st.button("최근 발주 복사", use_container_width=True, key="copy_latest_order"):
                        rows = saved_items[
                            saved_items["발주ID"].astype(str) == str(latest["발주ID"])
                        ]
                        st.session_state.order_items = _normalise_items(core_app, rows)
                        st.session_state.pop("order_excel_export", None)
                        st.rerun()
                else:
                    st.caption("최근 발주 이력이 없습니다.")

                latest_product_slot = st.empty()

        with search_col:
            with st.container(border=True):
                st.markdown("### 제품 검색")
                keyword = st.text_input(
                    "검색",
                    value="",
                    placeholder="예: 마취크림",
                    key="order_product_search",
                    label_visibility="collapsed",
                )
                result = core_app.search_products(keyword, vendor_name, products, aliases)

                if keyword and result.empty:
                    st.warning("검색 결과가 없습니다.")
                elif not result.empty:
                    view_cols = [
                        c
                        for c in ["별칭(검색어)", "정식제품명", "제품코드", "규격", "단위"]
                        if c in result.columns
                    ]
                    st.dataframe(
                        result[view_cols].head(30),
                        use_container_width=True,
                        hide_index=True,
                        height=180,
                    )
                    selected_index = st.selectbox(
                        "제품 선택",
                        list(result.index[:30]),
                        format_func=lambda i: (
                            f'{result.loc[i, "별칭(검색어)"]} → '
                            f'{result.loc[i, "정식제품명"]}'
                        ),
                        key="order_product_pick",
                        label_visibility="collapsed",
                    )
                    selected = result.loc[selected_index]

                if selected is not None:
                    info_col, qty_col = st.columns([3, 1])
                    info_col.markdown(
                        f'**{selected.get("정식제품명", "")}**  \n'
                        f'{selected.get("규격", "")} / {selected.get("단위", "")}'
                    )
                    qty = qty_col.number_input(
                        "수량", min_value=1, value=1, step=1, key="order_add_qty"
                    )
                    if st.button(
                        "선택 제품 추가",
                        type="primary",
                        use_container_width=True,
                        key="add_selected_product",
                    ):
                        item = {
                            "제품코드": selected.get("제품코드", ""),
                            "정식제품명": selected.get("정식제품명", ""),
                            "검색별칭": selected.get("별칭(검색어)", ""),
                            "규격": selected.get("규격", ""),
                            "단위": selected.get("단위", ""),
                            "포장단위": selected.get("단위", ""),
                            "수량": int(qty),
                        }
                        st.session_state.order_items = _add_or_merge_item(
                            st.session_state.order_items, item
                        )
                        st.session_state.pop("order_excel_export", None)
                        st.rerun()

        if selected is not None and latest_product_slot is not None:
            latest_product_order = _latest_product_order(
                core_app,
                vendor_name,
                selected.get("제품코드", ""),
                orders_df,
                saved_items,
            )
            with latest_product_slot.container():
                _render_latest_product_order_card(st, latest_product_order)

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
                        "삭제": st.column_config.CheckboxColumn("선택"),
                        "수량": st.column_config.NumberColumn("수량", min_value=0, step=1),
                        "단위": st.column_config.TextColumn("포장단위"),
                    },
                    key="order_items_editor_v2",
                )

                updated_items = []
                checked_indexes = []
                for idx, row in edited.iterrows():
                    original = dict(st.session_state.order_items[idx])
                    original["수량"] = core_app.safe_int(row.get("수량", 0))
                    updated_items.append(original)
                    if bool(row.get("삭제", False)):
                        checked_indexes.append(idx)

                action_col, delete_col, summary_col = st.columns([1.1, 1.1, 2])
                if action_col.button("수량 변경 적용", use_container_width=True):
                    st.session_state.order_items = updated_items
                    st.session_state.pop("order_excel_export", None)
                    st.rerun()

                if delete_col.button("선택 품목 삭제", use_container_width=True):
                    if not checked_indexes:
                        st.warning("삭제할 품목을 체크하세요.")
                    else:
                        st.session_state.order_items = [
                            item
                            for idx, item in enumerate(updated_items)
                            if idx not in checked_indexes
                        ]
                        st.session_state.pop("order_excel_export", None)
                        st.rerun()

                count, total = core_app.calc_totals(updated_items)
                summary_col.markdown(
                    f"<div style='text-align:right;padding-top:8px;font-weight:700;'>"
                    f"총 {count:,}개 품목 / 총 수량 {total:,}</div>",
                    unsafe_allow_html=True,
                )

        with st.container(border=True):
            st.markdown("### 요청사항 및 발주 저장")
            request_note = st.text_area(
                "요청사항",
                value=st.session_state.get("loaded_request_note", ""),
                key="order_request_note",
            )
            c1, c2, c3 = st.columns(3)
            if c1.button("임시저장", use_container_width=True):
                draft_id = core_app.save_draft(
                    vendor_name, request_note, st.session_state.order_items
                )
                st.success(f"임시저장 완료: {draft_id}")
            if c2.button("발주완료", type="primary", use_container_width=True):
                if not st.session_state.order_items:
                    st.warning("발주 품목을 추가하세요.")
                else:
                    order_id = core_app.save_order(
                        vendor_name, request_note, st.session_state.order_items
                    )
                    st.session_state["last_saved_order_id"] = order_id
                    st.session_state["order_saved_success"] = True
                    st.session_state["reset_order_form_after_save"] = True
                    st.rerun()

            export_items = st.session_state.order_items
            export_note = st.session_state.get("order_request_note", request_note)
            _render_excel_export(
                st,
                core_app,
                vendor,
                export_items,
                export_note,
                order_date.strftime("%Y-%m-%d"),
                c3,
            )

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
                    st.session_state.pop("order_excel_export", None)
                    st.rerun()

    with preview:
        with st.container(border=True):
            preview_date = st.session_state.get("order_date", datetime.now().date())
            core_app.render_purchase_preview(
                vendor,
                st.session_state.order_items,
                st.session_state.get("order_request_note", ""),
                preview_date.strftime("%Y-%m-%d"),
            )
