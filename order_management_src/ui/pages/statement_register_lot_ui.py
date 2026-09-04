"""거래명세서 LOT 분할 입력 UI 보정 레이어."""
from __future__ import annotations

import inspect

import pandas as pd

from ui.pages import statement_register_substitution as base


def item_key(row) -> tuple:
    """대체입고는 실제 입고품이 아니라 원발주품목 기준으로 집계합니다."""
    original_code = str(row.get("원발주제품코드", "") or "").strip()
    original_name = str(row.get("원발주제품명", "") or "").strip()
    original_spec = str(row.get("원발주규격", "") or "").strip()
    original_unit = str(row.get("원발주단위", "") or "").strip()

    if original_code:
        return ("CODE", original_code)
    if original_name or original_spec or original_unit:
        return ("TEXT", original_name, original_spec, original_unit)

    code = str(row.get("제품코드", "") or "").strip()
    if code:
        return ("CODE", code)
    return (
        "TEXT",
        str(row.get("정식제품명", row.get("제품명", "")) or "").strip(),
        str(row.get("규격", "") or "").strip(),
        str(row.get("단위", row.get("포장단위", "")) or "").strip(),
    )


def _price_text(value) -> str:
    """매입단가는 화면에서 공란을 유지하고 입력한 숫자 문자열을 그대로 보존합니다."""
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in {"nan", "none"}:
        return ""
    if text in {"0", "0.0"}:
        return ""
    return text


def _sync_receipt_rows(st, purchase_module, selected_order, selected_lookup, substitution_state):
    rows = base._receipt_rows_state(st, selected_order)
    selected_item_nos = set(selected_lookup)
    rows = [dict(row) for row in rows if str(row.get("품목번호", "")) in selected_item_nos]

    existing_item_nos = {str(row.get("품목번호", "")) for row in rows}
    for item_no, original in selected_lookup.items():
        if item_no not in existing_item_nos:
            rows.append({
                "행번호": base._next_receipt_row_id(st, selected_order),
                "품목번호": int(item_no),
                "입고수량": base._to_int(purchase_module, original.get("남은수량", 0)),
                "매입단가": "",
                "제조번호": "",
                "유통기한": "",
                "현재 가격 적용": True,
            })

    for row in rows:
        item_no = str(row.get("품목번호", ""))
        original = selected_lookup.get(item_no)
        if original is None:
            continue
        actual = base._actual_for_item(original, substitution_state.get(item_no))
        row["제품명"] = str(actual.get("정식제품명", "") or original.get("제품명", ""))
        row["규격"] = str(actual.get("규격", "") or original.get("규격", ""))
        row["복사/삭제"] = False
        row["입고수량"] = base._to_int(purchase_module, row.get("입고수량", 0))
        row["매입단가"] = _price_text(row.get("매입단가", ""))
        row["제조번호"] = str(row.get("제조번호", "") or "")
        row["유통기한"] = str(row.get("유통기한", "") or "")
        row["현재 가격 적용"] = base._normalise_bool(row.get("현재 가격 적용", True))

    st.session_state[f"statement_receipt_rows_{selected_order}"] = rows
    return rows


def _store_entered_rows(st, selected_order: str, entered: pd.DataFrame) -> list[dict]:
    rows = []
    if entered is not None and not entered.empty:
        for _, row in entered.iterrows():
            rows.append({
                "행번호": int(row.get("행번호", 0)),
                "품목번호": int(row.get("품목번호", 0)),
                "입고수량": int(float(row.get("입고수량", 0) or 0)),
                "매입단가": _price_text(row.get("매입단가", "")),
                "제조번호": str(row.get("제조번호", "") or "").strip(),
                "유통기한": str(row.get("유통기한", "") or "").strip(),
                "현재 가격 적용": base._normalise_bool(row.get("현재 가격 적용", True)),
            })
    st.session_state[f"statement_receipt_rows_{selected_order}"] = rows
    return rows


base.item_key = item_key
base._sync_receipt_rows = _sync_receipt_rows
base._store_entered_rows = _store_entered_rows


_render_source = inspect.getsource(base.render)
_render_source = _render_source.replace(
    '"매입단가": _to_int(purchase_module, row.get("매입단가", 0)),',
    '"매입단가": _price_text(row.get("매입단가", "")),',
)
_render_source = _render_source.replace(
    '"매입단가": st.column_config.NumberColumn("매입단가", min_value=0, step=100, width="small"),',
    '"매입단가": st.column_config.TextColumn("매입단가", width="small", help="숫자만 입력하세요."),',
)
_render_source = _render_source.replace(
    '''            for row in list(stored_rows):
                if int(row.get("행번호", 0)) not in selected_row_ids:
                    continue
                copied = dict(row)
                copied["행번호"] = _next_receipt_row_id(st, selected_order)
                copied["입고수량"] = 0
                copied["제조번호"] = ""
                copied["유통기한"] = ""
                stored_rows.append(copied)''',
    '''            next_rows = []
            for row in stored_rows:
                next_rows.append(row)
                if int(row.get("행번호", 0)) not in selected_row_ids:
                    continue
                copied = dict(row)
                copied["행번호"] = _next_receipt_row_id(st, selected_order)
                copied["입고수량"] = 0
                copied["제조번호"] = ""
                copied["유통기한"] = ""
                next_rows.append(copied)
            stored_rows = next_rows''',
)

_namespace = dict(base.__dict__)
_namespace["_price_text"] = _price_text
_namespace["item_key"] = item_key
exec(_render_source, _namespace)
render = _namespace["render"]
