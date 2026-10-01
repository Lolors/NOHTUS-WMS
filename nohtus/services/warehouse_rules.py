"""용인창고/화성창고 구분 규칙. Streamlit을 import하지 않는다."""

from __future__ import annotations

import pandas as pd

from nohtus.services.stock_rules import BIDATA_COMPANY

GM_MEDIC_COMPANY = "노투스팜"
GM_MEDIC_LOCATION = "지엠메딕"
YONGIN_COMPANIES = ("노투스팜", "NOH", "노투스", BIDATA_COMPANY)


def apply_warehouse_filter(df, warehouse):
    """용인창고/화성창고 필터.

    화성창고 = 로케이션이 "지엠메딕"인 것만 (노투스팜 소속 재고 기준).
    용인창고 = 노투스팜(지엠메딕 제외) + NOH + 노투스 + 비자료 — 즉
    화성창고를 뺀 나머지. 비자료는 실제로 용인창고에만 있으므로 용인창고
    선택 시에도 보여야 한다. 그 외 두 창고 어디에도 안 속하는 회사
    (등록대기 등)는 "전체"를 골랐을 때만 보인다.
    """
    if not isinstance(df, pd.DataFrame) or df.empty or warehouse not in ("yongin", "hwaseong"):
        return df
    company = df["company"].astype(str).str.strip()
    location = df["location"].astype(str).str.strip()
    is_gm_medic = (company == GM_MEDIC_COMPANY) & (location == GM_MEDIC_LOCATION)
    if warehouse == "hwaseong":
        return df[is_gm_medic]
    return df[company.isin(YONGIN_COMPANIES) & ~is_gm_medic]
