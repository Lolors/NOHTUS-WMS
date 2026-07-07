from datetime import date, datetime

import pandas as pd
import streamlit as st

import nohtus.pages.outbound as outbound_page
from nohtus.db import connect, q


def _hide_last_sale_importer():
    return None


def _default_outbound_date():
    if "outbound_order_date" in st.session_state:
        return st.session_state["outbound_order_date"]
    order_id = st.session_state.get("editing_order_id")
    if order_id:
        try:
            df = q("SELECT order_date FROM outbound_orders WHERE id=?", (int(order_id),))
            if not df.empty:
                value = str(df.iloc[0].get("order_date") or "").strip()
                if value:
                    return datetime.strptime(value[:10], "%Y-%m-%d").date()
        except Exception:
            pass
    return date.today()


def _selected_outbound_date_text():
    value = st.session_state.get("outbound_order_date") or date.today()
    try:
        return value.strftime("%Y-%m-%d")
    except Exception:
        return str(value)[:10]


def _set_outbound_order_date(order_id):
    if not order_id:
        return
    outbound_date = _selected_outbound_date_text()
    with connect() as con:
        con.execute("UPDATE outbound_orders SET order_date=? WHERE id=?", (outbound_date, int(order_id)))
        con.commit()


def page_outbound():
    original_renderer = outbound_page._render_last_sale_importer
    original_text_input = st.text_input
    original_checkbox = st.checkbox
    original_data_editor = st.data_editor
    original_manual_pick_rows = outbound_page._manual_pick_rows
    original_save_outbound_order = outbound_page.save_outbound_order
    original_update_outbound_order = outbound_page.update_outbound_order

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

    checkbox_skip_values = {}

    def patched_save_outbound_order(cart, title='', memo=''):
        order_id = original_save_outbound_order(cart, title, memo)
        _set_outbound_order_date(order_id)
        return order_id

    def patched_update_outbound_order(order_id, title_or_cart, maybe_cart=None):
        result = original_update_outbound_order(order_id, title_or_cart, maybe_cart)
        _set_outbound_order_date(order_id)
        return result

    def patched_text_input(label, *args, **kwargs):
        if kwargs.get("key") == "out_customer_term":
            st.date_input("출고일자", value=_default_outbound_date(), key="outbound_order_date")
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
    outbound_page.save_outbound_order = patched_save_outbound_order
    outbound_page.update_outbound_order = patched_update_outbound_order
    st.text_input = patched_text_input
    st.checkbox = patched_checkbox
    st.data_editor = patched_data_editor
    try:
        return outbound_page.page_outbound()
    finally:
        outbound_page._render_last_sale_importer = original_renderer
        outbound_page._manual_pick_rows = original_manual_pick_rows
        outbound_page.save_outbound_order = original_save_outbound_order
        outbound_page.update_outbound_order = original_update_outbound_order
        st.text_input = original_text_input
        st.checkbox = original_checkbox
        st.data_editor = original_data_editor
