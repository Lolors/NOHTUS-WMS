"""Outbound Cart service functions for NOHTUS WMS.

Migrated from app.py. Keep functions independent from Streamlit whenever possible.
"""

from __future__ import annotations

import calendar
import json
import re
import sqlite3
from datetime import date, datetime
from html import escape
from io import BytesIO
from urllib.parse import quote

import pandas as pd
import streamlit as st

from nohtus.config import AREA_COLOR, AREA_CONFIG, COMPANIES, INBOUND_COMPANIES, SPECIAL_LOCATIONS
from nohtus.db import connect, exec_sql, q
from nohtus.dates import display_date_only, expiry_status, normalize_exp_date
from nohtus.locations import location_picking_key, make_location, parse_location


def get_cart():
    """출고지시 장바구니를 안전하게 반환한다.
    리팩토링 중 함수 누락으로 page_outbound가 깨지는 것을 막기 위해 app.py 내부에 유지한다.
    """
    cart = st.session_state.get("outbound_cart")
    if not isinstance(cart, list):
        st.session_state["outbound_cart"] = []
    return st.session_state["outbound_cart"]

def _add_rows_to_outbound_cart(rows):
    """추천 행을 출고지시 장바구니에 추가한다.
    같은 로케이션/사업장/제품/LOT/유통기한이면 수량을 합산한다.
    """
    cart = get_cart()
    added = 0
    for row in rows or []:
        qty2 = int(row.get("요청수량", 0) or 0)
        if qty2 <= 0:
            continue
        key = (row.get("로케이션"), row.get("사업장"), row.get("제품명"), row.get("LOT"), row.get("유통기한"))
        merged = False
        for existing in cart:
            ekey = (existing.get("로케이션"), existing.get("사업장"), existing.get("제품명"), existing.get("LOT"), existing.get("유통기한"))
            if ekey == key:
                existing["요청수량"] = int(existing.get("요청수량", 0) or 0) + qty2
                merged = True
                break
        if not merged:
            cart.append({
                "id": int(row.get("id")),
                "로케이션": row.get("로케이션", ""),
                "사업장": row.get("사업장", ""),
                "제품명": row.get("제품명", ""),
                "LOT": row.get("LOT", "-"),
                "유통기한": row.get("유통기한", "-"),
                "요청수량": qty2,
            })
        added += 1
    return added

def _cart_expiry_warnings(cart):
    """출고지시 장바구니 투입 전 유통기한 경고 목록을 만든다. 만료 또는 30일 미만 남은 품목."""
    warnings = []
    today = date.today()
    for item in cart or []:
        exp = display_date_only(item.get("유통기한"))
        if not exp or exp == "-":
            continue
        try:
            d = datetime.strptime(exp, "%Y-%m-%d").date()
        except Exception:
            continue
        days = (d - today).days
        if days < 0:
            status = "유통기한 만료"
        elif days < 30:
            status = f"유통기한 {days}일 남음"
        else:
            continue
        warnings.append({
            "제품명": item.get("제품명", "-"),
            "LOT": item.get("LOT", "-"),
            "유통기한": exp,
            "수량": item.get("요청수량", ""),
            "상태": status,
        })
    return warnings

def _clear_outbound_inputs_before_render():
    """출고지시 저장/수정 완료 후 다음 렌더에서 입력 위젯 값을 초기화한다.
    Streamlit widget key를 생성된 뒤 직접 수정하지 않기 위해 page_outbound 시작부에서만 실행한다.
    """
    if not st.session_state.pop("_outbound_reset_inputs_pending", False):
        return
    for k in [
        "out_customer_term", "out_customer_select", "out_selected_customer",
        "out_product_term", "out_req_qty", "out_rec_editor",
        "outbound_cart", "editing_order_id", "editing_order_title",
        "pending_outbound_save", "pending_outbound_expiry_warnings",
    ]:
        st.session_state.pop(k, None)
    st.session_state["out_cart_editor_token"] = int(st.session_state.get("out_cart_editor_token", 0) or 0) + 1
