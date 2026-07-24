from __future__ import annotations

import pandas as pd

import nohtus.pages.mobile_stock as mobile_stock
from nohtus.pages.mobile_stock_layout_patch_v3 import page_mobile_stock_finder as _page_mobile_stock_finder


_MATERIAL_OR_PROMO_PREFIXES = ("G1", "G2")


def _normalized_location(value):
    return str(value or "").strip().upper().replace(" ", "").replace("-", "").replace("_", "")


def _is_material_or_promo_location(value):
    location = _normalized_location(value)
    return location.startswith(_MATERIAL_OR_PROMO_PREFIXES) or "홍보물랙" in location


def _exclude_material_or_promo_rows(df):
    if not isinstance(df, pd.DataFrame) or df.empty or "location" not in df.columns:
        return df
    return df.loc[~df["location"].apply(_is_material_or_promo_location)].copy()


def page_mobile_stock_finder():
    """모바일 재고 화면에서는 G1/G2 및 홍보물랙 재고를 항상 제외한다."""
    original_stock_rows = mobile_stock.mobile_stock_rows
    original_candidates = mobile_stock.mobile_product_candidates
    original_expiry_inventory = mobile_stock._expiry_inventory
    original_favorites = mobile_stock.mobile_favorites_for_user

    def filtered_stock_rows(product_name, company_filter="전체", expiry_filter="전체"):
        rows = original_stock_rows(product_name, company_filter, expiry_filter)
        return _exclude_material_or_promo_rows(rows)

    def has_visible_stock(product_name):
        rows = original_stock_rows(product_name)
        rows = _exclude_material_or_promo_rows(rows)
        return isinstance(rows, pd.DataFrame) and not rows.empty

    def filtered_candidates(term="", limit=30):
        # 부자재/홍보물 위치에만 재고가 있는 제품은 검색 카드 자체를 만들지 않는다.
        candidates = original_candidates(term, limit=max(int(limit or 0) * 5, 100))
        visible = [name for name in candidates if has_visible_stock(name)]
        return visible[:limit]

    def filtered_expiry_inventory(days_limit=365):
        return _exclude_material_or_promo_rows(original_expiry_inventory(days_limit))

    def filtered_favorites(username):
        favorites = original_favorites(username)
        if not isinstance(favorites, pd.DataFrame) or favorites.empty or "product_name" not in favorites.columns:
            return favorites
        keep = favorites["product_name"].astype(str).apply(has_visible_stock)
        return favorites.loc[keep].copy()

    mobile_stock.mobile_stock_rows = filtered_stock_rows
    mobile_stock.mobile_product_candidates = filtered_candidates
    mobile_stock._expiry_inventory = filtered_expiry_inventory
    mobile_stock.mobile_favorites_for_user = filtered_favorites
    try:
        recent = mobile_stock.st.session_state.get("mobile_recent_searches", [])
        if recent:
            mobile_stock.st.session_state["mobile_recent_searches"] = [
                name for name in recent if has_visible_stock(name)
            ]
        return _page_mobile_stock_finder()
    finally:
        mobile_stock.mobile_stock_rows = original_stock_rows
        mobile_stock.mobile_product_candidates = original_candidates
        mobile_stock._expiry_inventory = original_expiry_inventory
        mobile_stock.mobile_favorites_for_user = original_favorites
