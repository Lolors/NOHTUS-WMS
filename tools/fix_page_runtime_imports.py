"""Fix missing runtime imports in migrated page modules.

When a page function is moved from app.py to nohtus/pages/*.py, it may still call
helper functions that remain in app.py. This script scans a page module, finds
called helpers that are defined in app.py, and injects a local runtime import
inside the page function.

Examples:

    python tools/fix_page_runtime_imports.py outbound page_outbound
    python tools/fix_page_runtime_imports.py location_map page_map

Run from the repository root.
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
PAGES_DIR = ROOT / "nohtus" / "pages"

IGNORE_NAMES = {
    "print", "len", "str", "int", "float", "bool", "list", "dict", "set", "tuple",
    "range", "min", "max", "sum", "sorted", "round", "abs", "enumerate", "zip",
    "isinstance", "hasattr", "getattr", "setattr", "callable", "type", "open",
    "pd", "st", "q", "connect", "exec_sql", "date", "datetime", "BytesIO",
}


def find_function_span(text: str, name: str) -> tuple[int, int] | None:
    pattern = re.compile(rf"^def {re.escape(name)}\s*\([^\n]*\):\n", re.MULTILINE)
    match = pattern.search(text)
    if not match:
        return None
    start = match.start()
    next_match = re.search(r"^def [A-Za-z_][A-Za-z0-9_]*\s*\([^\n]*\):\n", text[match.end():], re.MULTILINE)
    end = match.end() + next_match.start() if next_match else len(text)
    return start, end


def defined_functions(text: str) -> set[str]:
    return set(re.findall(r"^def ([A-Za-z_][A-Za-z0-9_]*)\s*\(", text, flags=re.MULTILINE))


def called_names(text: str) -> set[str]:
    return set(re.findall(r"(?<![\.\w])([A-Za-z_][A-Za-z0-9_]*)\s*\(", text))


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("Usage: python tools/fix_page_runtime_imports.py <module_name> <page_function_name>")

    module_name = sys.argv[1]
    page_func = sys.argv[2]
    page_path = PAGES_DIR / f"{module_name}.py"
    backup_path = page_path.with_name(page_path.name + ".bak_fix_runtime_imports")

    if not APP.exists():
        raise SystemExit("app.py not found.")
    if not page_path.exists():
        raise SystemExit(f"Page module not found: {page_path.relative_to(ROOT)}")
    if backup_path.exists():
        raise SystemExit(f"Backup already exists: {backup_path.relative_to(ROOT)}. Review/remove it before running again.")

    app_text = APP.read_text(encoding="utf-8")
    page_text = page_path.read_text(encoding="utf-8")

    app_defs = defined_functions(app_text)
    span = find_function_span(page_text, page_func)
    if not span:
        raise SystemExit(f"Function not found in page module: {page_func}")

    start, end = span
    block = page_text[start:end]
    page_defs = defined_functions(page_text)
    calls = called_names(block)
    missing_helpers = sorted((calls & app_defs) - page_defs - IGNORE_NAMES)

    if not missing_helpers:
        print("No app.py runtime helpers detected. No files changed.")
        return

    shutil.copy2(page_path, backup_path)
    print(f"BACKUP {backup_path.relative_to(ROOT)}")

    marker = f"def {page_func}():\n"
    import_line = "    from app import " + ", ".join(missing_helpers) + "\n"

    if import_line in page_text:
        print("Runtime import already present. No files changed.")
        return
    if marker not in page_text:
        raise SystemExit(f"Could not find exact function marker: {marker!r}")

    page_text = page_text.replace(marker, marker + import_line, 1)
    page_path.write_text(page_text, encoding="utf-8")
    print(f"ADD runtime import inside {page_func}: {', '.join(missing_helpers)}")

    try:
        py_compile.compile(str(page_path), doraise=True)
        print(f"OK compile: {page_path.relative_to(ROOT)}")
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
        subprocess.run([sys.executable, "tools/smoke_check.py"], cwd=ROOT, env=env, check=True)
    except Exception:
        shutil.copy2(backup_path, page_path)
        print("FAILED. Restored page module from backup.")
        raise

    print("DONE. Run: streamlit run app.py")


if __name__ == "__main__":
    main()
