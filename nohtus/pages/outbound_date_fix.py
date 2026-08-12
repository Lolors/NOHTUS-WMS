from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import streamlit as st

import nohtus.pages.outbound as outbound_page
import nohtus.pages.outbound_business as outbound_business


_BLOCKED_OUTBOUND_LOCATIONS = {"홍보물랙", "G1", "G2"}
_INVALID_RECENT_DATE_TEXTS = {"", "none", "nan", "nat", "null", "-"}


def _normalized_location(value):
    return str(value or "").strip().upper().replace(" ", "")


def _is_blocked_outbound_location(value):
    location = _normalized_location(value)
    if location in _BLOCKED_OUTBOUND_LOCATIONS:
        return True
    return location.startswith("P") or location.startswith("G1-") or location.startswith("G2-")


def _normalized_recent_date(value):
    text = str(value or "").strip()
    if text.casefold() in _INVALID_RECENT_DATE_TEXTS:
        return ""
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").strftime("%Y-%m-%d")
    except Exception:
        return ""


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


def _actual_recent_outbound_date(customer_name, company):
    """최근거래일 테이블이 비었거나 깨졌을 때 실제 출고지시 이력으로 보완한다."""
    customer = str(customer_name or "").strip()
    company = str(company or "").strip()
    if not customer or not company:
        return ""
    try:
        history = outbound_page._recent_outbound_history(customer, company, limit=1)
    except Exception:
        return ""
    if not history:
        return ""
    return _normalized_recent_date(history[0].get("order_date"))


def _resolved_last_sale_date(customer_name, company, exact_map, name_map):
    customer = str(customer_name or "").strip()
    company = str(company or "").strip()
    raw_date = exact_map.get((customer, company)) if company else name_map.get(customer)
    last_date = _normalized_recent_date(raw_date)
    if last_date:
        return last_date
    return _actual_recent_outbound_date(customer, company)


def _last_sale_text(customer_name, company, exact_map, name_map):
    last_date = _resolved_last_sale_date(customer_name, company, exact_map, name_map)
    if not last_date:
        return "최근거래 없음"

    ago = _days_ago_label(last_date)
    return f"최근거래 {last_date} ({ago})" if ago else f"최근거래 {last_date}"


def _customer_select_label(row, exact_map, name_map):
    customer = str(getattr(row, "customer_name", "") or "").strip()
    company = str(getattr(row, "company", "") or "").strip()
    last_date = _resolved_last_sale_date(customer, company, exact_map, name_map)
    if not last_date:
        last_sale = "최근거래 없음"
    else:
        ago = _days_ago_label(last_date)
        last_sale = f"최근거래 {last_date} ({ago})" if ago else f"최근거래 {last_date}"
    return f"{customer} | {company or '-'} | {last_sale}"


def page_outbound():
    """출고일자와 과거/현재 출고 화면 간 헬퍼 시그니처 차이를 보정한다."""
    original_last_sale_text = getattr(outbound_page, "_last_sale_text", None)
    original_customer_select_label = getattr(outbound_page, "_customer_select_label", None)
    original_days_ago_label = getattr(outbound_page, "_days_ago_label", None)
    original_customer_payload = getattr(outbound_page, "_current_customer_payload", None)
    original_inventory_query = outbound_page._inventory_query_for_outbound
    original_q = outbound_page.q
    original_title = st.title

    # outbound_business가 과거 수출대기용 text_input 패치를 원본으로 잘못 보관했을 수 있다.
    # 일반 출고 화면에서는 현재 Streamlit 원본 위젯을 사용해 매출처 검색창을 반드시 표시한다.
    previous_base_text_input = outbound_business._BASE_TEXT_INPUT
    previous_base_checkbox = outbound_business._BASE_CHECKBOX
    previous_base_data_editor = outbound_business._BASE_DATA_EDITOR
    previous_base_markdown = outbound_business._BASE_MARKDOWN
    previous_base_caption = outbound_business._BASE_CAPTION
    outbound_business._BASE_TEXT_INPUT = st.text_input
    outbound_business._BASE_CHECKBOX = st.checkbox
    outbound_business._BASE_DATA_EDITOR = st.data_editor
    outbound_business._BASE_MARKDOWN = st.markdown
    outbound_business._BASE_CAPTION = st.caption

    # 수출대기 화면을 다녀온 뒤 남은 화면 모드가 일반 출고 제목을 바꾸지 않게 한다.
    st.session_state.pop("_outbound_screen_mode", None)

    def patched_title(body, *args, **kwargs):
        if isinstance(body, str) and body.strip() in {"수출대기 등록", "수출대기 수정"}:
            body = "출고지시"
        return original_title(body, *args, **kwargs)

    def patched_customer_payload(selected_customer=None):
        if original_customer_payload is None:
            saved = st.session_state.get("out_selected_customer") or {}
            return {
                "customer_name": str(saved.get("customer_name") or "").strip(),
                "company": str(saved.get("company") or "").strip(),
            }
        try:
            return original_customer_payload(selected_customer)
        except TypeError:
            return original_customer_payload()

    def patched_inventory_query(selected_product, selected_company, ignore_company=False):
        rows = original_inventory_query(selected_product, selected_company, ignore_company=ignore_company)
        if rows is None or rows.empty or "location" not in rows.columns:
            return rows
        blocked = rows["location"].apply(_is_blocked_outbound_location)
        return rows.loc[~blocked].copy()

    def patched_q(sql, params=()):
        normalized = " ".join(str(sql or "").lower().split())
        if (
            "select coalesce(sum(qty),0) as qty from inventory" in normalized
            and "where product_name=? and qty>0" in normalized
        ):
            return original_q(
                """
                SELECT COALESCE(SUM(qty),0) AS qty
                FROM inventory
                WHERE product_name=? AND qty>0
                  AND REPLACE(UPPER(TRIM(COALESCE(location,''))), ' ', '') NOT LIKE 'P%'
                  AND REPLACE(UPPER(TRIM(COALESCE(location,''))), ' ', '') <> '홍보물랙'
                  AND REPLACE(UPPER(TRIM(COALESCE(location,''))), ' ', '') NOT IN ('G1','G2')
                  AND REPLACE(UPPER(TRIM(COALESCE(location,''))), ' ', '') NOT LIKE 'G1-%'
                  AND REPLACE(UPPER(TRIM(COALESCE(location,''))), ' ', '') NOT LIKE 'G2-%'
                """,
                params,
            )
        result = original_q(sql, params)
        if isinstance(result, pd.DataFrame) and "location" in result.columns:
            blocked = result["location"].apply(_is_blocked_outbound_location)
            return result.loc[~blocked].copy()
        return result

    outbound_page._last_sale_text = _last_sale_text
    outbound_page._customer_select_label = _customer_select_label
    outbound_page._days_ago_label = _days_ago_label
    outbound_page._current_customer_payload = patched_customer_payload
    outbound_page._inventory_query_for_outbound = patched_inventory_query
    outbound_page.q = patched_q
    st.title = patched_title
    try:
        return outbound_business.page_outbound()
    finally:
        outbound_page._inventory_query_for_outbound = original_inventory_query
        outbound_page.q = original_q
        st.title = original_title

        outbound_business._BASE_TEXT_INPUT = previous_base_text_input
        outbound_business._BASE_CHECKBOX = previous_base_checkbox
        outbound_business._BASE_DATA_EDITOR = previous_base_data_editor
        outbound_business._BASE_MARKDOWN = previous_base_markdown
        outbound_business._BASE_CAPTION = previous_base_caption

        if original_last_sale_text is None:
            try:
                delattr(outbound_page, "_last_sale_text")
            except AttributeError:
                pass
        else:
            outbound_page._last_sale_text = original_last_sale_text

        if original_customer_select_label is None:
            try:
                delattr(outbound_page, "_customer_select_label")
            except AttributeError:
                pass
        else:
            outbound_page._customer_select_label = original_customer_select_label

        if original_days_ago_label is None:
            try:
                delattr(outbound_page, "_days_ago_label")
            except AttributeError:
                pass
        else:
            outbound_page._days_ago_label = original_days_ago_label

        if original_customer_payload is None:
            try:
                delattr(outbound_page, "_current_customer_payload")
            except AttributeError:
                pass
        else:
            outbound_page._current_customer_payload = original_customer_payload
