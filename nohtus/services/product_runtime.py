from pathlib import Path
from datetime import datetime

import sqlite3
import pandas as pd
import streamlit as st

from nohtus.db import connect, q, exec_sql
from nohtus.dates import normalize_exp_date
from nohtus.services.outbound_runtime import insert_transaction_log

PROJECT_ROOT = Path(__file__).resolve().parents[2]

def normalize_blank(v):
    v = (v or "").strip()
    return v if v else "-"

def add_product_mapping_record(standard_name, erp_np="", np_code="", erp_noh="", noh_code="", erp_nt="", bidata_name="", aliases=""):
    """제품 매칭 관리 화면에서 제품매칭표 행을 직접 추가한다."""
    standard_name = (standard_name or "").strip()
    if not standard_name:
        raise ValueError("표준제품명은 반드시 입력해야 합니다.")
    with connect() as con:
        cur = con.cursor()
        exists = cur.execute("SELECT id FROM products WHERE TRIM(standard_name)=?", (standard_name,)).fetchone()
        if exists:
            raise ValueError("이미 같은 표준제품명이 제품매칭표에 있습니다. 기존 행을 수정하세요.")
        cur.execute("""INSERT INTO products(
            product_code, standard_name, warehouse_name, aliases,
            erp_nohtuspharm_name, erp_nohtus_name, erp_noh_name, erp_noh_code, bidata_name
        ) VALUES(?,?,?,?,?,?,?,?,?)""", (
            str(np_code or "").strip(), standard_name, standard_name, str(aliases or "").strip(),
            str(erp_np or "").strip(), str(erp_nt or "").strip(), str(erp_noh or "").strip(),
            str(noh_code or "").strip(), str(bidata_name or "").strip()
        ))
        con.commit()

def get_erp_column(company):
    if company == "노투스팜":
        return "erp_nohtuspharm_name"
    if company == "NOH":
        return "erp_noh_name"
    if company == "노투스":
        return "erp_nohtus_name"
    return None

def ensure_standard_product(name):
    """표준제품명이 products DB에 없으면 새로 등록하고, 최종 표준제품명을 반환한다."""
    name = (name or "").strip()
    if not name:
        return ""
    with connect() as con:
        cur = con.cursor()
        existing = cur.execute("SELECT standard_name FROM products WHERE TRIM(standard_name)=?", (name,)).fetchone()
        if existing:
            return str(existing[0])
        cur.execute("""
            INSERT INTO products(
                product_code, standard_name, warehouse_name, aliases,
                erp_nohtuspharm_name, erp_nohtus_name, erp_noh_name, erp_noh_code, bidata_name
            ) VALUES(?,?,?,?,?,?,?,?,?)
        """, ("", name, name, "", "", "", "", "", ""))
        con.commit()
    return name

def ensure_standard_product_only(name):
    """최초 입고 등록용: 표준제품명만 products DB에 추가한다.
    ERP명/비자료명/별칭은 비워 두어 제품 매칭 관리에서 보완할 수 있게 한다.
    """
    name = (name or "").strip()
    if not name:
        return ""
    with connect() as con:
        cur = con.cursor()
        existing = cur.execute("SELECT standard_name FROM products WHERE TRIM(standard_name)=?", (name,)).fetchone()
        if existing:
            return str(existing[0])
        cur.execute("""
            INSERT INTO products(
                product_code, standard_name, warehouse_name, aliases,
                erp_nohtuspharm_name, erp_nohtus_name, erp_noh_name, erp_noh_code, bidata_name
            ) VALUES(?,?,?,?,?,?,?,?,?)
        """, ("", name, "", "", "", "", "", "", ""))
        con.commit()
    return name

def ensure_inbound_first_product_mapping(standard_name, company, erp_name, product_code=""):
    """입고 최초 등록용: 표준제품명과 선택 사업장의 ERP명/제품코드를 제품매칭표에 저장한다."""
    standard_name = (standard_name or "").strip()
    company = (company or "").strip()
    erp_name = (erp_name or "").strip()
    product_code = (product_code or "").strip()
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
            cur.execute("""
                INSERT INTO products(
                    product_code, standard_name, warehouse_name, aliases,
                    erp_nohtuspharm_name, erp_nohtus_name, erp_noh_name, erp_noh_code, bidata_name
                ) VALUES(?,?,?,?,?,?,?,?,?)
            """, ("", standard_name, standard_name, "", "", "", "", "", ""))
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

def warehouse_name_options(term=""):
    term = (term or "").strip().lower()
    df = q("""
        SELECT standard_name AS name FROM products
        UNION
        SELECT warehouse_name AS name FROM products WHERE IFNULL(warehouse_name,'')<>''
        UNION
        SELECT product_name AS name FROM inventory
        UNION
        SELECT warehouse_name AS name FROM inventory WHERE IFNULL(warehouse_name,'')<>''
        ORDER BY name
    """)
    df = df.dropna()
    df = df[df["name"].astype(str).str.strip() != ""]
    if term:
        df = df[df["name"].astype(str).str.lower().str.contains(term, regex=False)]
    return df["name"].drop_duplicates().tolist()

def update_inventory_metadata(inv_id, new_lot, new_exp, memo=""):
    """기존 재고 행의 제조번호/유통기한을 정정한다. 수량은 변경하지 않는다."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lot2 = normalize_blank(new_lot)
    exp2 = normalize_exp_date(new_exp)
    with connect() as con:
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        src = cur.execute("SELECT * FROM inventory WHERE id=?", (int(inv_id),)).fetchone()
        if not src:
            raise ValueError("수정할 재고를 찾을 수 없습니다.")
        old_lot = src["lot"] or "-"
        old_exp = src["exp_date"] or "-"
        if lot2 == old_lot and exp2 == old_exp:
            raise ValueError("변경된 제조번호/유통기한이 없습니다.")

        target = cur.execute("""
            SELECT id, qty FROM inventory
            WHERE id<>? AND company=? AND product_name=? AND IFNULL(warehouse_name,'')=?
              AND lot=? AND exp_date=? AND location=?
        """, (int(inv_id), src["company"], src["product_name"], src["warehouse_name"] or "", lot2, exp2, src["location"])).fetchone()

        merge_note = ""
        qty = int(src["qty"] or 0)
        if target:
            cur.execute("UPDATE inventory SET qty=?, updated_at=? WHERE id=?", (int(target["qty"] or 0) + qty, now, int(target["id"])))
            cur.execute("DELETE FROM inventory WHERE id=?", (int(inv_id),))
            merge_note = f" / 동일 재고행 #{int(target['id'])}에 수량 합산"
        else:
            cur.execute("UPDATE inventory SET lot=?, exp_date=?, updated_at=? WHERE id=?", (lot2, exp2, now, int(inv_id)))

        reason = f"재고정보수정: LOT {old_lot} → {lot2}, 유통기한 {old_exp} → {exp2}"
        if str(memo or "").strip():
            reason += f" / {str(memo).strip()}"
        reason += merge_note
        insert_transaction_log(cur, created_at=now, tx_type="재고정보수정", product_name=src["product_name"], warehouse_name=src["warehouse_name"],
                               lot=lot2, exp_date=exp2, from_company=src["company"], from_location=src["location"],
                               to_company=src["company"], to_location=src["location"], qty=0, memo=reason)
        con.commit()
        return True

def asset_dir():
    d = PROJECT_ROOT / "data" / "product_images"
    d.mkdir(parents=True, exist_ok=True)
    return d

def safe_filename(name):
    keep = []
    for ch in str(name):
        if ch.isalnum() or ch in ("-", "_", "."):
            keep.append(ch)
        else:
            keep.append("_")
    return "".join(keep)[:80] or "product"

def save_product_image(product_name, uploaded_file):
    if uploaded_file is None or not product_name:
        return None
    suffix = Path(uploaded_file.name).suffix.lower() or ".jpg"
    fname = safe_filename(product_name) + "_" + datetime.now().strftime("%Y%m%d_%H%M%S") + suffix
    path = asset_dir() / fname
    path.write_bytes(uploaded_file.getvalue())
    rel = str(path.relative_to(PROJECT_ROOT))
    exec_sql("UPDATE products SET image_path=? WHERE standard_name=?", (rel, product_name))
    return rel

def product_image_placeholder(size=60):
    st.markdown(f"""
    <div style='width:{size}px;height:{size}px;border:1.5px dashed #cbd5e1;border-radius:14px;background:#f8fafc;display:flex;align-items:center;justify-content:center;color:#94a3b8;font-size:22px;'>📷</div>
    """, unsafe_allow_html=True)
