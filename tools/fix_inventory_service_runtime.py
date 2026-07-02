from __future__ import annotations

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
BAK = P.with_name(P.name + ".bak_fix_runtime")

HELPERS = '''

def first_nonblank(*values):
    for v in values:
        if v is None:
            continue
        text = str(v).strip()
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
    }.get(company)
    if not col:
        return ""
    df = q(f"SELECT {col} AS nm FROM products WHERE standard_name=?", (standard_name,))
    if df.empty:
        return ""
    return first_nonblank(df.iloc[0].get("nm"))


def insert_transaction_log(cur, *, created_at, tx_type, product_name, warehouse_name=None,
                           lot=None, exp_date=None, from_company=None, from_location=None,
                           to_company=None, to_location=None, qty=0, memo="", final_stock=None):
    cur.execute(
        """INSERT INTO transactions(
               created_at, tx_type, product_name, warehouse_name, lot, exp_date,
               from_company, from_location, to_company, to_location, qty, memo, final_stock
           ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (created_at, tx_type, product_name, warehouse_name, lot, exp_date,
         from_company, from_location, to_company, to_location, int(qty or 0), memo, final_stock),
    )
'''


def main():
    if not P.exists():
        raise SystemExit("inventory.py not found")
    if BAK.exists():
        raise SystemExit(f"Backup already exists: {BAK.relative_to(ROOT)}")
    s = P.read_text(encoding="utf-8")
    shutil.copy2(P, BAK)
    print(f"BACKUP {BAK.relative_to(ROOT)}")

    # Remove runtime app dependency that can cause circular imports.
    s = s.replace("        from app import product_mapping_name_for\n", "")
    s = re.sub(r"^from app import product_mapping_name_for\n", "", s, flags=re.M)

    # Ensure sqlite3 import exists.
    if "import sqlite3" not in s:
        s = s.replace("from __future__ import annotations\n\n", "from __future__ import annotations\n\nimport sqlite3\n")

    # Add helpers if missing.
    if "def insert_transaction_log" not in s:
        marker = "from nohtus.db import connect, q\n"
        s = s.replace(marker, marker + HELPERS, 1)

    # Make adjust_inventory row_factory use local sqlite3 import defensively.
    s = s.replace("        con.row_factory = sqlite3.Row", "        import sqlite3 as _sqlite3\n        con.row_factory = _sqlite3.Row")

    # Add final_stock to 재고조정 log if current call lacks it.
    s = s.replace(
        'to_company=src["company"], to_location=src["location"], qty=diff, memo=reason_memo)',
        'to_company=src["company"], to_location=src["location"], qty=diff, memo=reason_memo, final_stock=actual_qty)',
    )

    P.write_text(s, encoding="utf-8")
    py_compile.compile(str(P), doraise=True)
    print("OK compile: nohtus/services/inventory.py")
    subprocess.run([sys.executable, "tools/smoke_check.py"], cwd=ROOT, check=True)
    print("DONE")


if __name__ == "__main__":
    main()
