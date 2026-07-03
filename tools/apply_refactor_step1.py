"""Apply refactor step 1 to app.py safely.

This script performs a small, local-only migration:

- backs up app.py to app.py.bak_refactor_step1
- imports date/location helpers from nohtus modules
- removes duplicated helper function definitions from app.py when they match names
- aliases the old private picking-key name to the new helper
- compiles app.py and runs tools/smoke_check.py

Run from the repository root:

    python tools/apply_refactor_step1.py

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
BACKUP = ROOT / "app.py.bak_refactor_step1"

IMPORT_BLOCK = """from nohtus.dates import normalize_exp_date, display_date_only, expiry_status\nfrom nohtus.locations import make_location, parse_location, location_picking_key\n"""

FUNCTION_NAMES_TO_REMOVE = [
    "normalize_exp_date",
    "display_date_only",
    "expiry_status",
    "make_location",
    "parse_location",
    "_location_picking_key",
]


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

    if "from nohtus.dates import" not in text:
        anchor = "from inbound_map import render_inbound_quick_location_map\n"
        if anchor not in text:
            raise SystemExit("Import anchor not found. Stop without modifying app.py.")
        text = text.replace(anchor, anchor + IMPORT_BLOCK, 1)
        print("ADD helper imports")
    else:
        print("SKIP helper imports already present")

    for name in FUNCTION_NAMES_TO_REMOVE:
        text = remove_function(text, name)

    if "_location_picking_key = location_picking_key" not in text:
        text = text.replace(
            "from nohtus.locations import make_location, parse_location, location_picking_key\n",
            "from nohtus.locations import make_location, parse_location, location_picking_key\n\n_location_picking_key = location_picking_key\n",
            1,
        )
        print("ADD compatibility alias: _location_picking_key")

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
