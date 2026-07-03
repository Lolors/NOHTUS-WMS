"""Harden inventory add/move code so duplicate rows cannot be created by code.

This script patches nohtus/services/inventory.py to:
- normalize inventory key fields before lookup/insert
- use one helper for logical inventory key lookup
- update existing rows before insert
- keep the unique index as a last-resort DB guard

Run from repository root:

    python tools/harden_inventory_upserts.py
"""

from __future__ import annotations

import os
import py_compile
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

P = ROOT / "nohtus" / "services" / "inventory.py"
BAK = P.with_name(P.name + ".bak_harden_upserts")

HELPERS = '''

def _clean_key(value, dash_blank=False):
    text = "" if value is None else str(value).strip()
    if dash_blank and not text:
        return "-"
    return text


def _inventory_key(company, product_name, warehouse_name, lot, exp_date, location):
    return (
        _clean_key(company),
        _clean_key(product_name),
        _clean_key(warehouse_name),
        _clean_key(lot, dash_blank=True),
        _clean_key(exp_date, dash_blank=True),
        _clean_key(location),
    )


def _find_inventory_row(cur, company, product_name, warehouse_name, lot, exp_date, location):
    company, product_name, warehouse_name, lot, exp_date, location = _inventory_key(
        company, product_name, warehouse_name, lot, exp_date, location
    )
    return cur.execute("""
        SELECT id, qty
        FROM inventory
        WHERE company=?
          AND product_name=?
          AND IFNULL(warehouse_name,'')=?
          AND IFNULL(lot,'-')=?
          AND IFNULL(exp_date,'-')=?
          AND location=?
    """, (company, product_name, warehouse_name, lot, exp_date, location)).fetchone()
'''

NEW_ADD = '''def add_inventory(company, product, warehouse, lot, exp, location, qty, memo="입고 등록"):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    company, product, warehouse, lot, exp, location = _inventory_key(company, product, warehouse, lot, exp, location)
    qty = int(qty)
    with connect() as con:
        cur = con.cursor()
        row = _find_inventory_row(cur, company, product, warehouse, lot, exp, location)
        if row:
            final_stock = int(row[1] or 0) + qty
            cur.execute("UPDATE inventory SET qty=?, updated_at=? WHERE id=?", (final_stock, now, row[0]))
        else:
            final_stock = qty
            cur.execute("""INSERT INTO inventory(company,product_name,warehouse_name,lot,exp_date,location,qty,updated_at)
                           VALUES(?,?,?,?,?,?,?,?)""", (company, product, warehouse, lot, exp, location, final_stock, now))
        insert_transaction_log(cur, created_at=now, tx_type="입고", product_name=product, warehouse_name=warehouse,
                               lot=lot, exp_date=exp, from_company=None, from_location=None,
                               to_company=company, to_location=location, qty=qty, memo=memo, final_stock=final_stock)
        con.commit()
'''


def main() -> None:
    if not P.exists():
        raise SystemExit("inventory.py not found")
    if BAK.exists():
        raise SystemExit(f"Backup already exists: {BAK.relative_to(ROOT)}. Review/remove it before running again.")

    s = P.read_text(encoding="utf-8")
    old = s

    if "def _inventory_key(" not in s:
        marker = "from nohtus.db import connect, q\n"
        s = s.replace(marker, marker + HELPERS, 1)

    # Replace add_inventory block.
    s = re.sub(
        r"def add_inventory\(company, product, warehouse, lot, exp, location, qty, memo=\"입고 등록\"\):\n.*?\n\ndef move_inventory",
        NEW_ADD + "\n\ndef move_inventory",
        s,
        count=1,
        flags=re.S,
    )

    # Normalize move_inventory inputs after source validation.
    s = s.replace(
        '        product_name = src["product_name"]\n        old_warehouse = src.get("warehouse_name") or ""\n        dest_warehouse = product_mapping_name_for(to_company, product_name) or product_name',
        '        product_name = _clean_key(src["product_name"])\n        old_warehouse = _clean_key(src.get("warehouse_name"))\n        dest_warehouse = product_mapping_name_for(to_company, product_name) or product_name\n        to_company, product_name, dest_warehouse, lot_key, exp_key, to_location = _inventory_key(to_company, product_name, dest_warehouse, src["lot"], src["exp_date"], to_location)',
    )

    # Replace destination lookup in move_inventory with normalized helper.
    s = re.sub(
        r'row = cur\.execute\("""SELECT id, qty FROM inventory WHERE company=\? AND product_name=\? AND IFNULL\(warehouse_name,\'\'\)=\? AND lot=\? AND exp_date=\? AND location=\?""",\n\s*\(to_company, product_name, dest_warehouse or "", src\["lot"\], src\["exp_date"\], to_location\)\)\.fetchone\(\)',
        'row = _find_inventory_row(cur, to_company, product_name, dest_warehouse, lot_key, exp_key, to_location)',
        s,
        count=1,
    )

    # Replace destination insert in move_inventory to use normalized lot/exp.
    s = s.replace(
        'VALUES(?,?,?,?,?,?,?,?)""", (to_company, product_name, dest_warehouse, src["lot"], src["exp_date"], to_location, qty, now))',
        'VALUES(?,?,?,?,?,?,?,?)""", (to_company, product_name, dest_warehouse, lot_key, exp_key, to_location, qty, now))',
    )

    # Replace move transaction log lot/exp with normalized lot/exp.
    s = s.replace(
        'lot=src["lot"], exp_date=src["exp_date"], from_company=src["company"], from_location=src["location"],',
        'lot=lot_key, exp_date=exp_key, from_company=src["company"], from_location=src["location"],',
    )

    if s == old:
        print("No patterns changed. No files modified.")
        return

    shutil.copy2(P, BAK)
    print(f"BACKUP {BAK.relative_to(ROOT)}")
    P.write_text(s, encoding="utf-8")
    py_compile.compile(str(P), doraise=True)
    print("OK compile: nohtus/services/inventory.py")

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    subprocess.run([sys.executable, "tools/smoke_check.py"], cwd=ROOT, env=env, check=True)
    print("DONE. Run: python -m streamlit run app.py")


if __name__ == "__main__":
    main()
