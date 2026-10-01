"""모바일 전용 API가 사용하는, Streamlit에 의존하지 않는 순수 조회 함수 모음.

부자재/홍보물 제외, 수출대기 로케이션 판정, 유통기한 구간, 창고 필터
같은 규칙은 `nohtus/services/stock_rules.py` 등 공용 모듈에서 가져온다 —
데스크톱 페이지도 같은 곳을 본다.
"""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path

import pandas as pd

from nohtus.db import q
from nohtus.locations import expand_row_range
from nohtus.services.expiry_rules import PERIOD_DAYS as EXPIRY_PERIOD_DAYS
from nohtus.services.expiry_rules import expiry_badge_for as _expiry_badge_for
from nohtus.services.product_images import ensure_thumbnail as _ensure_thumbnail
from nohtus.services.product_images import get_product_image_path
from nohtus.services.stock_rules import BIDATA_COMPANY
from nohtus.services.stock_rules import (
    exclude_material_or_promo_rows as _exclude_material_or_promo_rows,
)
from nohtus.services.stock_rules import is_export_waiting_location
from nohtus.services.warehouse_rules import apply_warehouse_filter as _apply_warehouse_filter


def _material_product_names():
    """제품마스터에서 부자재로 등록된(is_material=1) 표준제품명 집합."""
    df = q("SELECT standard_name FROM products WHERE COALESCE(is_material, 0) = 1")
    if df.empty:
        return set()
    return set(df["standard_name"].dropna().astype(str))


def product_candidates(term, limit=20):
    term = (term or "").strip().lower()
    if not term:
        return []
    df = q(
        """
        SELECT standard_name, aliases
        FROM products
        WHERE COALESCE(standard_name, '') <> ''
        ORDER BY standard_name, id
        """
    )
    if df.empty:
        return []

    def matches(row):
        standard_name = str(row.get("standard_name", "") or "").lower()
        aliases = str(row.get("aliases", "") or "").lower()
        return term in standard_name or term in aliases

    df = df[df.apply(matches, axis=1)].copy()
    if df.empty:
        return []
    df["_starts"] = df["standard_name"].astype(str).str.lower().str.startswith(term)
    df = df.sort_values(["_starts", "standard_name"], ascending=[False, True])
    return df["standard_name"].dropna().astype(str).drop_duplicates().head(limit).tolist()


def stock_rows(product_name, exclude_material_or_promo=True):
    product_name = (product_name or "").strip()
    if not product_name:
        return pd.DataFrame()
    if exclude_material_or_promo and product_name in _material_product_names():
        return pd.DataFrame()
    df = q(
        """
        SELECT company, location, lot, exp_date, qty, location_range_end, location_range_cells
        FROM inventory
        WHERE product_name=? AND qty>0
        ORDER BY company, exp_date, location, lot
        """,
        (product_name,),
    )
    return df


def has_visible_stock(product_name):
    rows = stock_rows(product_name)
    return isinstance(rows, pd.DataFrame) and not rows.empty


def stock_summary(rows):
    total_qty = int(rows["qty"].sum()) if not rows.empty else 0
    company_totals = rows.groupby("company")["qty"].sum() if not rows.empty else pd.Series(dtype=float)
    summary = " · ".join(
        f"{company} {int(qty):,}" for company, qty in company_totals.items() if int(qty or 0) > 0
    )
    return total_qty, summary


def search_products(term, limit=20, exclude_material=True):
    """검색어에 매칭되고 실제로 노출 가능한 재고가 있는 제품만 반환."""
    candidates = product_candidates(term, limit=max(limit * 5, 100))
    material_names = _material_product_names()
    results = []
    for name in candidates:
        rows = stock_rows(name, exclude_material_or_promo=exclude_material)
        if rows.empty:
            continue
        total_qty, summary = stock_summary(rows)
        results.append(
            {
                "name": name,
                "total_qty": total_qty,
                "summary": summary,
                "is_material": name in material_names,
                "thumbnail": thumbnail_data_uri(name),
            }
        )
        if len(results) >= limit:
            break
    return results


def stock_detail(product_name):
    """특정 제품을 이미 선택해 들어온 상세 화면이므로 부자재 여부와 상관없이
    실제 재고를 그대로 보여준다 (목록 검색 단계의 '부자재 제외'와는 별개)."""
    rows = stock_rows(product_name, exclude_material_or_promo=False)
    is_material = product_name in _material_product_names()
    total_qty, summary = stock_summary(rows)
    location_rows = []
    if not rows.empty:
        detail = rows.sort_values(["exp_date", "company", "location", "lot"])
        for row in detail.itertuples(index=False):
            location = str(row.location or "")
            occupied_cells = expand_row_range(location, row.location_range_cells, row.location_range_end)
            location_rows.append(
                {
                    "company": str(row.company or ""),
                    "location": location,
                    "occupied_cells": occupied_cells,
                    "lot": str(row.lot or ""),
                    "exp_date": str(row.exp_date or ""),
                    "qty": int(row.qty or 0),
                }
            )
    return {
        "name": product_name,
        "total_qty": total_qty,
        "summary": summary,
        "is_material": is_material,
        "thumbnail": thumbnail_data_uri(product_name),
        "rows": location_rows,
    }


def expiry_inventory(period="1y", bidata_scope="data", warehouse="all"):
    days_limit = EXPIRY_PERIOD_DAYS.get(period, 365)
    df = q(
        """
        SELECT product_name, company, location, lot, exp_date, qty
        FROM inventory
        WHERE qty > 0 AND COALESCE(product_name, '') <> ''
        ORDER BY exp_date, product_name, location, lot
        """
    )
    if df.empty:
        return df
    today = pd.Timestamp.today().normalize()
    df["_expiry"] = pd.to_datetime(df["exp_date"], errors="coerce").dt.normalize()
    df = df[df["_expiry"].notna()].copy()
    df["days_left"] = (df["_expiry"] - today).dt.days
    df = df[(df["days_left"] >= 0) & (df["days_left"] <= days_limit)]
    df = _exclude_material_or_promo_rows(df)
    if not df.empty:
        is_bidata = df["company"].astype(str).str.strip() == BIDATA_COMPANY
        df = df[is_bidata] if bidata_scope == "bidata" else df[~is_bidata]
    df = _apply_warehouse_filter(df, warehouse)
    return df


def search_expiry(term, period="1y", bidata_scope="data", warehouse="all", limit=100):
    df = expiry_inventory(period=period, bidata_scope=bidata_scope, warehouse=warehouse)
    if df.empty:
        return []
    available_names = df["product_name"].dropna().astype(str).drop_duplicates().tolist()
    if not term or not term.strip():
        candidates = available_names
    else:
        matched = product_candidates(term, limit=100)
        available_set = set(available_names)
        candidates = [name for name in matched if name in available_set]

    # 데스크톱과 같이 로트별 유통기한 구간(빨강/노랑/파랑)으로 나눠서 보여준다.
    df = df.assign(_level=df["_expiry"].apply(lambda ts: _expiry_badge_for(ts)["level"]))
    results = []
    for name in candidates:
        name_rows = df[df["product_name"].astype(str) == str(name)]
        for (level, expiry), rows in name_rows.groupby(["_level", "_expiry"]):
            total_qty, summary = stock_summary(rows)
            nearest = rows["_expiry"].min()
            badge = _expiry_badge_for(nearest)
            is_waiting = rows["location"].apply(is_export_waiting_location)
            export_waiting_qty = int(rows.loc[is_waiting, "qty"].sum())
            results.append(
                {
                    "name": name,
                    "level": level,
                    "exp_date": expiry.strftime("%Y-%m-%d"),
                    "total_qty": total_qty,
                    "summary": summary,
                    "badge": badge,
                    "export_waiting": export_waiting_qty > 0,
                    "export_waiting_qty": export_waiting_qty,
                    "thumbnail": thumbnail_data_uri(name),
                    "_sort_key": nearest,
                }
            )
    results.sort(key=lambda item: (item["_sort_key"], item["name"]))
    for item in results:
        item.pop("_sort_key", None)
    return results[:limit]


def expiry_detail(product_name, period="1y", bidata_scope="data", warehouse="all", level="", exp_date=""):
    df = expiry_inventory(period=period, bidata_scope=bidata_scope, warehouse=warehouse)
    if level and not df.empty:
        df = df[df["_expiry"].apply(lambda ts: _expiry_badge_for(ts)["level"]) == level]
    if exp_date and not df.empty:
        df = df[df["_expiry"].dt.strftime("%Y-%m-%d") == exp_date]
    rows = df[df["product_name"].astype(str) == str(product_name)] if not df.empty else df
    total_qty, summary = stock_summary(rows) if isinstance(rows, pd.DataFrame) else (0, "")
    location_rows = []
    if isinstance(rows, pd.DataFrame) and not rows.empty:
        detail = rows.sort_values(["_expiry", "company", "location", "lot"]).rename(columns={"_expiry": "expiry_dt"})
        for row in detail.itertuples(index=False):
            location_rows.append(
                {
                    "company": str(row.company or ""),
                    "location": str(row.location or ""),
                    "lot": str(row.lot or ""),
                    "exp_date": row.expiry_dt.strftime("%Y-%m-%d") if pd.notna(row.expiry_dt) else "",
                    "qty": int(row.qty or 0),
                    "export_waiting": is_export_waiting_location(row.location),
                }
            )
    return {
        "name": product_name,
        "total_qty": total_qty,
        "summary": summary,
        "thumbnail": thumbnail_data_uri(product_name),
        "rows": location_rows,
    }


def _image_data_uri(path_value):
    path = Path(str(path_value or ""))
    if not path.is_file():
        return ""
    try:
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    except OSError:
        return ""
    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    return f"data:{mime};base64,{encoded}"


def thumbnail_data_uri(product_name):
    """압축된 썸네일만 반환한다 — 원본으로 폴백하면 검색 결과에 원본 크기
    이미지가 그대로 base64로 실려 모바일 응답이 크게 느려진다."""
    original_path = get_product_image_path(product_name)
    if not original_path:
        return ""
    thumb = _ensure_thumbnail(original_path)
    return _image_data_uri(thumb) if thumb else ""
