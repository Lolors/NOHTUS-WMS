"""모바일 전용 API가 사용하는, Streamlit에 의존하지 않는 순수 조회 함수 모음.

nohtus/pages/mobile_stock*.py에 있는 동일한 비즈니스 규칙(부자재/홍보물 제외,
수출대기 로케이션 판정, 유통기한 구간 필터)을 st.session_state 없이 그대로
재구현한다. 규칙이 바뀌면 두 곳 다 함께 고쳐야 한다는 점에 주의.
"""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path

import pandas as pd

from nohtus.db import q
from nohtus.services.location_map import get_product_image_path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_THUMB_DIR = _PROJECT_ROOT / "data" / "product_images" / "thumbs"

_MATERIAL_OR_PROMO_PREFIXES = ("G1", "G2")
_MATERIAL_OR_PROMO_KEYWORDS = ("부자재", "홍보물")

EXPIRY_PERIOD_DAYS = {"3m": 90, "6m": 180, "1y": 365}


def _normalized_location(value):
    return str(value or "").strip().upper().replace(" ", "").replace("-", "").replace("_", "")


def _is_material_or_promo_location(value):
    location = _normalized_location(value)
    return (
        location.startswith(_MATERIAL_OR_PROMO_PREFIXES)
        or any(keyword in location for keyword in _MATERIAL_OR_PROMO_KEYWORDS)
    )


def is_export_waiting_location(value):
    return _normalized_location(value).startswith("P")


def _material_product_names():
    """제품마스터에서 부자재로 등록된(is_material=1) 표준제품명 집합."""
    df = q("SELECT standard_name FROM products WHERE COALESCE(is_material, 0) = 1")
    if df.empty:
        return set()
    return set(df["standard_name"].dropna().astype(str))


def _exclude_material_or_promo_rows(df):
    if not isinstance(df, pd.DataFrame) or df.empty or "location" not in df.columns:
        return df
    return df.loc[~df["location"].apply(_is_material_or_promo_location)].copy()


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
    df = q(
        """
        SELECT company, location, lot, exp_date, qty
        FROM inventory
        WHERE product_name=? AND qty>0
        ORDER BY company, exp_date, location, lot
        """,
        (product_name,),
    )
    if exclude_material_or_promo:
        df = _exclude_material_or_promo_rows(df)
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
    if exclude_material:
        material_names = _material_product_names()
        candidates = [name for name in candidates if name not in material_names]
    results = []
    for name in candidates:
        rows = stock_rows(name)
        if rows.empty:
            continue
        total_qty, summary = stock_summary(rows)
        results.append({"name": name, "total_qty": total_qty, "summary": summary})
        if len(results) >= limit:
            break
    return results


def stock_detail(product_name):
    rows = stock_rows(product_name)
    total_qty, summary = stock_summary(rows)
    location_rows = []
    if not rows.empty:
        detail = rows.sort_values(["exp_date", "company", "location", "lot"])
        for row in detail.itertuples(index=False):
            location_rows.append(
                {
                    "company": str(row.company or ""),
                    "location": str(row.location or ""),
                    "lot": str(row.lot or ""),
                    "exp_date": str(row.exp_date or ""),
                    "qty": int(row.qty or 0),
                }
            )
    return {
        "name": product_name,
        "total_qty": total_qty,
        "summary": summary,
        "thumbnail": thumbnail_data_uri(product_name),
        "rows": location_rows,
    }


_GM_MEDIC_COMPANY = "노투스팜"
_GM_MEDIC_LOCATION = "지엠메딕"
_YONGIN_COMPANIES = ("노투스팜", "NOH", "노투스")


def _apply_warehouse_filter(df, warehouse):
    """용인창고/화성창고 필터.

    화성창고 = 노투스팜 소속 재고 중 로케이션이 "지엠메딕"인 것만.
    용인창고 = 노투스팜(지엠메딕 제외) + NOH + 노투스 — 즉 화성창고를 뺀
    나머지. 두 창고 어디에도 안 속하는 회사(비자료, 등록대기 등)는
    "전체"를 골랐을 때만 보인다.
    """
    if not isinstance(df, pd.DataFrame) or df.empty or warehouse not in ("yongin", "hwaseong"):
        return df
    company = df["company"].astype(str).str.strip()
    location = df["location"].astype(str).str.strip()
    is_gm_medic = (company == _GM_MEDIC_COMPANY) & (location == _GM_MEDIC_LOCATION)
    if warehouse == "hwaseong":
        return df[is_gm_medic]
    return df[company.isin(_YONGIN_COMPANIES) & ~is_gm_medic]


def expiry_inventory(period="1y", exclude_bidata=True, warehouse="all"):
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
    if exclude_bidata and not df.empty:
        df = df[df["company"].astype(str).str.strip() != "비자료"]
    df = _apply_warehouse_filter(df, warehouse)
    return df


def _expiry_badge_for(nearest_expiry_ts):
    if pd.isna(nearest_expiry_ts):
        return None
    days = int((nearest_expiry_ts.date() - pd.Timestamp.today().normalize().date()).days)
    date_text = nearest_expiry_ts.strftime("%Y.%m.%d")
    if days <= 90:
        return {"label": "3개월 이내", "level": "red", "date": date_text}
    if days <= 180:
        return {"label": "6개월 이내", "level": "yellow", "date": date_text}
    return {"label": "1년 이내", "level": "blue", "date": date_text}


def search_expiry(term, period="1y", exclude_bidata=True, warehouse="all", limit=100):
    df = expiry_inventory(period=period, exclude_bidata=exclude_bidata, warehouse=warehouse)
    if df.empty:
        return []
    available_names = df["product_name"].dropna().astype(str).drop_duplicates().tolist()
    if not term or not term.strip():
        candidates = available_names
    else:
        matched = product_candidates(term, limit=100)
        available_set = set(available_names)
        candidates = [name for name in matched if name in available_set]

    results = []
    for name in candidates:
        rows = df[df["product_name"].astype(str) == str(name)]
        total_qty, summary = stock_summary(rows)
        nearest = rows["_expiry"].min()
        badge = _expiry_badge_for(nearest)
        export_waiting = bool(rows["location"].apply(is_export_waiting_location).any())
        results.append(
            {
                "name": name,
                "total_qty": total_qty,
                "summary": summary,
                "badge": badge,
                "export_waiting": export_waiting,
                "_sort_key": nearest,
            }
        )
    results.sort(key=lambda item: (item["_sort_key"], item["name"]))
    for item in results:
        item.pop("_sort_key", None)
    return results[:limit]


def expiry_detail(product_name, period="1y", exclude_bidata=True, warehouse="all"):
    df = expiry_inventory(period=period, exclude_bidata=exclude_bidata, warehouse=warehouse)
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
    original_path = get_product_image_path(product_name)
    if not original_path:
        return ""
    original = Path(original_path)
    thumb = _THUMB_DIR / f"{original.stem}.jpg"
    return _image_data_uri(thumb if thumb.is_file() else original)
