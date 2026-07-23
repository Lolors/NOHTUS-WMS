from datetime import date, datetime

import pandas as pd
import streamlit as st

import nohtus.pages.outbound as outbound_page
from nohtus.db import connect


_ALL_COMPANY_MANUAL_PICK_KEY = "out_all_company_manual_pick"
_SHIPPABLE_COL = "is_shippable"
_DIRECT_CUSTOMER_INLINE_KEY = "out_customer_direct_inline"


def _hide_last_sale_importer():
    return None


def _ensure_inventory_shippable_column():
    with connect() as con:
        cur = con.cursor()
        cols = {r[1] for r in cur.execute("PRAGMA table_info(inventory)").fetchall()}
        if _SHIPPABLE_COL not in cols:
            cur.execute(f"ALTER TABLE inventory ADD COLUMN {_SHIPPABLE_COL} INTEGER NOT NULL DEFAULT 1")
        con.commit()


def _outbound_order_exists(order_id):
    try:
        oid = int(order_id)
    except Exception:
        return False
    with connect() as con:
        row = con.execute("SELECT id FROM outbound_orders WHERE id=?", (oid,)).fetchone()
    return row is not None


def _default_outbound_date():
    if "outbound_order_date" in st.session_state:
        return st.session_state["outbound_order_date"]
    order_id = st.session_state.get("editing_order_id")
    if order_id:
        try:
            with connect() as con:
                row = con.execute("SELECT order_date FROM outbound_orders WHERE id=?", (int(order_id),)).fetchone()
            value = str(row[0] if row else "").strip()
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


def _upsert_wms_last_sale(customer_payload, order_date):
    customer_name = str((customer_payload or {}).get("customer_name") or "").strip()
    company = str((customer_payload or {}).get("company") or "").strip()
    order_date = str(order_date or "").strip()
    if not customer_name or not order_date:
        return
    now = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    outbound_page._ensure_customer_last_sales_table()
    with connect() as con:
        cur = con.cursor()
        old = cur.execute(
            "SELECT id, last_sale_date FROM customer_last_sales WHERE customer_name=? AND company=?",
            (customer_name, company),
        ).fetchone()
        if old:
            old_date = str(old[1] or "")
            final_date = max(old_date, order_date) if old_date else order_date
            cur.execute(
                """
                UPDATE customer_last_sales
                SET last_sale_date=?, source_company=?, updated_at=?
                WHERE id=?
                """,
                (final_date, company or "WMS", now, int(old[0])),
            )
        else:
            cur.execute(
                """
                INSERT INTO customer_last_sales(customer_name, company, last_sale_date, source_company, updated_at)
                VALUES(?,?,?,?,?)
                """,
                (customer_name, company, order_date, company or "WMS", now),
            )
        con.commit()


def page_outbound():
    original_renderer = outbound_page._render_last_sale_importer
    original_save_with_customer = outbound_page._save_outbound_cart_with_customer
    original_inventory_query = outbound_page._inventory_query_for_outbound
    original_text_input = st.text_input
    original_checkbox = st.checkbox
    original_data_editor = st.data_editor
    original_markdown = st.markdown
    original_caption = st.caption
    original_manual_pick_rows = outbound_page._manual_pick_rows

    st.markdown(
        """
        <style>
        div[data-testid="stCheckbox"] label, div[data-testid="stCheckbox"] p {
            white-space: nowrap !important;
        }
        div[data-testid="stDateInput"] {
            width: 118px !important;
            min-width: 118px !important;
            max-width: 118px !important;
        }
        div[data-testid="stDateInput"] input {
            width: 118px !important;
            min-width: 118px !important;
            max-width: 118px !important;
            padding-left: 8px !important;
            padding-right: 8px !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    checkbox_skip_values = {}
    manual_pick_option_rendered = False
    outbound_date_rendered = False
    direct_customer_inline_rendered = False

    def all_company_manual_pick_value():
        return bool(st.session_state.get(_ALL_COMPANY_MANUAL_PICK_KEY, False))

    def patched_inventory_query(selected_product, selected_company, ignore_company=False):
        _ensure_inventory_shippable_column()
        stock_df = original_inventory_query(selected_product, selected_company, ignore_company=ignore_company)
        if stock_df is None or stock_df.empty or _SHIPPABLE_COL not in stock_df.columns:
            return stock_df
        return stock_df[stock_df[_SHIPPABLE_COL].fillna(1).astype(int) == 1].copy()

    def patched_save_outbound_cart_with_customer(cart, title, customer_payload):
        outbound_page._ensure_outbound_customer_columns()
        editing_id = st.session_state.get("editing_order_id")
        order_date = _selected_outbound_date_text()
        if editing_id and _outbound_order_exists(editing_id):
            outbound_page.update_outbound_order(int(editing_id), title, cart)
            outbound_page._save_outbound_customer(int(editing_id), customer_payload)
            _set_outbound_order_date(int(editing_id))
            msg = f"출고지시서 #{int(editing_id)} 수정 저장 완료"
            st.session_state.pop("editing_order_id", None)
            st.session_state.pop("editing_order_title", None)
        else:
            if editing_id:
                st.session_state.pop("editing_order_id", None)
                st.session_state.pop("editing_order_title", None)
                prefix = f"수정 대상 출고지시서 #{editing_id}를 찾을 수 없어 새 출고지시서로 저장했습니다."
            else:
                prefix = ""
            oid = outbound_page.save_outbound_order(cart, title)
            outbound_page._save_outbound_customer(int(oid), customer_payload)
            _set_outbound_order_date(int(oid))
            msg = f"{prefix} 출고지시서 #{int(oid)} 저장 완료".strip()
        _upsert_wms_last_sale(customer_payload, order_date)

        for k in [
            "outbound_cart",
            "outbound_order_date",
            "out_customer_term",
            "out_customer_select",
            "_out_customer_label",
            "out_selected_customer",
            "out_customer_direct",
            _DIRECT_CUSTOMER_INLINE_KEY,
            "out_customer_manual_name",
            "out_product_term",
            "out_req_qty",
            "out_rec_editor",
            "out_manual_editor",
            "out_ignore_company",
            "out_manual_pick",
            _ALL_COMPANY_MANUAL_PICK_KEY,
            "out_expiry_short_first",
            "pending_outbound_save",
            "pending_outbound_expiry_warnings",
            "pending_outbound_add_rows",
            "pending_outbound_add_warnings",
        ]:
            st.session_state.pop(k, None)
        st.session_state["outbound_cart"] = []
        st.session_state["out_cart_editor_token"] = int(st.session_state.get("out_cart_editor_token", 0) or 0) + 1
        st.session_state["_outbound_reset_inputs_pending"] = True
        st.session_state["_outbound_last_success"] = msg
        st.rerun()

    def patched_markdown(body, *args, **kwargs):
        nonlocal manual_pick_option_rendered, outbound_date_rendered
        if isinstance(body, str) and body.strip() == "### 재고 선택 옵션":
            return None
        if isinstance(body, str) and body.strip() == "### 매출처" and not outbound_date_rendered:
            outbound_date_rendered = True
            st.date_input("출고일자", value=_default_outbound_date(), key="outbound_order_date")
        result = original_markdown(body, *args, **kwargs)
        if isinstance(body, str) and body.strip() == "### 제품 선택" and not manual_pick_option_rendered:
            manual_pick_option_rendered = True
            value = original_checkbox(
                "사업장 구분 없이 특정 재고 선택",
                value=all_company_manual_pick_value(),
                key=_ALL_COMPANY_MANUAL_PICK_KEY,
            )
            checkbox_skip_values["out_ignore_company"] = bool(value)
            checkbox_skip_values["out_manual_pick"] = bool(value)
        return result

    def patched_caption(body, *args, **kwargs):
        if isinstance(body, str) and (
            "매출처 사업장과 관계없이" in body
            or "유통기한 우선 추천 없이" in body
            or "추천 범위: 전체 사업장 재고" in body
        ):
            return None
        return original_caption(body, *args, **kwargs)

    def patched_text_input(label, *args, **kwargs):
        nonlocal direct_customer_inline_rendered
        if kwargs.get("key") == "out_customer_term":
            search_col, direct_col = st.columns([8, 2], gap="small")
            with search_col:
                value = original_text_input(label, *args, **kwargs)
            with direct_col:
                st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
                if not direct_customer_inline_rendered:
                    direct_customer_inline_rendered = True
                    direct_value = original_checkbox(
                        "직접입력",
                        value=bool(st.session_state.get("out_customer_direct", False)),
                        key=_DIRECT_CUSTOMER_INLINE_KEY,
                    )
                else:
                    direct_value = bool(
                        st.session_state.get(
                            _DIRECT_CUSTOMER_INLINE_KEY,
                            st.session_state.get("out_customer_direct", False),
                        )
                    )
            st.session_state["out_customer_direct"] = bool(direct_value)
            checkbox_skip_values["out_customer_direct"] = bool(direct_value)
            return value
        return original_text_input(label, *args, **kwargs)

    def patched_checkbox(label, *args, **kwargs):
        key = kwargs.get("key")
        if key == "out_customer_direct":
            value = bool(
                st.session_state.get(
                    _DIRECT_CUSTOMER_INLINE_KEY,
                    st.session_state.get("out_customer_direct", kwargs.get("value", False)),
                )
            )
            st.session_state["out_customer_direct"] = value
            checkbox_skip_values["out_customer_direct"] = value
            return value
        if key in checkbox_skip_values:
            return checkbox_skip_values[key]
        if key in ["out_ignore_company", "out_manual_pick"]:
            return all_company_manual_pick_value()
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

    outbound_page._render_last_sale_importer = _hide_last_sale_importer
    outbound_page._save_outbound_cart_with_customer = patched_save_outbound_cart_with_customer
    outbound_page._inventory_query_for_outbound = patched_inventory_query
    outbound_page._manual_pick_rows = original_manual_pick_rows
    st.markdown = patched_markdown
    st.caption = patched_caption
    st.text_input = patched_text_input
    st.checkbox = patched_checkbox
    st.data_editor = patched_data_editor
    try:
        return outbound_page.page_outbound()
    finally:
        outbound_page._render_last_sale_importer = original_renderer
        outbound_page._save_outbound_cart_with_customer = original_save_with_customer
        outbound_page._inventory_query_for_outbound = original_inventory_query
        outbound_page._manual_pick_rows = original_manual_pick_rows
        st.markdown = original_markdown
        st.caption = original_caption
        st.text_input = original_text_input
        st.checkbox = original_checkbox
        st.data_editor = original_data_editor
