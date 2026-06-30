"""NOHTUS WMS local refactoring engine.

Run from the repository root.

Examples:

    python tools/refactor.py move-page page_outbound outbound
    python tools/refactor.py move-page page_closing closing
    python tools/refactor.py move-service closing erp_compare today_outbound_check
    python tools/refactor.py move-group master

Commands:

    move-page <function_name> <module_name>
        Move one Streamlit page function from app.py to nohtus/pages/<module_name>.py.

    move-service <module_name> <function_name> [function_name ...]
        Move one or more service/helper functions from app.py to nohtus/services/<module_name>.py.

    move-group <group_name>
        Move a predefined group of related page functions together.

The engine always:

- creates backups
- updates imports in app.py
- compiles changed files
- runs tools/smoke_check.py
- restores backups on failure
"""

from __future__ import annotations

import argparse
import os
import py_compile
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

APP = ROOT / "app.py"
PAGES_DIR = ROOT / "nohtus" / "pages"
SERVICES_DIR = ROOT / "nohtus" / "services"

GROUPS = {
    "closing": {
        "module": "closing",
        "functions": ["page_closing", "page_erp_stock_compare", "page_erp_data_upload"],
    },
    "master": {
        "module": "master",
        "functions": ["page_master", "page_customer_master", "page_inventory_metadata_edit"],
    },
    "search": {
        "module": "search",
        "functions": ["page_search", "page_mobile_stock_finder"],
    },
}

DEFAULT_IMPORT_ANCHORS = [
    "from nohtus.pages.master import",
    "from nohtus.pages.search import",
    "from nohtus.pages.closing import",
    "from nohtus.pages.product_matching import",
    "from nohtus.pages.outbound import",
    "from nohtus.pages.location_map import",
    "from nohtus.pages.stocktake import page_stocktake\n",
    "from nohtus.pages.move import page_move\n",
    "from nohtus.pages.history import page_history\n",
    "from nohtus.services.products import product_master_excel_bytes, import_product_master_excel, product_options\n",
    "from nohtus.services.inventory import add_inventory, move_inventory, adjust_inventory\n",
    "from nohtus.db import connect, q, exec_sql\n",
    "from inbound_map import render_inbound_quick_location_map\n",
]

PAGE_HEADER_TEMPLATE = '''"""{title} page for NOHTUS WMS.

Migrated from app.py. This module intentionally imports Streamlit because it
contains page rendering code.
"""

from __future__ import annotations

import calendar
import json
import re
from datetime import date, datetime
from io import BytesIO

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from nohtus.config import AREA_COLOR, AREA_CONFIG, COMPANIES, INBOUND_COMPANIES
from nohtus.db import connect, exec_sql, q
from nohtus.dates import display_date_only, expiry_status, normalize_exp_date
from nohtus.locations import location_picking_key, make_location, parse_location

'''

SERVICE_HEADER_TEMPLATE = '''"""{title} service functions for NOHTUS WMS.

Migrated from app.py. Keep functions independent from Streamlit whenever possible.
"""

from __future__ import annotations

from datetime import date, datetime
from io import BytesIO

import pandas as pd

from nohtus.config import AREA_COLOR, AREA_CONFIG, COMPANIES, INBOUND_COMPANIES
from nohtus.db import connect, exec_sql, q
from nohtus.dates import display_date_only, expiry_status, normalize_exp_date
from nohtus.locations import location_picking_key, make_location, parse_location

'''


@dataclass
class Backup:
    path: Path
    backup_path: Path
    existed: bool


def find_function_span(text: str, name: str) -> tuple[int, int] | None:
    pattern = re.compile(rf"^def {re.escape(name)}\s*\([^\n]*\):\n", re.MULTILINE)
    match = pattern.search(text)
    if not match:
        return None

    start = match.start()
    next_match = re.search(
        r"^def [A-Za-z_][A-Za-z0-9_]*\s*\([^\n]*\):\n",
        text[match.end():],
        re.MULTILINE,
    )
    if next_match:
        end = match.end() + next_match.start()
    else:
        end = len(text)
    return start, end


def backup_file(path: Path, label: str) -> Backup:
    backup_path = path.with_name(path.name + f".bak_{label}")
    if backup_path.exists():
        raise SystemExit(f"Backup already exists: {backup_path.relative_to(ROOT)}. Review/remove it before running again.")
    existed = path.exists()
    if existed:
        shutil.copy2(path, backup_path)
        print(f"BACKUP {backup_path.relative_to(ROOT)}")
    return Backup(path=path, backup_path=backup_path, existed=existed)


def restore(backups: list[Backup]) -> None:
    for item in backups:
        if item.existed and item.backup_path.exists():
            shutil.copy2(item.backup_path, item.path)
        elif not item.existed and item.path.exists():
            item.path.unlink()
    print("FAILED. Restored files from backup.")


def ensure_import(app_text: str, import_line: str) -> str:
    if import_line in app_text:
        print("SKIP import already present")
        return app_text

    for anchor in DEFAULT_IMPORT_ANCHORS:
        if anchor in app_text:
            if anchor.endswith("\n"):
                app_text = app_text.replace(anchor, anchor + import_line, 1)
            else:
                line_end = app_text.find("\n", app_text.find(anchor))
                app_text = app_text[: line_end + 1] + import_line + app_text[line_end + 1 :]
            print(f"ADD import: {import_line.strip()}")
            return app_text

    raise SystemExit("Import anchor not found. Stop without modifying app.py.")


def extract_functions(app_text: str, names: list[str], *, require_all: bool) -> tuple[str, list[str], list[str]]:
    blocks: list[str] = []
    moved: list[str] = []

    for name in names:
        span = find_function_span(app_text, name)
        if not span:
            if require_all:
                raise SystemExit(f"Required function not found in app.py: {name}")
            print(f"SKIP missing function: {name}")
            continue
        start, end = span
        blocks.append(app_text[start:end].strip() + "\n")
        moved.append(name)
        app_text = app_text[:start] + app_text[end:]
        print(f"MOVE function: {name}")

    return app_text, blocks, moved


def compile_and_smoke(paths: list[Path]) -> None:
    for path in paths:
        if path.exists():
            py_compile.compile(str(path), doraise=True)
            print(f"OK compile: {path.relative_to(ROOT)}")

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    subprocess.run([sys.executable, "tools/smoke_check.py"], cwd=ROOT, env=env, check=True)


def write_page_module(module_name: str, function_names: list[str], *, require_any: bool = True) -> None:
    if not APP.exists():
        raise SystemExit("app.py not found. Run this script from the repository root.")
    PAGES_DIR.mkdir(parents=True, exist_ok=True)

    page_path = PAGES_DIR / f"{module_name}.py"
    label = f"refactor_move_page_{module_name}"
    backups = [backup_file(APP, label), backup_file(page_path, label)]

    try:
        app_text = APP.read_text(encoding="utf-8")
        page_text = page_path.read_text(encoding="utf-8") if page_path.exists() else ""

        app_text, blocks, moved = extract_functions(app_text, function_names, require_all=False)
        already_present = [name for name in function_names if f"def {name}(" in page_text]
        if require_any and not moved and not already_present:
            raise SystemExit(f"None of {function_names} found in app.py or already in {page_path}.")

        if not page_text.strip():
            page_text = PAGE_HEADER_TEMPLATE.format(title=module_name.replace("_", " ").title()).rstrip()

        if blocks:
            page_text = page_text.rstrip() + "\n\n\n" + "\n".join(blocks).rstrip() + "\n"

        import_names = moved + [name for name in already_present if name not in moved]
        if import_names:
            import_line = f"from nohtus.pages.{module_name} import {', '.join(import_names)}\n"
            app_text = ensure_import(app_text, import_line)

        page_path.write_text(page_text.rstrip() + "\n", encoding="utf-8")
        APP.write_text(app_text, encoding="utf-8")
        compile_and_smoke([page_path, APP])
    except Exception:
        restore(backups)
        raise

    print("DONE. Review the diff, then commit if it looks good.")


def move_page(function_name: str, module_name: str) -> None:
    write_page_module(module_name, [function_name])


def move_group(group_name: str) -> None:
    if group_name not in GROUPS:
        available = ", ".join(sorted(GROUPS))
        raise SystemExit(f"Unknown group: {group_name}. Available groups: {available}")
    group = GROUPS[group_name]
    write_page_module(group["module"], group["functions"])


def move_service(module_name: str, function_names: list[str]) -> None:
    if not APP.exists():
        raise SystemExit("app.py not found. Run this script from the repository root.")
    SERVICES_DIR.mkdir(parents=True, exist_ok=True)

    service_path = SERVICES_DIR / f"{module_name}.py"
    label = f"refactor_move_service_{module_name}"
    backups = [backup_file(APP, label), backup_file(service_path, label)]

    try:
        app_text = APP.read_text(encoding="utf-8")
        service_text = service_path.read_text(encoding="utf-8") if service_path.exists() else ""

        app_text, blocks, moved = extract_functions(app_text, function_names, require_all=False)
        if not moved:
            raise SystemExit("No requested service functions were found in app.py. No useful changes made.")

        if not service_text.strip():
            service_text = SERVICE_HEADER_TEMPLATE.format(title=module_name.replace("_", " ").title()).rstrip()

        service_text = service_text.rstrip() + "\n\n\n" + "\n".join(blocks).rstrip() + "\n"

        import_line = f"from nohtus.services.{module_name} import {', '.join(moved)}\n"
        app_text = ensure_import(app_text, import_line)

        service_path.write_text(service_text.rstrip() + "\n", encoding="utf-8")
        APP.write_text(app_text, encoding="utf-8")
        compile_and_smoke([service_path, APP])
    except Exception:
        restore(backups)
        raise

    print("DONE. Review the diff, then commit if it looks good.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="NOHTUS WMS local refactoring engine")
    sub = parser.add_subparsers(dest="command", required=True)

    p_page = sub.add_parser("move-page", help="Move one page function to nohtus/pages/<module>.py")
    p_page.add_argument("function_name")
    p_page.add_argument("module_name")

    p_group = sub.add_parser("move-group", help="Move a predefined group of page functions")
    p_group.add_argument("group_name", choices=sorted(GROUPS))

    p_service = sub.add_parser("move-service", help="Move service/helper functions to nohtus/services/<module>.py")
    p_service.add_argument("module_name")
    p_service.add_argument("function_names", nargs="+")

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "move-page":
        move_page(args.function_name, args.module_name)
    elif args.command == "move-group":
        move_group(args.group_name)
    elif args.command == "move-service":
        move_service(args.module_name, args.function_names)
    else:
        raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
