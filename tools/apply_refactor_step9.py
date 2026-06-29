"""Apply refactor step 9 to app.py safely.

This script moves the location-map page function from app.py to
nohtus/pages/location_map.py, then imports it back into app.py using the same
function name.

Candidate function names are checked in order:

- page_map
- page_location_map
- page_locations

Run from the repository root after earlier refactor steps:

    python tools/apply_refactor_step9.py

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
PAGE = ROOT / "nohtus" / "pages" / "location_map.py"
BACKUP_APP = ROOT / "app.py.bak_refactor_step9"
BACKUP_PAGE = ROOT / "nohtus" / "pages" / "location_map.py.bak_refactor_step9"

CANDIDATE_FUNCTIONS = ["page_map", "page_location_map", "page_locations"]
PAGE_HEADER = '''"""Location map page for NOHTUS WMS.

Migrated from app.py. This module intentionally imports Streamlit because it
contains page rendering code.
"""

from __future__ import annotations

import streamlit as st

from nohtus.config import AREA_COLOR, AREA_CONFIG, COMPANIES
from nohtus.db import q
from nohtus.dates import display_date_only
from nohtus.locations import location_picking_key, parse_location
from nohtus.services.products import product_options

# Some UI/map helper functions may still live in app.py until later steps.
# The migration script injects runtime imports inside the moved page as needed.

'''

RUNTIME_HELPERS = [
    "render_location_map",
    "render_map",
    "location_detail_panel",
    "render_location_detail",
    "inventory_summary_for_location",
    "display_product_search_results",
    "set_product_search_from_map",
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


def _detect_runtime_helpers(page_block: str) -> list[str]:
    return [name for name in RUNTIME_HELPERS if re.search(rf"\b{name}\s*\(", page_block)]


def _append_runtime_app_imports(page_text: str, func_name: str, helpers: list[str]) -> str:
    if not helpers:
        return page_text
    marker = f"def {func_name}():\n"
    import_line = "    from app import " + ", ".join(helpers) + "\n"
    if import_line in page_text or marker not in page_text:
        return page_text
    return page_text.replace(marker, marker + import_line, 1)


def _find_target(app_text: str, page_text: str) -> tuple[str, tuple[int, int] | None]:
    for name in CANDIDATE_FUNCTIONS:
        span = _find_function_span(app_text, name)
        if span:
            return name, span
    for name in CANDIDATE_FUNCTIONS:
        if f"def {name}(" in page_text:
            return name, None
    raise SystemExit("No location-map page function found. No files changed.")


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

    func_name, span = _find_target(original_app, original_page)
    import_line = f"from nohtus.pages.location_map import {func_name}\n"

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
        helpers = _detect_runtime_helpers(block)
        if f"def {func_name}(" not in page_text:
            page_text = page_text.rstrip() + "\n\n\n" + block
            page_text = _append_runtime_app_imports(page_text, func_name, helpers)
            print(f"MOVE function: {func_name}")
        else:
            print(f"REMOVE duplicate from app.py: {func_name}")
    else:
        print(f"SKIP already moved: {func_name}")

    if import_line not in app_text:
        anchor_candidates = [
            "from nohtus.pages.stocktake import page_stocktake\n",
            "from nohtus.pages.move import page_move\n",
            "from nohtus.pages.history import page_history\n",
            "from nohtus.services.products import product_master_excel_bytes, import_product_master_excel, product_options\n",
            "from nohtus.db import connect, q, exec_sql\n",
            "from inbound_map import render_inbound_quick_location_map\n",
        ]
        inserted = False
        for anchor in anchor_candidates:
            if anchor in app_text:
                app_text = app_text.replace(anchor, anchor + import_line, 1)
                inserted = True
                print("ADD location-map page import")
                break
        if not inserted:
            raise SystemExit("Import anchor not found. Stop without modifying app.py.")
    else:
        print("SKIP location-map page import already present")

    PAGE.write_text(page_text.rstrip() + "\n", encoding="utf-8")
    APP.write_text(app_text, encoding="utf-8")

    try:
        py_compile.compile(str(PAGE), doraise=True)
        print("OK compile: nohtus/pages/location_map.py")
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
