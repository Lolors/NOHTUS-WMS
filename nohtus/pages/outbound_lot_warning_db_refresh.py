"""출고 경고에 표시할 유통기한을 현재 inventory DB 값으로 갱신한다."""

from __future__ import annotations

from nohtus.dates import display_date_only
from nohtus.db import q
from nohtus.pages import outbound_lot_warning


_original_warning_rows = outbound_lot_warning._warning_rows


def _current_expiry(row: dict) -> str:
    """장바구니에 저장된 과거 값보다 inventory의 현재 유통기한을 우선한다."""
    inventory_id = row.get("id")
    if inventory_id not in (None, ""):
        current = q("SELECT exp_date FROM inventory WHERE id=? LIMIT 1", (int(inventory_id),))
        if not current.empty:
            return display_date_only(current.iloc[0].get("exp_date"))

    product = str(row.get("제품명") or "").strip()
    lot = str(row.get("LOT") or "").strip()
    company = str(row.get("사업장") or "").strip()
    location = str(row.get("로케이션") or "").strip()
    if not product or not lot:
        return str(row.get("유통기한") or "").strip()

    current = q(
        """
        SELECT exp_date
        FROM inventory
        WHERE product_name=? AND lot=?
          AND (?='' OR company=?)
          AND (?='' OR location=?)
        ORDER BY id DESC
        LIMIT 1
        """,
        (product, lot, company, company, location, location),
    )
    if current.empty:
        return str(row.get("유통기한") or "").strip()
    return display_date_only(current.iloc[0].get("exp_date"))


def _warning_rows_with_current_expiry(rows):
    warning_rows = _original_warning_rows(rows)
    refreshed = []
    for row in warning_rows:
        current = dict(row)
        current["유통기한"] = _current_expiry(current)
        refreshed.append(current)
    return refreshed


outbound_lot_warning._warning_rows = _warning_rows_with_current_expiry
