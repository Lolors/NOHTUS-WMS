"""용인창고/화성창고 구분 규칙. Streamlit을 import하지 않는다."""

from __future__ import annotations

import pandas as pd

GM_MEDIC_COMPANY = "노투스팜"
GM_MEDIC_LOCATION = "지엠메딕"
YONGIN_COMPANIES = ("노투스팜", "NOH", "노투스")


def apply_warehouse_filter(df, warehouse):
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
    is_gm_medic = (company == GM_MEDIC_COMPANY) & (location == GM_MEDIC_LOCATION)
    if warehouse == "hwaseong":
        return df[is_gm_medic]
    return df[company.isin(YONGIN_COMPANIES) & ~is_gm_medic]
