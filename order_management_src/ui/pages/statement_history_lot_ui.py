"""거래명세서 내역에 제조번호·유통기한과 대체입고 정보를 표시하는 보정 레이어."""
from __future__ import annotations

import pandas as pd

from ui.pages import statement_history as base
from ui.style_utils import map_cells


def _statement_display_table(items: pd.DataFrame, purchase_module):
    rows = items.copy().fillna("")
    for col in [
        "정식제품명", "규격", "제조번호", "유통기한", "입고수량", "단위", "포장단위",
        "매입단가", "출고단가", "상품금액", "가격적용여부", "입고유형", "원발주제품명",
    ]:
        if col not in rows.columns:
            rows[col] = ""

    display_rows = []
    for _, row in rows.iterrows():
        returned, original_quantity, original_amount = base._return_info(row.get("가격적용여부", ""))
        quantity = original_quantity if returned else base._to_int(purchase_module, row.get("입고수량", 0))
        amount = -original_amount if returned else base._to_int(purchase_module, row.get("상품금액", 0))
        purchase_price = base._to_int(purchase_module, row.get("매입단가", 0))
        sale_price = base._to_int(purchase_module, row.get("출고단가", 0)) or int(round(purchase_price * 1.3))
        is_substitution = str(row.get("입고유형", "") or "").strip() == "대체입고"
        actual_name = str(row.get("정식제품명", "") or "")
        original_name = str(row.get("원발주제품명", "") or "") if is_substitution else ""
        product_name = f"{actual_name} (대체: {original_name})" if original_name else actual_name

        display_rows.append({
            "상태": "반품" if returned else "입고",
            "제품명": product_name,
            "수량": quantity,
            "제조번호": str(row.get("제조번호", "")),
            "유통기한": str(row.get("유통기한", "")),
            "매입단가": f"{purchase_price:,}원",
            "매출단가": f"{sale_price:,}원",
            "매입총액": f"{amount:,}원",
            "규격": str(row.get("규격", "")),
            "포장단위": str(row.get("포장단위", "") or row.get("단위", "")),
        })

    display = pd.DataFrame(display_rows)
    display.insert(0, "No.", range(1, len(display) + 1))

    def style_status(value):
        if str(value) == "반품":
            return "background-color: #fee2e2; color: #991b1b; font-weight: 700;"
        return ""

    styler = display.style.set_properties(
        subset=["매출단가"],
        **{"background-color": "#f3f4f6", "color": "#4b5563"},
    )
    return map_cells(styler, style_status, subset=["상태"])


base._statement_display_table = _statement_display_table
render = base.render
