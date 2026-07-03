"""Apply small WMS 5.0 UI/behavior requests.

Changes:
1) Move registration page 3-column ratio: 40:40:20 or similar -> 30:40:30.
2) Stocktake adjustment search should include qty=0 inventory rows.

This script is conservative and only edits local generated page modules.
Run from repository root:

    python tools/apply_wms5_ui_requests.py

Then:

    python tools/smoke_check.py
    python -m streamlit run app.py
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

CANDIDATE_FILES = [
    ROOT / "nohtus" / "pages" / "move.py",
    ROOT / "nohtus" / "pages" / "stocktake.py",
    ROOT / "app.py",
]


def backup(path: Path) -> Path:
    bak = path.with_name(path.name + ".bak_wms5_ui_requests")
    if bak.exists():
        raise SystemExit(f"Backup already exists: {bak.relative_to(ROOT)}. Review/remove it before running again.")
    shutil.copy2(path, bak)
    print(f"BACKUP {bak.relative_to(ROOT)}")
    return bak


def patch_move_columns(text: str) -> tuple[str, int]:
    changes = 0
    patterns = [
        r"st\.columns\(\s*\[\s*40\s*,\s*40\s*,\s*20\s*\](\s*,[^\)]*)?\)",
        r"st\.columns\(\s*\[\s*4\s*,\s*4\s*,\s*2\s*\](\s*,[^\)]*)?\)",
        r"st\.columns\(\s*\[\s*0\.4\s*,\s*0\.4\s*,\s*0\.2\s*\](\s*,[^\)]*)?\)",
    ]
    for pattern in patterns:
        def repl(match: re.Match[str]) -> str:
            nonlocal changes
            changes += 1
            suffix = match.group(1) or ""
            return f"st.columns([30, 40, 30]{suffix})"
        text = re.sub(pattern, repl, text)
    return text, changes


def patch_stocktake_zero_qty(text: str) -> tuple[str, int]:
    changes = 0
    # Remove simple SQL filters that hide zero-quantity rows in stock adjustment/search sections.
    replacements = [
        ("WHERE qty <> 0", "WHERE 1=1"),
        ("WHERE qty!=0", "WHERE 1=1"),
        ("WHERE qty > 0", "WHERE 1=1"),
        ("AND qty <> 0", ""),
        ("AND qty!=0", ""),
        ("AND qty > 0", ""),
        ("WHERE i.qty <> 0", "WHERE 1=1"),
        ("WHERE i.qty!=0", "WHERE 1=1"),
        ("WHERE i.qty > 0", "WHERE 1=1"),
        ("AND i.qty <> 0", ""),
        ("AND i.qty!=0", ""),
        ("AND i.qty > 0", ""),
    ]
    lower_markers = ["재고조정", "조정 대상", "stocktake", "adjust"]
    if any(m.lower() in text.lower() for m in lower_markers):
        for old, new in replacements:
            count = text.count(old)
            if count:
                text = text.replace(old, new)
                changes += count
    return text, changes


def main() -> None:
    touched: list[Path] = []
    backups: dict[Path, Path] = {}

    try:
        for path in CANDIDATE_FILES:
            if not path.exists():
                continue
            original = path.read_text(encoding="utf-8")
            text = original
            move_changes = 0
            stock_changes = 0

            if path.name in {"move.py", "app.py"}:
                text, move_changes = patch_move_columns(text)
            if path.name in {"stocktake.py", "app.py"}:
                text, stock_changes = patch_stocktake_zero_qty(text)

            if text != original:
                backups[path] = backup(path)
                path.write_text(text, encoding="utf-8")
                touched.append(path)
                if move_changes:
                    print(f"PATCH {path.relative_to(ROOT)}: move columns -> 30:40:30 ({move_changes})")
                if stock_changes:
                    print(f"PATCH {path.relative_to(ROOT)}: include qty=0 stock adjustment rows ({stock_changes})")

        if not touched:
            print("No matching patterns found. No files changed.")
            return

        for path in touched:
            py_compile.compile(str(path), doraise=True)
            print(f"OK compile: {path.relative_to(ROOT)}")

        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
        subprocess.run([sys.executable, "tools/smoke_check.py"], cwd=ROOT, env=env, check=True)
    except Exception:
        for path, bak in backups.items():
            shutil.copy2(bak, path)
        print("FAILED. Restored changed files from backup.")
        raise

    print("DONE. Run: python -m streamlit run app.py")


if __name__ == "__main__":
    main()
