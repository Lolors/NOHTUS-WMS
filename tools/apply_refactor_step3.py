"""Apply refactor step 3 to app.py safely.

This script moves selected inventory service functions from app.py to
nohtus/services/inventory.py, then imports them back into app.py.

Target functions:

- add_inventory
- move_inventory
- adjust_inventory

Run from the repository root after step 1 and step 2:

    python tools/apply_refactor_step3.py

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
SERVICE = ROOT / "nohtus" / "services" / "inventory.py"
BACKUP_APP = ROOT / "app.py.bak_refactor_step3"
BACKUP_SERVICE = ROOT / "nohtus" / "services" / "inventory.py.bak_refactor_step3"

TARGET_FUNCTIONS = [
    "add_inventory",
    "move_inventory",
    "adjust_inventory",
]

IMPORT_LINE = "from nohtus.services.inventory import add_inventory, move_inventory, adjust_inventory\n"
SERVICE_HEADER = '''"""Inventory service functions for NOHTUS WMS.

This module is migrated gradually from app.py. Keep functions independent from
Streamlit whenever possible.
"""

from __future__ import annotations

from datetime import datetime

from nohtus.db import connect, q

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


def extract_function(text: str, name: str) -> tuple[str, str]:
    span = _find_function_span(text, name)
    if not span:
        raise SystemExit(f"Required function not found in app.py: {name}")
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

    shutil.copy2(APP, BACKUP_APP)
    print(f"BACKUP {BACKUP_APP.name}")
    if SERVICE.exists():
        shutil.copy2(SERVICE, BACKUP_SERVICE)
        print(f"BACKUP {BACKUP_SERVICE.relative_to(ROOT)}")

    app_text = original_app
    service_text = original_service.strip()
    if not service_text:
        service_text = SERVICE_HEADER.rstrip()

    moved_blocks: list[str] = []
    for name in TARGET_FUNCTIONS:
        if f"def {name}(" in service_text:
            print(f"SKIP already in service: {name}")
            app_text = re.sub(rf"\n?def {re.escape(name)}\s*\([^\n]*\):\n.*?(?=\ndef [A-Za-z_][A-Za-z0-9_]*\s*\([^\n]*\):\n|\Z)", "\n", app_text, flags=re.S)
            continue
        app_text, block = extract_function(app_text, name)
        moved_blocks.append(block)
        print(f"MOVE function: {name}")

    if moved_blocks:
        service_text = service_text.rstrip() + "\n\n\n" + "\n".join(moved_blocks).rstrip() + "\n"

    if IMPORT_LINE not in app_text:
        anchor_candidates = [
            "from nohtus.db import connect, q, exec_sql\n",
            "from nohtus.locations import make_location, parse_location, location_picking_key\n",
            "from inbound_map import render_inbound_quick_location_map\n",
        ]
        for anchor in anchor_candidates:
            if anchor in app_text:
                app_text = app_text.replace(anchor, anchor + IMPORT_LINE, 1)
                print("ADD inventory service import")
                break
        else:
            raise SystemExit("Import anchor not found. Stop without modifying app.py.")
    else:
        print("SKIP inventory service import already present")

    SERVICE.write_text(service_text, encoding="utf-8")
    APP.write_text(app_text, encoding="utf-8")

    try:
        py_compile.compile(str(SERVICE), doraise=True)
        print("OK compile: nohtus/services/inventory.py")
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
