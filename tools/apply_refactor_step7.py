"""Apply refactor step 7 to app.py safely.

This script moves page_move() from app.py to nohtus/pages/move.py,
then imports it back into app.py using the same function name.

Run from the repository root after earlier refactor steps:

    python tools/apply_refactor_step7.py

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
PAGE = ROOT / "nohtus" / "pages" / "move.py"
BACKUP_APP = ROOT / "app.py.bak_refactor_step7"
BACKUP_PAGE = ROOT / "nohtus" / "pages" / "move.py.bak_refactor_step7"

TARGET_FUNCTION = "page_move"
IMPORT_LINE = "from nohtus.pages.move import page_move\n"
PAGE_HEADER = '''"""Move page for NOHTUS WMS.

Migrated from app.py. This module intentionally imports Streamlit because it
contains page rendering code.
"""

from __future__ import annotations

import streamlit as st

from nohtus.config import COMPANIES
from nohtus.db import q
from nohtus.dates import display_date_only
from nohtus.locations import parse_location
from nohtus.services.inventory import move_inventory
from nohtus.services.products import product_options

# These UI helpers still live in app.py until later refactor steps.
# The migration script injects compatibility imports dynamically when needed.

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


def _detect_app_helpers(page_block: str) -> list[str]:
    helper_names = [
        "location_picker",
        "display_date_only",
        "product_options",
        "move_inventory",
        "parse_location",
    ]
    return [name for name in helper_names if re.search(rf"\b{name}\s*\(", page_block)]


def _append_runtime_app_imports(page_text: str, helpers: list[str]) -> str:
    # location_picker is still in app.py at this stage. Importing app.py at module import time
    # would cause a circular import, so import it inside page_move only.
    if "location_picker" not in helpers:
        return page_text
    marker = "def page_move():\n"
    inject = "    from app import location_picker\n"
    if inject in page_text or marker not in page_text:
        return page_text
    return page_text.replace(marker, marker + inject, 1)


def main() -> None:
    if not APP.exists():
        raise SystemExit("app.py not found. Run this script from the repository root.")
    if not (ROOT / "nohtus" / "pages").exists():
        raise SystemExit("nohtus/pages folder not found.")

    if BACKUP_APP.exists():
        raise SystemExit(f"Backup already exists: {BACKUP_APP.name}. Remove it only after reviewing the previous run.")
    if BACKUP_PAGE.exists():
        raise SystemExit(f"Backup already exists: {BACKUP_PAGE}. Remove it only after reviewing the previous run.")

    original_app = APP.read_text(encoding="utf-8")
    original_page = PAGE.read_text(encoding="utf-8") if PAGE.exists() else ""

    span = _find_function_span(original_app, TARGET_FUNCTION)
    if not span and f"def {TARGET_FUNCTION}(" not in original_page:
        raise SystemExit(f"{TARGET_FUNCTION} not found in app.py and not already in page module. No files changed.")

    shutil.copy2(APP, BACKUP_APP)
    print(f"BACKUP {BACKUP_APP.name}")
    if PAGE.exists():
        shutil.copy2(PAGE, BACKUP_PAGE)
        print(f"BACKUP {BACKUP_PAGE.relative_to(ROOT)}")

    app_text = original_app
    page_text = original_page.strip()
    if not page_text:
        page_text = PAGE_HEADER.rstrip()

    if span:
        start, end = span
        block = app_text[start:end].strip() + "\n"
        app_text = app_text[:start] + app_text[end:]
        helpers = _detect_app_helpers(block)
        if f"def {TARGET_FUNCTION}(" not in page_text:
            page_text = page_text.rstrip() + "\n\n\n" + block
            page_text = _append_runtime_app_imports(page_text, helpers)
            print(f"MOVE function: {TARGET_FUNCTION}")
        else:
            print(f"REMOVE duplicate from app.py: {TARGET_FUNCTION}")
    else:
        print(f"SKIP already moved: {TARGET_FUNCTION}")

    if IMPORT_LINE not in app_text:
        anchor_candidates = [
            "from nohtus.pages.history import page_history\n",
            "from nohtus.services.history import",
            "from nohtus.services.products import product_master_excel_bytes, import_product_master_excel, product_options\n",
            "from nohtus.services.inventory import add_inventory, move_inventory, adjust_inventory\n",
            "from nohtus.db import connect, q, exec_sql\n",
            "from inbound_map import render_inbound_quick_location_map\n",
        ]
        inserted = False
        for anchor in anchor_candidates:
            if anchor in app_text:
                if anchor.endswith("\n"):
                    app_text = app_text.replace(anchor, anchor + IMPORT_LINE, 1)
                else:
                    line_end = app_text.find("\n", app_text.find(anchor))
                    app_text = app_text[:line_end+1] + IMPORT_LINE + app_text[line_end+1:]
                inserted = True
                print("ADD move page import")
                break
        if not inserted:
            raise SystemExit("Import anchor not found. Stop without modifying app.py.")
    else:
        print("SKIP move page import already present")

    PAGE.write_text(page_text.rstrip() + "\n", encoding="utf-8")
    APP.write_text(app_text, encoding="utf-8")

    try:
        py_compile.compile(str(PAGE), doraise=True)
        print("OK compile: nohtus/pages/move.py")
        py_compile.compile(str(APP), doraise=True)
        print("OK compile: app.py")
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
        subprocess.run([sys.executable, "tools/smoke_check.py"], cwd=ROOT, env=env, check=True)
    except Exception:
        shutil.copy2(BACKUP_APP, APP)
        if BACKUP_PAGE.exists():
            shutil.copy2(BACKUP_PAGE, PAGE)
        elif PAGE.exists():
            PAGE.unlink()
        print("FAILED. Restored files from backup.")
        raise

    print("DONE. Review the diff, then commit if it looks good.")


if __name__ == "__main__":
    main()
