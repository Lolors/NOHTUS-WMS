from __future__ import annotations

from datetime import date, datetime

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


def _days_ago_label(date_text):
    try:
        target_date = datetime.strptime(str(date_text), "%Y-%m-%d").date()
    except Exception:
        return ""

    days = (date.today() - target_date).days
    if days < 0:
        return "예정"
    if days == 0:
        return "오늘"
    return f"{days}일 전"


def _last_sale_text(customer_name, company, exact_map, name_map):
    customer = str(customer_name or "").strip()
    company = str(company or "").strip()
    last_date = exact_map.get((customer, company)) or name_map.get(customer) or ""
    if not last_date:
        return "최근거래 없음"

    ago = _days_ago_label(last_date)
    return f"최근거래 {last_date} ({ago})" if ago else f"최근거래 {last_date}"


def page_outbound():
    """신규 출고지시 저장일과 누락된 최근거래 표시 헬퍼를 보정한다."""
    original_save = outbound_page.save_outbound_order
    original_last_sale_text = getattr(outbound_page, "_last_sale_text", None)
    original_days_ago_label = getattr(outbound_page, "_days_ago_label", None)

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
    outbound_page._last_sale_text = _last_sale_text
    outbound_page._days_ago_label = _days_ago_label
    try:
        return _page_outbound()
    finally:
        outbound_page.save_outbound_order = original_save
        if original_last_sale_text is None:
            try:
                delattr(outbound_page, "_last_sale_text")
            except AttributeError:
                pass
        else:
            outbound_page._last_sale_text = original_last_sale_text

        if original_days_ago_label is None:
            try:
                delattr(outbound_page, "_days_ago_label")
            except AttributeError:
                pass
        else:
            outbound_page._days_ago_label = original_days_ago_label
