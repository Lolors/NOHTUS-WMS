"""Fix closing page current quantity lookup.

Problem:
    nohtus/pages/closing.py calculates current quantity only by
    outbound_order_items.inventory_id -> inventory.id. If the inventory row was
    removed/recreated after outbound processing, the join fails and current qty
    displays as 0 even when matching stock still exists.

Fix:
    Replace the today-closing SELECT query so it first tries inventory_id and
    then falls back to company/location/product/lot/exp_date grouped stock.

Run from repository root:

    python tools/fix_closing_current_qty.py
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

PAGE = ROOT / "nohtus" / "pages" / "closing.py"
BACKUP = PAGE.with_name(PAGE.name + ".bak_fix_current_qty")

NEW_QUERY = '''        items = q("""SELECT o.id AS 지시서번호,
                            COALESCE(o.title, '') AS 출고지시서제목,
                            i.inventory_id AS 재고ID,
                            i.company AS 사업장,
                            i.location AS 로케이션,
                            i.product_name AS 표준제품명,
                            COALESCE(i.lot, '-') AS 제조번호,
                            COALESCE(i.exp_date, '-') AS 유통기한,
                            i.qty AS 출고수량,
                            COALESCE(inv_id.qty, inv_key.qty, 0) AS 현재수량
                     FROM outbound_orders o
                     JOIN outbound_order_items i ON o.id=i.order_id
                     LEFT JOIN inventory inv_id ON i.inventory_id=inv_id.id
                     LEFT JOIN (
                         SELECT company,
                                location,
                                product_name,
                                COALESCE(lot, '-') AS lot,
                                COALESCE(exp_date, '-') AS exp_date,
                                SUM(qty) AS qty
                         FROM inventory
                         WHERE qty <> 0
                         GROUP BY company, location, product_name, COALESCE(lot, '-'), COALESCE(exp_date, '-')
                     ) inv_key
                       ON inv_key.company = i.company
                      AND inv_key.location = i.location
                      AND inv_key.product_name = i.product_name
                      AND inv_key.lot = COALESCE(i.lot, '-')
                      AND inv_key.exp_date = COALESCE(i.exp_date, '-')
                     WHERE o.order_date=? AND IFNULL(o.status,'')<>'취소됨'
                     ORDER BY o.id, i.company, i.location, i.product_name, i.lot, i.exp_date""", (ds,))'''


def main() -> None:
    if not PAGE.exists():
        raise SystemExit("nohtus/pages/closing.py not found.")
    if BACKUP.exists():
        raise SystemExit(f"Backup already exists: {BACKUP.relative_to(ROOT)}. Review/remove it before running again.")

    text = PAGE.read_text(encoding="utf-8")

    pattern = re.compile(
        r"        items = q\(\"\"\"SELECT o\.id AS 지시서번호,.*?ORDER BY o\.id, i\.company, i\.location, i\.product_name, i\.lot, i\.exp_date\"\"\", \(ds,\)\)",
        re.DOTALL,
    )
    match = pattern.search(text)
    if not match:
        raise SystemExit("Could not find the today closing SELECT query block. No files changed.")

    shutil.copy2(PAGE, BACKUP)
    print(f"BACKUP {BACKUP.relative_to(ROOT)}")

    new_text = text[: match.start()] + NEW_QUERY + text[match.end():]
    PAGE.write_text(new_text, encoding="utf-8")
    print("PATCH closing current quantity query")

    try:
        py_compile.compile(str(PAGE), doraise=True)
        print("OK compile: nohtus/pages/closing.py")
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
        subprocess.run([sys.executable, "tools/smoke_check.py"], cwd=ROOT, env=env, check=True)
    except Exception:
        shutil.copy2(BACKUP, PAGE)
        print("FAILED. Restored closing.py from backup.")
        raise

    print("DONE. Run: streamlit run app.py")


if __name__ == "__main__":
    main()
