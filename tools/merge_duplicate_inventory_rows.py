"""Merge duplicate inventory rows and add a logical uniqueness guard.

Duplicate definition:
    company + product_name + warehouse_name + lot + exp_date + location

The script:
1) Creates a timestamped backup of data/nohtus.db.
2) Normalizes key text fields by trimming whitespace and using '-' for blank LOT/exp.
3) Merges duplicate inventory rows by keeping the smallest id and summing qty.
4) Repoints outbound_order_items.inventory_id from deleted ids to the kept id.
5) Creates a unique index on the normalized inventory key to prevent future duplicates.

Run from repository root:

    python tools/merge_duplicate_inventory_rows.py
"""

from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "nohtus.db"

KEY_COLS = ["company", "product_name", "warehouse_name", "lot", "exp_date", "location"]


def norm(value: object, dash_blank: bool = False) -> str:
    text = "" if value is None else str(value).strip()
    if dash_blank and not text:
        return "-"
    return text


def main() -> None:
    if not DB.exists():
        raise SystemExit(f"DB not found: {DB}")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = DB.with_name(f"nohtus_before_inventory_merge_{stamp}.db")
    shutil.copy2(DB, backup)
    print(f"BACKUP {backup.relative_to(ROOT)}")

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    # Normalize existing rows first, so whitespace-only differences collapse.
    rows = cur.execute("SELECT id, company, product_name, warehouse_name, lot, exp_date, location FROM inventory").fetchall()
    for r in rows:
        vals = {
            "company": norm(r["company"]),
            "product_name": norm(r["product_name"]),
            "warehouse_name": norm(r["warehouse_name"]),
            "lot": norm(r["lot"], dash_blank=True),
            "exp_date": norm(r["exp_date"], dash_blank=True),
            "location": norm(r["location"]),
        }
        cur.execute(
            """UPDATE inventory
               SET company=?, product_name=?, warehouse_name=?, lot=?, exp_date=?, location=?
               WHERE id=?""",
            (vals["company"], vals["product_name"], vals["warehouse_name"], vals["lot"], vals["exp_date"], vals["location"], r["id"]),
        )

    dup_groups = cur.execute(
        """
        SELECT company, product_name, IFNULL(warehouse_name,'') AS warehouse_name,
               IFNULL(lot,'-') AS lot, IFNULL(exp_date,'-') AS exp_date, location,
               COUNT(*) AS cnt, SUM(qty) AS total_qty, MIN(id) AS keep_id,
               GROUP_CONCAT(id) AS ids
        FROM inventory
        GROUP BY company, product_name, IFNULL(warehouse_name,''), IFNULL(lot,'-'), IFNULL(exp_date,'-'), location
        HAVING COUNT(*) > 1
        ORDER BY cnt DESC, product_name, location
        """
    ).fetchall()

    print(f"DUPLICATE GROUPS {len(dup_groups)}")
    deleted_count = 0
    moved_outbound_refs = 0

    for g in dup_groups:
        ids = [int(x) for x in str(g["ids"]).split(",") if str(x).strip()]
        keep_id = int(g["keep_id"])
        delete_ids = [x for x in ids if x != keep_id]
        total_qty = int(g["total_qty"] or 0)

        cur.execute("UPDATE inventory SET qty=?, updated_at=? WHERE id=?", (total_qty, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), keep_id))

        for old_id in delete_ids:
            res = cur.execute("UPDATE outbound_order_items SET inventory_id=? WHERE inventory_id=?", (keep_id, old_id))
            moved_outbound_refs += int(res.rowcount or 0)
            cur.execute("DELETE FROM inventory WHERE id=?", (old_id,))
            deleted_count += 1

    # Prevent future duplicates. Use IFNULL expressions to make NULL and blanks behave consistently.
    cur.execute("DROP INDEX IF EXISTS ux_inventory_logical_key")
    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_inventory_logical_key
        ON inventory(
            company,
            product_name,
            IFNULL(warehouse_name,''),
            IFNULL(lot,'-'),
            IFNULL(exp_date,'-'),
            location
        )
        """
    )

    con.commit()

    remain = cur.execute(
        """
        SELECT COUNT(*) FROM (
            SELECT 1
            FROM inventory
            GROUP BY company, product_name, IFNULL(warehouse_name,''), IFNULL(lot,'-'), IFNULL(exp_date,'-'), location
            HAVING COUNT(*) > 1
        )
        """
    ).fetchone()[0]
    total_rows = cur.execute("SELECT COUNT(*) FROM inventory").fetchone()[0]
    con.close()

    print(f"MERGED deleted_rows={deleted_count}, outbound_refs_repointed={moved_outbound_refs}")
    print(f"INVENTORY ROWS {total_rows}")
    print(f"REMAINING DUPLICATE GROUPS {remain}")
    print("DONE")


if __name__ == "__main__":
    main()
