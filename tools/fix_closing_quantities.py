"""Fix closing page quantity semantics.

Business rule:
    - 기존수량: stock at the time of outbound transaction, before outbound.
      Use transactions.final_stock + transactions.qty when a matching outbound
      transaction exists.
    - 출고수량: outbound_order_items.qty.
    - 현재수량: current stock total for the same company + product + lot + exp_date,
      regardless of inventory row id and location.

Run from repository root:

    python tools/fix_closing_quantities.py
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
BACKUP = PAGE.with_name(PAGE.name + ".bak_fix_quantities")

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
                                product_name,
                                COALESCE(lot, '-') AS lot,
                                COALESCE(exp_date, '-') AS exp_date,
                                SUM(qty) AS qty
                         FROM inventory
                         WHERE qty <> 0
                         GROUP BY company, product_name, COALESCE(lot, '-'), COALESCE(exp_date, '-')
                     ) cur
                       ON cur.company = i.company
                      AND cur.product_name = i.product_name
                      AND cur.lot = COALESCE(i.lot, '-')
                      AND cur.exp_date = COALESCE(i.exp_date, '-')
                     WHERE o.order_date=? AND IFNULL(o.status,'')<>'취소됨'
                     ORDER BY o.id, i.company, i.location, i.product_name, i.lot, i.exp_date""", (ds,))'''

OLD_AFTER_QUERY_PATTERN = re.compile(
    r'''            items\["유통기한"\] = items\["유통기한"\]\.apply\(display_date_only\)\n
            items\["출고수량"\] = pd\.to_numeric\(items\["출고수량"\], errors="coerce"\)\.fillna\(0\)\.astype\(int\)\n
            items\["현재수량"\] = pd\.to_numeric\(items\["현재수량"\], errors="coerce"\)\.fillna\(0\)\.astype\(int\)\n
            valid_inv = items\["재고ID"\]\.notna\(\)\n
            items\["동일재고출고합계"\] = items\.groupby\("재고ID"\)\["출고수량"\]\.transform\("sum"\)\.where\(valid_inv, items\["출고수량"\]\)\n
            # 오늘 출고 체크는 실제 지시내역 확인용이다\.\n
            # 현재수량은 출고지시 저장으로 이미 차감된 뒤의 inventory 수량이며,\n
            # 기존수량은 오늘 해당 재고ID의 출고수량을 되돌려 계산한 출고 전 수량이다\.\n
            items\["기존수량"\] = items\["현재수량"\] \+ items\["동일재고출고합계"\]''',
    re.MULTILINE,
)

NEW_AFTER_QUERY = '''            items["유통기한"] = items["유통기한"].apply(display_date_only)
            items["출고수량"] = pd.to_numeric(items["출고수량"], errors="coerce").fillna(0).astype(int)
            items["기존수량"] = pd.to_numeric(items["기존수량"], errors="coerce").fillna(0).astype(int)
            items["현재수량"] = pd.to_numeric(items["현재수량"], errors="coerce").fillna(0).astype(int)
            # 기준:
            # - 기존수량: 출고 거래 당시 기록된 출고 전 재고(transactions.final_stock + qty)
            # - 현재수량: 현재 inventory 기준 같은 사업장+제품+제조번호+유통기한 전체 수량'''


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

    if OLD_AFTER_QUERY_PATTERN.search(new_text):
        new_text = OLD_AFTER_QUERY_PATTERN.sub(NEW_AFTER_QUERY, new_text, count=1)
    else:
        # More tolerant fallback for already-modified files.
        fallback = re.compile(
            r'''            items\["유통기한"\] = items\["유통기한"\]\.apply\(display_date_only\)\n.*?            items\["기존수량"\] = items\["현재수량"\] \+ items\["동일재고출고합계"\]''',
            re.DOTALL,
        )
        if fallback.search(new_text):
            new_text = fallback.sub(NEW_AFTER_QUERY, new_text, count=1)
        else:
            print("WARN: Could not replace old post-query quantity calculation. Query was patched only.")

    shutil.copy2(PAGE, BACKUP)
    print(f"BACKUP {BACKUP.relative_to(ROOT)}")
    PAGE.write_text(new_text, encoding="utf-8")
    print("PATCH closing quantity semantics")

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
