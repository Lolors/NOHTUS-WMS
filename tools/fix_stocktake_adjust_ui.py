"""Clean up stocktake adjustment UI after WMS 5.0 refactor.

Changes applied to nohtus/pages/stocktake.py:
1) Remove temporary DEBUG DB/inventory count messages.
2) Show only qty > 0 inventory rows in stock adjustment target list.
3) Normalize LOT/exp dropdown values with strip() so duplicates do not appear.
4) Keep selected stock table grouped by the selected product + LOT + exp date,
   so all locations for the same LOT are shown together.

Run from repository root:

    python tools/fix_stocktake_adjust_ui.py
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

P = ROOT / "nohtus" / "pages" / "stocktake.py"
BAK = P.with_name(P.name + ".bak_fix_adjust_ui")


def main() -> None:
    if not P.exists():
        raise SystemExit("stocktake.py not found")
    if BAK.exists():
        raise SystemExit(f"Backup already exists: {BAK.relative_to(ROOT)}. Review/remove it before running again.")

    s = P.read_text(encoding="utf-8")
    old = s

    # Remove temporary debug lines added during DB-path diagnosis.
    debug_patterns = [
        r"\n\s*from nohtus\.config import DB_PATH\s*",
        r"\n\s*st\.(?:error|warning|write)\(f?['\"]DEBUG DB:.*?\)\s*",
        r"\n\s*st\.(?:error|warning|write)\(q\(['\"]SELECT COUNT\(\*\) AS cnt FROM inventory['\"]\)\)\s*",
        r"\n\s*st\.(?:error|warning|write)\(.*inventory count.*?\)\s*",
    ]
    for pat in debug_patterns:
        s = re.sub(pat, "", s)

    # Stock adjustment should not show zero-quantity targets.
    s = s.replace("""        FROM inventory
        WHERE 1=1
        ORDER BY product_name, lot, exp_date, location""", """        FROM inventory
        WHERE qty > 0
        ORDER BY product_name, lot, exp_date, location""")
    s = s.replace("""        FROM inventory
        WHERE qty <> 0
        ORDER BY product_name, lot, exp_date, location""", """        FROM inventory
        WHERE qty > 0
        ORDER BY product_name, lot, exp_date, location""")

    # Normalize selected product list.
    s = s.replace(
        'products = filtered["product_name"].dropna().astype(str).drop_duplicates().tolist()',
        'products = sorted(filtered["product_name"].fillna("").astype(str).str.strip().loc[lambda x: x != ""].drop_duplicates().tolist())',
    )
    s = s.replace(
        'lot_df = filtered[filtered["product_name"] == product].copy()',
        'lot_df = filtered[filtered["product_name"].fillna("").astype(str).str.strip() == product].copy()',
    )

    # Normalize LOT dropdown to avoid duplicates caused by whitespace/null differences.
    s = s.replace(
        'lots = lot_df["lot"].fillna("-").astype(str).drop_duplicates().tolist()\n                lot = st.selectbox("LOT/제조번호", lots, key=f"stock_adjust_lot_{product}")\n\n                exp_df = lot_df[lot_df["lot"].fillna("-").astype(str) == lot].copy()',
        'lot_df["_lot_key"] = lot_df["lot"].fillna("-").astype(str).str.strip().replace("", "-")\n                lots = sorted(lot_df["_lot_key"].drop_duplicates().tolist())\n                lot = st.selectbox("LOT/제조번호", lots, key=f"stock_adjust_lot_{product}")\n\n                exp_df = lot_df[lot_df["_lot_key"] == lot].copy()',
    )

    # Normalize exp dropdown too, then selected stock table shows all rows for same product+LOT+exp.
    s = s.replace(
        'exps = exp_df["exp_date"].fillna("-").astype(str).drop_duplicates().tolist()\n                exp = st.selectbox("유통기한", exps, key=f"stock_adjust_exp_{product}_{lot}", format_func=display_date_only)\n\n            target_df = exp_df[exp_df["exp_date"].fillna("-").astype(str) == exp].copy()',
        'exp_df["_exp_key"] = exp_df["exp_date"].fillna("-").astype(str).str.strip().replace("", "-")\n                exps = sorted(exp_df["_exp_key"].drop_duplicates().tolist())\n                exp = st.selectbox("유통기한", exps, key=f"stock_adjust_exp_{product}_{lot}", format_func=display_date_only)\n\n            target_df = exp_df[exp_df["_exp_key"] == exp].copy()',
    )

    # Make selected stock labels a little clearer when several rows share a LOT.
    s = s.replace(
        'label = f"{r.location} / {r.company} / 현재 {int(r.qty)}EA"',
        'label = f"{r.location} / {r.company} / 현재 {int(r.qty)}EA"',
    )

    if s == old:
        print("No matching stocktake patterns found. No files changed.")
        return

    shutil.copy2(P, BAK)
    print(f"BACKUP {BAK.relative_to(ROOT)}")
    P.write_text(s, encoding="utf-8")
    py_compile.compile(str(P), doraise=True)
    print("OK compile: nohtus/pages/stocktake.py")

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    subprocess.run([sys.executable, "tools/smoke_check.py"], cwd=ROOT, env=env, check=True)
    print("DONE. Run: python -m streamlit run app.py")


if __name__ == "__main__":
    main()
