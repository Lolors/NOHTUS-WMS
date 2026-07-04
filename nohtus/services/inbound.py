"""Inbound service helpers for NOHTUS WMS."""

from __future__ import annotations

from nohtus.config import COMPANIES
import re
from nohtus.db import connect, q


def normalize_blank(value):
    text = str(value or "").strip()
    return text if text else "-"


def first_nonblank(*values):
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text and text.lower() != "nan" and text != "-":
            return text
    return ""


def product_mapping_name_for(company, standard_name):
    if not standard_name:
        return ""
    col = {
        "노투스팜": "erp_nohtuspharm_name",
        "NOH": "erp_noh_name",
        "노투스": "erp_nohtus_name",
        "비자료": "bidata_name",
    }.get(str(company or "").strip())
    if not col:
        return ""
    df = q(f"SELECT {col} AS nm FROM products WHERE standard_name=?", (standard_name,))
    if df.empty:
        return ""
    return first_nonblank(df.iloc[0].get("nm"))


def ensure_inbound_first_product_mapping(standard_name, company, erp_name, product_code=""):
    """입고 최초 등록용: 표준제품명과 선택 사업장의 ERP명/제품코드를 제품매칭표에 저장한다."""
    standard_name = str(standard_name or "").strip()
    company = str(company or "").strip()
    erp_name = str(erp_name or "").strip()
    product_code = str(product_code or "").strip()
    if not standard_name:
        raise ValueError("표준제품명을 입력하세요.")
    if not erp_name:
        raise ValueError("ERP명/비자료명을 입력하세요.")

    with connect() as con:
        cur = con.cursor()
        row = cur.execute("SELECT id FROM products WHERE TRIM(standard_name)=?", (standard_name,)).fetchone()
        if row:
            pid = int(row[0])
        else:
            cur.execute(
                """
                INSERT INTO products(
                    product_code, standard_name, warehouse_name, aliases,
                    erp_nohtuspharm_name, erp_nohtus_name, erp_noh_name, erp_noh_code, bidata_name
                ) VALUES(?,?,?,?,?,?,?,?,?)
                """,
                ("", standard_name, standard_name, "", "", "", "", "", ""),
            )
            pid = int(cur.lastrowid)

        if company == "노투스팜":
            cur.execute("UPDATE products SET erp_nohtuspharm_name=?, product_code=? WHERE id=?", (erp_name, product_code, pid))
        elif company == "NOH":
            cur.execute("UPDATE products SET erp_noh_name=?, erp_noh_code=? WHERE id=?", (erp_name, product_code, pid))
        elif company == "노투스":
            cur.execute("UPDATE products SET erp_nohtus_name=? WHERE id=?", (erp_name, pid))
        elif company == "비자료":
            cur.execute("UPDATE products SET bidata_name=? WHERE id=?", (erp_name, pid))
        else:
            raise ValueError("최초 등록은 사업장을 먼저 선택해야 합니다.")
        con.commit()
    return standard_name, erp_name


def strip_company_stock_label(label):
    """'노투스팜 (30 EA)'처럼 표시된 사업장 라벨에서 실제 사업장명만 추출한다."""
    text = str(label or "").strip()
    return re.sub(r"\s*\(\s*[-+]?\d+\s*EA\s*\)\s*$", "", text).strip()

def inbound_company_options_for(product_name):
    """입고등록 전용 사업장 선택지.
    등록대기는 입고등록 전용 임시값이므로 수량을 붙이지 않는다.
    """
    product_name = str(product_name or "").strip()
    stock = {c: 0 for c in COMPANIES}
    if product_name:
        df = q("""SELECT company, COALESCE(SUM(qty),0) AS qty
                  FROM inventory
                  WHERE product_name=?
                  GROUP BY company""", (product_name,))
        if not df.empty:
            for r in df.itertuples(index=False):
                c = str(getattr(r, "company", "") or "").strip()
                if c in stock:
                    stock[c] = int(getattr(r, "qty", 0) or 0)
    return [f"{c} ({stock.get(c, 0)} EA)" for c in COMPANIES] + ["등록대기"]



# ---------------- mobile stock finder helpers ----------------
