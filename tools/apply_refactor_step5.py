"""Apply refactor step 5 to app.py safely.

This script moves selected history/query helper functions from app.py to
nohtus/services/history.py, then imports them back into app.py.

Unlike earlier steps, history helper names may vary by RC version. This script
uses an optional target list and moves only functions that exist in the current
app.py. If no target function is found, it stops without changing app.py.

Run from the repository root after earlier refactor steps:

    python tools/apply_refactor_step5.py

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
SERVICE = ROOT / "nohtus" / "services" / "history.py"
BACKUP_APP = ROOT / "app.py.bak_refactor_step5"
BACKUP_SERVICE = ROOT / "nohtus" / "services" / "history.py.bak_refactor_step5"

# Optional targets. The script moves only the functions that exist in app.py.
TARGET_FUNCTIONS = [
    "history_filter_key",
    "history_page_controls",
    "build_history_where_clause",
    "load_history_page",
    "transaction_history_excel_bytes",
    "history_excel_bytes",
    "export_history_excel_bytes",
]

SERVICE_HEADER = '''"""History service functions for NOHTUS WMS.

This module is migrated gradually from app.py. Keep functions independent from
Streamlit whenever possible.
"""

from __future__ import annotations

from io import BytesIO

import pandas as pd

from nohtus.db import q
from nohtus.dates import display_date_only

'''


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


def extract_function(text: str, name: str) -> tuple[str, str] | tuple[str, None]:
    span = _find_function_span(text, name)
    if not span:
        return text, None
    start, end = span
    block = text[start:end].strip() + "\n\n"
    new_text = text[:start] + text[end:]
    return new_text, block


def main() -> None:
    if not APP.exists():
        raise SystemExit("app.py not found. Run this script from the repository root.")
    if not (ROOT / "nohtus" / "services").exists():
        raise SystemExit("nohtus/services folder not found.")

    if BACKUP_APP.exists():
        raise SystemExit(f"Backup already exists: {BACKUP_APP.name}. Remove it only after reviewing the previous run.")
    if BACKUP_SERVICE.exists():
        raise SystemExit(f"Backup already exists: {BACKUP_SERVICE}. Remove it only after reviewing the previous run.")

    original_app = APP.read_text(encoding="utf-8")
    original_service = SERVICE.read_text(encoding="utf-8") if SERVICE.exists() else ""

    app_text = original_app
    service_text = original_service.strip()
    if not service_text:
        service_text = SERVICE_HEADER.rstrip()

    moved_blocks: list[str] = []
    moved_names: list[str] = []
    for name in TARGET_FUNCTIONS:
        if f"def {name}(" in service_text:
            print(f"SKIP already in service: {name}")
            span = _find_function_span(app_text, name)
            if span:
                start, end = span
                app_text = app_text[:start] + app_text[end:]
            moved_names.append(name)
            continue

        app_text, block = extract_function(app_text, name)
        if block is None:
            print(f"SKIP missing function: {name}")
            continue
        moved_blocks.append(block)
        moved_names.append(name)
        print(f"MOVE function: {name}")

    if not moved_names:
        raise SystemExit("No history helper functions found to move. No files were changed.")

    shutil.copy2(APP, BACKUP_APP)
    print(f"BACKUP {BACKUP_APP.name}")
    if SERVICE.exists():
        shutil.copy2(SERVICE, BACKUP_SERVICE)
        print(f"BACKUP {BACKUP_SERVICE.relative_to(ROOT)}")

    if moved_blocks:
        service_text = service_text.rstrip() + "\n\n\n" + "\n".join(moved_blocks).rstrip() + "\n"

    import_line = f"from nohtus.services.history import {', '.join(moved_names)}\n"
    if import_line not in app_text:
        anchor_candidates = [
            "from nohtus.services.products import product_master_excel_bytes, import_product_master_excel, product_options\n",
            "from nohtus.services.inventory import add_inventory, move_inventory, adjust_inventory\n",
            "from nohtus.db import connect, q, exec_sql\n",
            "from inbound_map import render_inbound_quick_location_map\n",
        ]
        for anchor in anchor_candidates:
            if anchor in app_text:
                app_text = app_text.replace(anchor, anchor + import_line, 1)
                print("ADD history service import")
                break
        else:
            raise SystemExit("Import anchor not found. Stop without modifying app.py.")
    else:
        print("SKIP history service import already present")

    SERVICE.write_text(service_text, encoding="utf-8")
    APP.write_text(app_text, encoding="utf-8")

    try:
        py_compile.compile(str(SERVICE), doraise=True)
        print("OK compile: nohtus/services/history.py")
        py_compile.compile(str(APP), doraise=True)
        print("OK compile: app.py")
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
        subprocess.run([sys.executable, "tools/smoke_check.py"], cwd=ROOT, env=env, check=True)
    except Exception:
        shutil.copy2(BACKUP_APP, APP)
        if BACKUP_SERVICE.exists():
            shutil.copy2(BACKUP_SERVICE, SERVICE)
        elif SERVICE.exists():
            SERVICE.unlink()
        print("FAILED. Restored files from backup.")
        raise

    print("DONE. Review the diff, then commit if it looks good.")


if __name__ == "__main__":
    main()
