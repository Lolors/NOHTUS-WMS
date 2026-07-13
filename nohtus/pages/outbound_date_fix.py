from __future__ import annotations

from datetime import date

import streamlit as st

import nohtus.pages.outbound as outbound_page
from nohtus.db import connect
from nohtus.pages.outbound_business import page_outbound as _page_outbound


def _selected_date_text():
    value = st.session_state.get("outbound_order_date") or date.today()
    try:
        return value.strftime("%Y-%m-%d")
    except Exception:
        return str(value)[:10]


def page_outbound():
    """신규 출고지시 저장 시 사용자가 선택한 출고일자를 즉시 확정한다."""
    original_save = outbound_page.save_outbound_order

    def patched_save(cart, title="", memo=""):
        order_id = original_save(cart, title, memo)
        with connect() as con:
            con.execute(
                "UPDATE outbound_orders SET order_date=? WHERE id=?",
                (_selected_date_text(), int(order_id)),
            )
            con.commit()
        return order_id

    outbound_page.save_outbound_order = patched_save
    try:
        return _page_outbound()
    finally:
        outbound_page.save_outbound_order = original_save
