"""부자재 제외, 수출대기 로케이션 판정 등 재고 조회 전반에 쓰이는
순수 규칙 모음. Streamlit을 import하지 않는다 — 데스크톱 페이지와
모바일 API가 이 모듈 하나만 보고 같은 기준으로 판정하게 하기 위함.
"""

from __future__ import annotations

import pandas as pd

from nohtus.db import q

BIDATA_COMPANY = "비자료"


def normalize_location(value) -> str:
    return str(value or "").strip().upper().replace(" ", "").replace("-", "").replace("_", "")


def is_export_waiting_location(value) -> bool:
    """P, P1, P2 등 수출대기 로케이션인지 확인한다."""
    return normalize_location(value).startswith("P")


def material_product_names() -> set[str]:
    """부자재 관리 메뉴에서 부자재로 등록해둔 표준제품명 집합.

    예전에는 G1/G2 구역 로케이션이면 무조건 부자재로 간주했는데, 그 구역에
    실제 제품 재고가 놓이면(예: 임시 보관) 정상 제품이 재고 조회에서 통째로
    사라지는 오탐이 났다. 이제는 부자재 관리에서 직접 체크해둔 제품인지만
    본다 — 어느 로케이션에 있든 결과가 같다.
    """
    try:
        rows = q(
            "SELECT DISTINCT standard_name FROM products "
            "WHERE COALESCE(is_material, 0)=1 AND TRIM(COALESCE(standard_name,''))<>''"
        )
    except Exception:
        return set()
    if rows.empty or "standard_name" not in rows.columns:
        return set()
    return {str(value).strip() for value in rows["standard_name"].dropna().tolist() if str(value).strip()}


def exclude_material_or_promo_rows(df):
    if not isinstance(df, pd.DataFrame) or df.empty or "product_name" not in df.columns:
        return df
    materials = material_product_names()
    if not materials:
        return df
    return df.loc[~df["product_name"].fillna("").astype(str).str.strip().isin(materials)].copy()
