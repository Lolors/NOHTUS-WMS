import pandas as pd
import streamlit as st

import nohtus.pages.outbound as outbound_page
from nohtus.services.kakao_order_parser import parse_kakao_order


def _hide_last_sale_importer():
    return None


def _render_kakao_order_helper():
    with st.expander("카톡 주문 붙여넣기", expanded=False):
        st.caption("예: 한양재활 / 콘쥬란 4통 / 리쥬비넥스 10통 처럼 붙여넣으면 매출처와 품목 키워드를 추출합니다.")
        raw_text = st.text_area(
            "카카오톡 주문내용",
            placeholder="한양재활\n콘쥬란 4통\n리쥬비넥스 10통\n\n부탁드려요",
            height=150,
            key="kakao_order_text",
        )

        if st.button("주문내용 해석", use_container_width=True, key="kakao_order_parse_btn"):
            parsed = parse_kakao_order(raw_text)
            st.session_state["kakao_order_parsed"] = {
                "customer_keyword": parsed.customer_keyword,
                "items": [item.__dict__ for item in parsed.items],
                "note": parsed.note,
            }

        parsed_data = st.session_state.get("kakao_order_parsed") or {}
        items = parsed_data.get("items") or []
        customer_keyword = str(parsed_data.get("customer_keyword") or "").strip()
        note = str(parsed_data.get("note") or "").strip()

        if parsed_data:
            if customer_keyword:
                st.success(f"매출처 키워드: {customer_keyword}")
            else:
                st.warning("매출처 키워드를 찾지 못했습니다. 첫 줄에 매출처명을 넣으면 더 정확합니다.")

            if items:
                preview = pd.DataFrame(items).rename(
                    columns={
                        "product_keyword": "제품 키워드",
                        "qty": "수량",
                        "unit": "단위",
                        "raw_line": "원문",
                    }
                )
                st.dataframe(preview[["제품 키워드", "수량", "단위", "원문"]], hide_index=True, use_container_width=True)
                st.caption("아래 버튼을 누르면 기존 출고지시 입력칸에 검색어와 수량이 들어갑니다. 재고 추천을 확인한 뒤 장바구니에 담으세요.")
                for idx, item in enumerate(items):
                    label = f"{idx + 1}. {item.get('product_keyword')} {item.get('qty')}{item.get('unit') or ''} 불러오기"
                    if st.button(label, use_container_width=True, key=f"kakao_load_item_{idx}"):
                        if customer_keyword:
                            st.session_state["out_customer_term"] = customer_keyword
                            st.session_state["out_customer_direct"] = False
                            st.session_state.pop("_out_customer_label", None)
                        st.session_state["out_product_term"] = str(item.get("product_keyword") or "").strip()
                        st.session_state["out_req_qty"] = int(item.get("qty") or 1)
                        st.session_state.pop("out_rec_editor", None)
                        st.session_state.pop("out_manual_editor", None)
                        st.session_state["_outbound_last_success"] = "카톡 주문에서 추출한 매출처/제품/수량을 입력칸에 반영했습니다."
                        st.rerun()
            else:
                st.warning("품목과 수량을 찾지 못했습니다. 예: 콘쥬란 4통")

            if note:
                st.caption(f"메모로 인식한 내용: {note}")


def page_outbound():
    original_renderer = outbound_page._render_last_sale_importer
    original_text_input = st.text_input
    original_checkbox = st.checkbox
    original_data_editor = st.data_editor
    original_manual_pick_rows = outbound_page._manual_pick_rows

    st.markdown(
        """
        <style>
        div[data-testid="stCheckbox"] label, div[data-testid="stCheckbox"] p {
            white-space: nowrap !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    _render_kakao_order_helper()

    checkbox_skip_values = {}
    manual_source_df = {"df": None}

    def patched_text_input(label, *args, **kwargs):
        if kwargs.get("key") == "out_customer_term":
            search_col, direct_col = st.columns([8, 2], gap="small")
            with search_col:
                value = original_text_input(label, *args, **kwargs)
            with direct_col:
                st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
                direct_value = original_checkbox("직접입력", value=False, key="out_customer_direct")
            checkbox_skip_values["out_customer_direct"] = bool(direct_value)
            return value
        return original_text_input(label, *args, **kwargs)

    def patched_checkbox(label, *args, **kwargs):
        key = kwargs.get("key")
        if key in checkbox_skip_values:
            return checkbox_skip_values[key]
        if key == "out_ignore_company":
            # 화면에는 '사업장 구분 없이'를 표시하지 않고 항상 False 처리한다.
            manual_value = original_checkbox("특정 재고 선택", value=False, key="out_manual_pick")
            checkbox_skip_values["out_manual_pick"] = bool(manual_value)
            return False
        return original_checkbox(label, *args, **kwargs)

    def patched_data_editor(data, *args, **kwargs):
        if kwargs.get("key") == "out_manual_editor" and isinstance(data, pd.DataFrame):
            work = data.copy()
            if "요청수량" in work.columns:
                work = work.drop(columns=["요청수량"])
            edited = original_data_editor(work, *args, **kwargs)
            if isinstance(edited, pd.DataFrame):
                result = edited.copy()
                result["요청수량"] = 0
                selected_indexes = [idx for idx, row in result.iterrows() if bool(row.get("선택", False))]
                remain = int(st.session_state.get("out_req_qty", 0) or 0)
                for idx in selected_indexes:
                    available = int(result.at[idx, "현재수량"] or 0) if "현재수량" in result.columns else remain
                    use_qty = min(remain, available) if remain > 0 else 0
                    result.at[idx, "요청수량"] = use_qty
                    remain -= use_qty
                    if remain <= 0:
                        break
                return result
            return edited
        return original_data_editor(data, *args, **kwargs)

    def patched_manual_pick_rows(pick_df, editor_df):
        return original_manual_pick_rows(pick_df, editor_df)

    outbound_page._render_last_sale_importer = _hide_last_sale_importer
    outbound_page._manual_pick_rows = patched_manual_pick_rows
    st.text_input = patched_text_input
    st.checkbox = patched_checkbox
    st.data_editor = patched_data_editor
    try:
        return outbound_page.page_outbound()
    finally:
        outbound_page._render_last_sale_importer = original_renderer
        outbound_page._manual_pick_rows = original_manual_pick_rows
        st.text_input = original_text_input
        st.checkbox = original_checkbox
        st.data_editor = original_data_editor
