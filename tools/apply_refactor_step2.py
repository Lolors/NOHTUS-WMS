"""Apply refactor step 2 to app.py safely.

This script performs a small, local-only migration:

- backs up app.py to app.py.bak_refactor_step2
- imports DB helpers from nohtus.db
- removes duplicated connect/q/exec_sql definitions from app.py
- compiles app.py and runs tools/smoke_check.py

Run from the repository root:

    python tools/apply_refactor_step2.py

Review the diff before committing.
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

APP = ROOT / "app.py"
BACKUP = ROOT / "app.py.bak_refactor_step2"

IMPORT_LINE = "from nohtus.db import connect, q, exec_sql\n"
FUNCTION_NAMES_TO_REMOVE = ["connect", "q", "exec_sql"]


def _find_function_span(text: str, name: str) -> tuple[int, int] | None:
    pattern = re.compile(rf"^def {re.escape(name)}\s*\([^\n]*\):\n", re.MULTILINE)
    match = pattern.search(text)
    if not match:
        return None

    start = match.start()
    next_match = re.search(r"^def [A-Za-z_][A-Za-z0-9_]*\s*\([^\n]*\):\n", text[match.end():], re.MULTILINE)
    if next_match:
        end = match.end() + next_match.start()
    else:
        end = len(text)
    return start, end


def remove_function(text: str, name: str) -> str:
    span = _find_function_span(text, name)
    if not span:
        print(f"SKIP missing function: {name}")
        return text
    start, end = span
    print(f"REMOVE function: {name}")
    return text[:start] + text[end:]


def main() -> None:
    if not APP.exists():
        raise SystemExit("app.py not found. Run this script from the repository root.")

    original = APP.read_text(encoding="utf-8")
    if BACKUP.exists():
        raise SystemExit(f"Backup already exists: {BACKUP.name}. Remove it only after reviewing the previous run.")
    shutil.copy2(APP, BACKUP)
    print(f"BACKUP {BACKUP.name}")

    text = original

    if IMPORT_LINE not in text:
        anchor_candidates = [
            "from nohtus.locations import make_location, parse_location, location_picking_key\n",
            "from inbound_map import render_inbound_quick_location_map\n",
        ]
        for anchor in anchor_candidates:
            if anchor in text:
                text = text.replace(anchor, anchor + IMPORT_LINE, 1)
                print("ADD DB helper import")
                break
        else:
            raise SystemExit("Import anchor not found. Stop without modifying app.py.")
    else:
        print("SKIP DB helper import already present")

    for name in FUNCTION_NAMES_TO_REMOVE:
        text = remove_function(text, name)

    APP.write_text(text, encoding="utf-8")

    try:
        py_compile.compile(str(APP), doraise=True)
        print("OK compile: app.py")
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
        subprocess.run([sys.executable, "tools/smoke_check.py"], cwd=ROOT, env=env, check=True)
    except Exception:
        shutil.copy2(BACKUP, APP)
        print("FAILED. Restored app.py from backup.")
        raise

    print("DONE. Review the diff, then commit if it looks good.")


if __name__ == "__main__":
    main()
