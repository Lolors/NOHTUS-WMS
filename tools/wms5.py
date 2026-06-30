"""NOHTUS WMS 5.0 preparation helper.

This tool is intentionally conservative. It helps prepare the 5.0 refactor by
analyzing page dependencies and repairing imports in already-migrated page
modules.

Run from the repository root.

Examples:

    python tools/wms5.py analyze-page inbound
    python tools/wms5.py analyze-page outbound
    python tools/wms5.py fix-page outbound
    python tools/wms5.py fix-all-pages

Commands:

    analyze-page <module_or_app_function>
        Analyze dependencies for nohtus/pages/<name>.py or app.py function.

    fix-page <module_name>
        Repair imports in nohtus/pages/<module_name>.py.

    fix-all-pages
        Repair imports in all nohtus/pages/*.py modules.

The fixer adds:

- common module imports: sqlite3, json, calendar, re, BytesIO, components, etc.
- imports from nohtus.db, nohtus.config, nohtus.dates, nohtus.locations
- imports from nohtus.services.* for functions already moved into services
- local runtime imports from app.py for helpers that still remain there

It creates .bak_wms5_fix backups and runs tools/smoke_check.py after changes.
"""

from __future__ import annotations

import argparse
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
NOHTUS_DIR = ROOT / "nohtus"
PAGES_DIR = NOHTUS_DIR / "pages"
SERVICES_DIR = NOHTUS_DIR / "services"

COMMON_IMPORT_RULES = [
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
        "APP_TITLE", "AREA_COLOR", "AREA_CONFIG", "COMPANIES", "INBOUND_COMPANIES",
        "SPECIAL_LOCATIONS", "DB_PATH",
    },
}

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
            return text.replace(old_line, new_line, 1), new_line
        return text, None
    new_line = f"from {module} import " + ", ".join(sorted(names))
    return insert_imports(text, [new_line]), new_line


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


def page_function_names(text: str) -> list[str]:
    return sorted(name for name in defined_functions(text) if name.startswith("page_"))


def fix_imports(text: str, app_text: str, target_functions: list[str]) -> tuple[str, list[str]]:
    changes: list[str] = []
    names = referenced_names(text)
    current_imports = imported_names(text)

    for name, import_line in COMMON_IMPORT_RULES:
        if re.search(rf"(?<![\.\w]){re.escape(name)}\b", text) and import_line not in text:
            text = insert_imports(text, [import_line])
            changes.append(import_line)

    needed_datetime = set()
    for name in ["date", "datetime"]:
        if re.search(rf"(?<![\.\w]){name}\s*\(", text):
            needed_datetime.add(name)
    text, added = merge_from_import(text, "datetime", needed_datetime - current_imports)
    if added:
        changes.append(added)
        current_imports |= needed_datetime

    for module, available in NAMED_IMPORT_SOURCES.items():
        needed = (names & available) - current_imports
        text, added = merge_from_import(text, module, needed)
        if added:
            changes.append(added)
            current_imports |= needed

    exports = service_exports()
    by_module: dict[str, set[str]] = {}
    for name in names - current_imports:
        module = exports.get(name)
        if module:
            by_module.setdefault(module, set()).add(name)
    for module, needed in sorted(by_module.items()):
        text, added = merge_from_import(text, module, needed)
        if added:
            changes.append(added)
            current_imports |= needed

    app_defs = defined_functions(app_text)
    local_defs = defined_functions(text)
    service_names = set(exports)
    imports_now = imported_names(text)
    for func_name in target_functions:
        span = find_function_span(text, func_name)
        if not span:
            continue
        block = text[span[0]:span[1]]
        helpers = sorted(
            (called_names(block) & app_defs)
            - local_defs
            - imports_now
            - service_names
            - IGNORE_RUNTIME_NAMES
        )
        if not helpers:
            continue
        marker = f"def {func_name}():\n"
        import_line = "    from app import " + ", ".join(helpers) + "\n"
        if import_line not in text and marker in text:
            text = text.replace(marker, marker + import_line, 1)
            changes.append(f"runtime {func_name}: " + ", ".join(helpers))

    return text, changes


def smoke(paths: list[Path]) -> None:
    for path in paths:
        py_compile.compile(str(path), doraise=True)
        print(f"OK compile: {path.relative_to(ROOT)}")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    subprocess.run([sys.executable, "tools/smoke_check.py"], cwd=ROOT, env=env, check=True)


def analyze_page(name: str) -> None:
    app_text = APP.read_text(encoding="utf-8") if APP.exists() else ""
    exports = service_exports()

    page_path = PAGES_DIR / f"{name}.py"
    if page_path.exists():
        text = page_path.read_text(encoding="utf-8")
        target_functions = page_function_names(text)
        source = page_path.relative_to(ROOT)
    else:
        func_name = name if name.startswith("page_") else f"page_{name}"
        span = find_function_span(app_text, func_name)
        if not span:
            raise SystemExit(f"No page module or app.py function found for: {name}")
        text = app_text[span[0]:span[1]]
        target_functions = [func_name]
        source = Path("app.py")

    refs = referenced_names(text)
    calls = called_names(text)
    app_defs = defined_functions(app_text)
    service_refs = sorted(name for name in refs if name in exports)
    app_helper_calls = sorted((calls & app_defs) - set(target_functions) - set(service_refs) - IGNORE_RUNTIME_NAMES)
    local_defs = sorted(defined_functions(text))

    print(f"SOURCE: {source}")
    print(f"PAGE FUNCTIONS: {', '.join(target_functions) if target_functions else '-'}")
    print(f"LOCAL FUNCTIONS: {', '.join(local_defs) if local_defs else '-'}")
    print(f"SERVICE REFS: {', '.join(service_refs) if service_refs else '-'}")
    print(f"APP HELPER CALLS: {', '.join(app_helper_calls) if app_helper_calls else '-'}")
    print(f"TOTAL REFERENCED NAMES: {len(refs)}")


def fix_page(module_name: str) -> None:
    page_path = PAGES_DIR / f"{module_name}.py"
    if not page_path.exists():
        raise SystemExit(f"Page module not found: {page_path.relative_to(ROOT)}")
    backup = page_path.with_name(page_path.name + ".bak_wms5_fix")
    if backup.exists():
        raise SystemExit(f"Backup already exists: {backup.relative_to(ROOT)}. Review/remove it before running again.")

    app_text = APP.read_text(encoding="utf-8")
    text = page_path.read_text(encoding="utf-8")
    targets = page_function_names(text)
    new_text, changes = fix_imports(text, app_text, targets)
    if not changes:
        print(f"NO CHANGE: {page_path.relative_to(ROOT)}")
        return

    shutil.copy2(page_path, backup)
    print(f"BACKUP {backup.relative_to(ROOT)}")
    page_path.write_text(new_text.rstrip() + "\n", encoding="utf-8")
    for change in changes:
        print(f"ADD {change}")
    try:
        smoke([page_path])
    except Exception:
        shutil.copy2(backup, page_path)
        print("FAILED. Restored page from backup.")
        raise
    print(f"DONE: {page_path.relative_to(ROOT)}")


def fix_all_pages() -> None:
    if not PAGES_DIR.exists():
        raise SystemExit("nohtus/pages folder not found.")
    for path in sorted(PAGES_DIR.glob("*.py")):
        if path.name == "__init__.py":
            continue
        print("=" * 72)
        print(f"FIX {path.stem}")
        try:
            fix_page(path.stem)
        except SystemExit as exc:
            print(str(exc))
            print("SKIP")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="NOHTUS WMS 5.0 preparation helper")
    sub = parser.add_subparsers(dest="command", required=True)

    p_analyze = sub.add_parser("analyze-page")
    p_analyze.add_argument("name")

    p_fix = sub.add_parser("fix-page")
    p_fix.add_argument("module_name")

    sub.add_parser("fix-all-pages")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "analyze-page":
        analyze_page(args.name)
    elif args.command == "fix-page":
        fix_page(args.module_name)
    elif args.command == "fix-all-pages":
        fix_all_pages()
    else:
        raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
