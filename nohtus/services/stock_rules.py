"""부자재/홍보물 제외, 수출대기 로케이션 판정 등 재고 조회 전반에 쓰이는
순수 규칙 모음. Streamlit을 import하지 않는다 — 데스크톱 페이지와
모바일 API가 이 모듈 하나만 보고 같은 기준으로 판정하게 하기 위함.
"""

from __future__ import annotations

import pandas as pd

MATERIAL_OR_PROMO_PREFIXES = ("G1", "G2")
MATERIAL_OR_PROMO_KEYWORDS = ("부자재", "홍보물")
BIDATA_COMPANY = "비자료"


def normalize_location(value) -> str:
    return str(value or "").strip().upper().replace(" ", "").replace("-", "").replace("_", "")


def is_material_or_promo_location(value) -> bool:
    location = normalize_location(value)
    return (
        location.startswith(MATERIAL_OR_PROMO_PREFIXES)
        or any(keyword in location for keyword in MATERIAL_OR_PROMO_KEYWORDS)
    )


def is_export_waiting_location(value) -> bool:
    """P, P1, P2 등 수출대기 로케이션인지 확인한다."""
    return normalize_location(value).startswith("P")


def exclude_material_or_promo_rows(df):
    if not isinstance(df, pd.DataFrame) or df.empty or "location" not in df.columns:
        return df
    return df.loc[~df["location"].apply(is_material_or_promo_location)].copy()
