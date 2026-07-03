"""Fix closing page quantity semantics using location-aware current stock.

Business rule:
    - 기존수량: stock at the time of outbound transaction, before outbound.
      Use transactions.final_stock + transactions.qty when a matching outbound
      transaction exists.
    - 출고수량: outbound_order_items.qty.
    - 현재수량: current stock for the same company + location + product + lot + exp_date.
      Location is included because staff need to go to the exact picking location.

Run from repository root:

    python tools/fix_closing_quantities_by_location.py
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
BACKUP = PAGE.with_name(PAGE.name + ".bak_fix_quantities_by_location")

NEW_QUERY = '''        items = q("""SELECT o.id AS 지시서번호,
                            COALESCE(o.title, '') AS 출고지시서제목,
                            i.inventory_id AS 재고ID,
                            i.company AS 사업장,
                            i.location AS 로케이션,
                            i.product_name AS 표준제품명,
                            COALESCE(i.lot, '-') AS 제조번호,
                            COALESCE(i.exp_date, '-') AS 유통기한,
                            i.qty AS 출고수량,
                            COALESCE(tx.final_stock + tx.qty, 0) AS 기존수량,
                            COALESCE(cur.qty, 0) AS 현재수량
                     FROM outbound_orders o
                     JOIN outbound_order_items i ON o.id=i.order_id
                     LEFT JOIN (
                         SELECT from_company,
                                from_location,
                                product_name,
                                COALESCE(lot, '-') AS lot,
                                COALESCE(exp_date, '-') AS exp_date,
                                qty,
                                final_stock,
                                substr(created_at, 1, 10) AS tx_date,
                                MAX(id) AS tx_id
                         FROM transactions
                         WHERE tx_type='출고'
                         GROUP BY from_company, from_location, product_name,
                                  COALESCE(lot, '-'), COALESCE(exp_date, '-'), qty, final_stock, substr(created_at, 1, 10)
                     ) tx
                       ON tx.tx_date = o.order_date
                      AND tx.from_company = i.company
                      AND tx.from_location = i.location
                      AND tx.product_name = i.product_name
                      AND tx.lot = COALESCE(i.lot, '-')
                      AND tx.exp_date = COALESCE(i.exp_date, '-')
                      AND tx.qty = i.qty
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
                     ) cur
                       ON cur.company = i.company
                      AND cur.location = i.location
                      AND cur.product_name = i.product_name
                      AND cur.lot = COALESCE(i.lot, '-')
                      AND cur.exp_date = COALESCE(i.exp_date, '-')
                     WHERE o.order_date=? AND IFNULL(o.status,'')<>'취소됨'
                     ORDER BY o.id, i.company, i.location, i.product_name, i.lot, i.exp_date""", (ds,))'''

NEW_AFTER_QUERY = '''            items["유통기한"] = items["유통기한"].apply(display_date_only)
            items["출고수량"] = pd.to_numeric(items["출고수량"], errors="coerce").fillna(0).astype(int)
            items["기존수량"] = pd.to_numeric(items["기존수량"], errors="coerce").fillna(0).astype(int)
            items["현재수량"] = pd.to_numeric(items["현재수량"], errors="coerce").fillna(0).astype(int)
            # 기준:
            # - 기존수량: 출고 거래 당시 해당 로케이션의 출고 전 재고(transactions.final_stock + qty)
            # - 현재수량: 현재 inventory 기준 같은 사업장+로케이션+제품+제조번호+유통기한 수량'''


def main() -> None:
    if not PAGE.exists():
        raise SystemExit("nohtus/pages/closing.py not found.")
    if BACKUP.exists():
        raise SystemExit(f"Backup already exists: {BACKUP.relative_to(ROOT)}. Review/remove it before running again.")

    text = PAGE.read_text(encoding="utf-8")

    query_pattern = re.compile(
        r"        items = q\(\"\"\"SELECT o\.id AS 지시서번호,.*?ORDER BY o\.id, i\.company, i\.location, i\.product_name, i\.lot, i\.exp_date\"\"\", \(ds,\)\)",
        re.DOTALL,
    )
    if not query_pattern.search(text):
        raise SystemExit("Could not find the today closing SELECT query block. No files changed.")

    new_text = query_pattern.sub(NEW_QUERY, text, count=1)

    # Replace the old calculation block from 유통기한 formatting through 기존수량 calculation.
    calc_pattern = re.compile(
        r'''            items\["유통기한"\] = items\["유통기한"\]\.apply\(display_date_only\)\n.*?            items\["기존수량"\] = items\["현재수량"\] \+ items\["동일재고출고합계"\]''',
        re.DOTALL,
    )
    if calc_pattern.search(new_text):
        new_text = calc_pattern.sub(NEW_AFTER_QUERY, new_text, count=1)
    else:
        print("WARN: Could not replace old post-query quantity calculation. Query was patched only.")

    shutil.copy2(PAGE, BACKUP)
    print(f"BACKUP {BACKUP.relative_to(ROOT)}")
    PAGE.write_text(new_text, encoding="utf-8")
    print("PATCH closing quantity semantics with location-aware current stock")

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
