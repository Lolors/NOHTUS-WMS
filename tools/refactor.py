"""NOHTUS WMS local refactoring engine v4.

Run from the repository root.

Examples:

    python tools/refactor.py move-page page_outbound outbound
    python tools/refactor.py move-group master
    python tools/refactor.py fix-page outbound
    python tools/refactor.py move-service closing compare_erp_stock

v4 adds automatic imports for:

- common standard modules such as sqlite3, json, calendar, BytesIO, components
- helpers that still live in app.py, imported inside the page function at runtime
- helpers already moved to nohtus.services.*, imported at module level
- nohtus db/date/location/config helpers when detected
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
NOHTUS_DIR = ROOT / "nohtus"
PAGES_DIR = NOHTUS_DIR / "pages"
SERVICES_DIR = NOHTUS_DIR / "services"

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
    "saved_outbound": {
        "module": "saved_outbound",
        "functions": ["page_saved_outbound"],
    },
}

DEFAULT_IMPORT_ANCHORS = [
    "from nohtus.pages.master import",
    "from nohtus.pages.search import",
    "from nohtus.pages.saved_outbound import",
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
import sqlite3
from datetime import date, datetime
from html import escape
from io import BytesIO
from urllib.parse import quote

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from nohtus.config import AREA_COLOR, AREA_CONFIG, COMPANIES, INBOUND_COMPANIES, SPECIAL_LOCATIONS
from nohtus.db import connect, exec_sql, q
from nohtus.dates import display_date_only, expiry_status, normalize_exp_date
from nohtus.locations import location_picking_key, make_location, parse_location

'''

SERVICE_HEADER_TEMPLATE = '''"""{title} service functions for NOHTUS WMS.

Migrated from app.py. Keep functions independent from Streamlit whenever possible.
"""

from __future__ import annotations

import calendar
import json
import re
import sqlite3
from datetime import date, datetime
from html import escape
from io import BytesIO
from urllib.parse import quote

import pandas as pd

from nohtus.config import AREA_COLOR, AREA_CONFIG, COMPANIES, INBOUND_COMPANIES, SPECIAL_LOCATIONS
from nohtus.db import connect, exec_sql, q
from nohtus.dates import display_date_only, expiry_status, normalize_exp_date
from nohtus.locations import location_picking_key, make_location, parse_location

'''

IGNORE_RUNTIME_NAMES = {
    "abs", "all", "any", "bool", "callable", "dict", "enumerate", "filter",
    "float", "getattr", "hasattr", "int", "isinstance", "len", "list", "map",
    "max", "min", "open", "print", "range", "reversed", "round", "set", "setattr",
    "sorted", "str", "sum", "tuple", "type", "zip",
    "pd", "st", "components", "calendar", "json", "re", "sqlite3",
    "date", "datetime", "BytesIO", "escape", "quote",
    "connect", "q", "exec_sql",
    "display_date_only", "expiry_status", "normalize_exp_date",
    "location_picking_key", "make_location", "parse_location",
}

MODULE_IMPORT_RULES = [
    ("sqlite3", "import sqlite3"),
    ("json", "import json"),
    ("calendar", "import calendar"),
    ("re", "import re"),
    ("components", "import streamlit.components.v1 as components"),
    ("BytesIO", "from io import BytesIO"),
    ("escape", "from html import escape"),
    ("quote", "from urllib.parse import quote"),
]

NAMED_IMPORT_SOURCES = {
    "nohtus.db": {"connect", "exec_sql", "q"},
    "nohtus.dates": {"display_date_only", "expiry_status", "normalize_exp_date"},
    "nohtus.locations": {"location_picking_key", "make_location", "parse_location"},
    "nohtus.config": {
        "AREA_COLOR", "AREA_CONFIG", "COMPANIES", "INBOUND_COMPANIES",
        "SPECIAL_LOCATIONS", "APP_TITLE",
    },
}


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
    end = match.end() + next_match.start() if next_match else len(text)
    return start, end


def defined_functions(text: str) -> set[str]:
    return set(re.findall(r"^def ([A-Za-z_][A-Za-z0-9_]*)\s*\(", text, flags=re.MULTILINE))


def called_names(text: str) -> set[str]:
    return set(re.findall(r"(?<![\.\w])([A-Za-z_][A-Za-z0-9_]*)\s*\(", text))


def referenced_names(text: str) -> set[str]:
    return set(re.findall(r"(?<![\.\w])([A-Za-z_][A-Za-z0-9_]*)\b", text))


def imported_names(text: str) -> set[str]:
    names: set[str] = set()
    for match in re.finditer(r"^import\s+([^\n]+)$", text, flags=re.MULTILINE):
        for part in match.group(1).split(","):
            raw = part.strip()
            if " as " in raw:
                names.add(raw.split(" as ")[-1].strip())
            else:
                names.add(raw.split(".")[0].strip())
    for match in re.finditer(r"^from\s+[A-Za-z0-9_\.]+\s+import\s+([^\n]+)$", text, flags=re.MULTILINE):
        for part in match.group(1).split(","):
            raw = part.strip().strip("()")
            if not raw:
                continue
            if " as " in raw:
                names.add(raw.split(" as ")[-1].strip())
            else:
                names.add(raw.strip())
    return names


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


def insert_imports(text: str, imports: list[str]) -> str:
    imports = [line for line in imports if line not in text]
    if not imports:
        return text
    lines = text.splitlines()
    insert_at = 0
    for i, line in enumerate(lines):
        if line.startswith("from __future__ import"):
            insert_at = i + 1
            break
    while insert_at < len(lines) and lines[insert_at].strip() == "":
        insert_at += 1
    return "\n".join(lines[:insert_at] + imports + lines[insert_at:]) + "\n"


def merge_from_import(text: str, module: str, names: set[str]) -> tuple[str, str | None]:
    names = {name for name in names if name}
    if not names:
        return text, None
    pattern = re.compile(rf"^from {re.escape(module)} import ([^\n]+)$", re.MULTILINE)
    match = pattern.search(text)
    if match:
        existing = {x.strip() for x in match.group(1).split(",") if x.strip()}
        merged = sorted(existing | names)
        new_line = f"from {module} import " + ", ".join(merged)
        old_line = match.group(0)
        if new_line != old_line:
            text = text.replace(old_line, new_line, 1)
            return text, new_line
        return text, None
    new_line = f"from {module} import " + ", ".join(sorted(names))
    text = insert_imports(text, [new_line])
    return text, new_line


def service_exports() -> dict[str, str]:
    exports: dict[str, str] = {}
    if not SERVICES_DIR.exists():
        return exports
    for path in SERVICES_DIR.glob("*.py"):
        if path.name == "__init__.py":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        module = f"nohtus.services.{path.stem}"
        for name in defined_functions(text):
            exports[name] = module
    return exports


def fix_module_imports(page_text: str) -> tuple[str, list[str]]:
    imports_added: list[str] = []
    for name, import_line in MODULE_IMPORT_RULES:
        if re.search(rf"(?<![\.\w]){re.escape(name)}\b", page_text) and import_line not in page_text:
            page_text = insert_imports(page_text, [import_line])
            imports_added.append(import_line)

    needed_datetime = set()
    for name in ["date", "datetime"]:
        if re.search(rf"(?<![\.\w]){name}\s*\(", page_text):
            needed_datetime.add(name)
    page_text, added = merge_from_import(page_text, "datetime", needed_datetime)
    if added:
        imports_added.append(added)
    return page_text, imports_added


def fix_named_imports(page_text: str) -> tuple[str, list[str]]:
    names = referenced_names(page_text)
    current = imported_names(page_text)
    added_lines: list[str] = []

    for module, available in NAMED_IMPORT_SOURCES.items():
        needed = (names & available) - current
        page_text, added = merge_from_import(page_text, module, needed)
        if added:
            added_lines.append(added)
            current |= needed

    exports = service_exports()
    by_module: dict[str, set[str]] = {}
    for name in names - current:
        module = exports.get(name)
        if module:
            by_module.setdefault(module, set()).add(name)

    for module, needed in sorted(by_module.items()):
        page_text, added = merge_from_import(page_text, module, needed)
        if added:
            added_lines.append(added)
            current |= needed

    return page_text, added_lines


def inject_runtime_imports(page_text: str, app_text: str, function_names: list[str]) -> tuple[str, dict[str, list[str]]]:
    app_defs = defined_functions(app_text)
    page_defs = defined_functions(page_text)
    page_imports = imported_names(page_text)
    service_names = set(service_exports())
    injected: dict[str, list[str]] = {}

    for func_name in function_names:
        span = find_function_span(page_text, func_name)
        if not span:
            continue
        start, end = span
        block = page_text[start:end]
        calls = called_names(block)
        helpers = sorted(
            (calls & app_defs)
            - page_defs
            - page_imports
            - service_names
            - IGNORE_RUNTIME_NAMES
        )
        if not helpers:
            continue
        marker = f"def {func_name}():\n"
        import_line = "    from app import " + ", ".join(helpers) + "\n"
        if import_line not in page_text and marker in page_text:
            page_text = page_text.replace(marker, marker + import_line, 1)
            injected[func_name] = helpers
    return page_text, injected


def repair_page_text(page_text: str, app_text: str, function_names: list[str]) -> tuple[str, list[str], list[str], dict[str, list[str]]]:
    page_text, module_imports = fix_module_imports(page_text)
    page_text, named_imports = fix_named_imports(page_text)
    page_text, runtime_imports = inject_runtime_imports(page_text, app_text, function_names)
    return page_text, module_imports, named_imports, runtime_imports


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


def print_repair_summary(module_imports: list[str], named_imports: list[str], runtime_imports: dict[str, list[str]]) -> None:
    if module_imports:
        print("ADD module imports: " + "; ".join(module_imports))
    if named_imports:
        print("ADD named imports: " + "; ".join(named_imports))
    for func_name, helpers in runtime_imports.items():
        print(f"ADD runtime import inside {func_name}: {', '.join(helpers)}")


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
            app_text = ensure_import(app_text, f"from nohtus.pages.{module_name} import {', '.join(import_names)}\n")
        page_text, module_imports, named_imports, runtime_imports = repair_page_text(page_text, app_text, function_names)
        print_repair_summary(module_imports, named_imports, runtime_imports)
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


def fix_page(module_name: str, function_names: list[str] | None = None) -> None:
    if not APP.exists():
        raise SystemExit("app.py not found. Run this script from the repository root.")
    page_path = PAGES_DIR / f"{module_name}.py"
    if not page_path.exists():
        raise SystemExit(f"Page module not found: {page_path.relative_to(ROOT)}")
    label = f"refactor_fix_page_{module_name}"
    backups = [backup_file(page_path, label)]
    try:
        app_text = APP.read_text(encoding="utf-8")
        page_text = page_path.read_text(encoding="utf-8")
        target_functions = function_names or sorted(name for name in defined_functions(page_text) if name.startswith("page_"))
        if not target_functions:
            raise SystemExit(f"No page_* functions found in {page_path.relative_to(ROOT)}")
        page_text, module_imports, named_imports, runtime_imports = repair_page_text(page_text, app_text, target_functions)
        if not module_imports and not named_imports and not runtime_imports:
            print("No missing imports detected. No files changed.")
            return
        print_repair_summary(module_imports, named_imports, runtime_imports)
        page_path.write_text(page_text.rstrip() + "\n", encoding="utf-8")
        compile_and_smoke([page_path])
    except Exception:
        restore(backups)
        raise
    print("DONE. Run: streamlit run app.py")


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
        service_text, module_imports = fix_module_imports(service_text)
        service_text, named_imports = fix_named_imports(service_text)
        if module_imports:
            print("ADD module imports: " + "; ".join(module_imports))
        if named_imports:
            print("ADD named imports: " + "; ".join(named_imports))
        app_text = ensure_import(app_text, f"from nohtus.services.{module_name} import {', '.join(moved)}\n")
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
    p_fix_page = sub.add_parser("fix-page", help="Repair imports in a migrated page module")
    p_fix_page.add_argument("module_name")
    p_fix_page.add_argument("function_names", nargs="*")
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
    elif args.command == "fix-page":
        fix_page(args.module_name, args.function_names or None)
    elif args.command == "move-service":
        move_service(args.module_name, args.function_names)
    else:
        raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
