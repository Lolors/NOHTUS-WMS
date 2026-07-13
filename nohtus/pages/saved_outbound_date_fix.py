from __future__ import annotations

from datetime import date

import streamlit as st

from nohtus.db import q
from nohtus.pages.saved_outbound_business_v4 import page_saved_outbound as _page_saved_outbound


def _extend_default_range_to_scheduled_orders():
    today = date.today()
    latest_df = q("""
        SELECT MAX(order_date) AS latest_date
        FROM outbound_orders
        WHERE IFNULL(status,'')<>'취소됨'
          AND TRIM(COALESCE(order_date,''))<>''
    """)
    if latest_df.empty:
        return
    latest_text = str(latest_df.iloc[0].get("latest_date") or "").strip()
    if not latest_text:
        return
    try:
        latest_date = date.fromisoformat(latest_text[:10])
    except Exception:
        return
    if latest_date <= today:
        return

    current_start = st.session_state.get("saved_start_date")
    current_end = st.session_state.get("saved_end_date")
    default_like = current_start in (None, today) and current_end in (None, today)
    if default_like:
        st.session_state["saved_start_date"] = today
        st.session_state["saved_end_date"] = latest_date


def page_saved_outbound():
    _extend_default_range_to_scheduled_orders()
    return _page_saved_outbound()
