from __future__ import annotations

import re

import pandas as pd

from nohtus.db import q
from nohtus.services.closing import clean_excel_text, dataframe_to_excel_bytes


ERP_SALES_COLUMNS = ["사업장", "표준제품명", "ERP명", "수량", "매칭상태"]


def _clean(value):
    return clean_excel_text(value)


def load_export_waiting_erp_name_map():
    """제품매칭표의 표준제품명별 네 사업장 ERP명을 가져온다."""
    products = q(
        """SELECT standard_name,erp_nohtuspharm_name,erp_nohtus_name,erp_noh_name,bidata_name
           FROM products
           ORDER BY standard_name,id"""
    )
    result = {}
    if products.empty:
        return result

    for product in products.itertuples(index=False):
        standard_name = _clean(getattr(product, "standard_name", ""))
        if not standard_name:
            continue
        erp_names = {
            "노투스팜": _clean(getattr(product, "erp_nohtuspharm_name", "")),
            "노투스": _clean(getattr(product, "erp_nohtus_name", "")),
            "NOH": _clean(getattr(product, "erp_noh_name", "")),
            "비자료": _clean(getattr(product, "bidata_name", "")),
        }
        for company, erp_name in erp_names.items():
            key = (company, standard_name)
            if erp_name and key not in result:
                result[key] = erp_name
    return result


def build_export_waiting_erp_sales_rows(items, product_map=None):
    """수출대기 재고행을 사업장별 ERP 제품명 기준의 매출입력 목록으로 합산한다."""
    if items is None or items.empty:
        return pd.DataFrame(columns=ERP_SALES_COLUMNS)

    product_map = load_export_waiting_erp_name_map() if product_map is None else dict(product_map)
    rows = []
    for item in items.itertuples(index=False):
        company = _clean(getattr(item, "사업장", ""))
        standard_name = _clean(getattr(item, "제품명", ""))
        numeric_qty = pd.to_numeric(getattr(item, "수량", 0), errors="coerce")
        qty = 0 if pd.isna(numeric_qty) else int(numeric_qty)
        if not company or not standard_name or qty == 0:
            continue
        erp_name = _clean(product_map.get((company, standard_name)))
        rows.append(
            {
                "사업장": company,
                "표준제품명": standard_name,
                "ERP명": erp_name,
                "수량": qty,
                "매칭상태": "매칭완료" if erp_name else "확인필요",
            }
        )

    if not rows:
        return pd.DataFrame(columns=ERP_SALES_COLUMNS)

    result = pd.DataFrame(rows)
    result = (
        result.groupby(["사업장", "표준제품명", "ERP명", "매칭상태"], as_index=False, dropna=False)["수량"]
        .sum()
        .sort_values(["사업장", "매칭상태", "ERP명", "표준제품명"], ascending=[True, False, True, True])
        .reset_index(drop=True)
    )
    result["수량"] = pd.to_numeric(result["수량"], errors="coerce").fillna(0).astype(int)
    return result[ERP_SALES_COLUMNS]


def export_waiting_erp_sales_excel_bytes(rows):
    return dataframe_to_excel_bytes(rows[ERP_SALES_COLUMNS], "ERP매출입력용")


def safe_export_no_for_filename(export_no):
    text = re.sub(r'[\\/:*?"<>|]+', "_", _clean(export_no))
    text = re.sub(r"\s+", "_", text).strip("._")
    return text[:80] or "수출대기"
