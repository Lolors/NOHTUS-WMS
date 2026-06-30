"""Fix common missing imports in migrated page modules.

This is a post-refactor repair tool for modules under nohtus/pages/.
It adds common standard-library / third-party imports when a migrated page uses
names such as sqlite3, json, calendar, re, components, BytesIO, or datetime.

Examples:

    python tools/fix_page_module_imports.py master
    python tools/fix_page_module_imports.py location_map

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

PAGES_DIR = ROOT / "nohtus" / "pages"

IMPORT_RULES = [
    ("sqlite3", "import sqlite3"),
    ("json", "import json"),
    ("calendar", "import calendar"),
    ("re", "import re"),
    ("components", "import streamlit.components.v1 as components"),
    ("BytesIO", "from io import BytesIO"),
]

DATETIME_IMPORTS = {
    "date": "date",
    "datetime": "datetime",
}


def has_import(text: str, import_line: str) -> bool:
    return import_line in text


def insert_imports(text: str, imports: list[str]) -> str:
    if not imports:
        return text

    lines = text.splitlines()
    insert_at = 0
    for i, line in enumerate(lines):
        if line.startswith("from __future__ import"):
            insert_at = i + 1
            break

    # place after future import and following blank lines
    while insert_at < len(lines) and lines[insert_at].strip() == "":
        insert_at += 1

    new_lines = lines[:insert_at] + imports + lines[insert_at:]
    return "\n".join(new_lines) + "\n"


def fix_datetime_import(text: str) -> tuple[str, list[str]]:
    needed = []
    for name in DATETIME_IMPORTS:
        if re.search(rf"(?<![\.\w]){name}\s*\(", text):
            needed.append(name)

    if not needed:
        return text, []

    existing_match = re.search(r"^from datetime import ([^\n]+)$", text, re.MULTILINE)
    if existing_match:
        existing = [x.strip() for x in existing_match.group(1).split(",")]
        merged = sorted(set(existing + needed))
        new_line = "from datetime import " + ", ".join(merged)
        old_line = existing_match.group(0)
        if new_line != old_line:
            text = text.replace(old_line, new_line, 1)
            return text, [new_line]
        return text, []

    return text, ["from datetime import " + ", ".join(sorted(set(needed)))]


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python tools/fix_page_module_imports.py <module_name>")

    module_name = sys.argv[1]
    page_path = PAGES_DIR / f"{module_name}.py"
    backup_path = page_path.with_name(page_path.name + ".bak_fix_module_imports")

    if not page_path.exists():
        raise SystemExit(f"Page module not found: {page_path.relative_to(ROOT)}")
    if backup_path.exists():
        raise SystemExit(f"Backup already exists: {backup_path.relative_to(ROOT)}. Review/remove it before running again.")

    text = page_path.read_text(encoding="utf-8")
    imports_to_add = []

    for name, import_line in IMPORT_RULES:
        if re.search(rf"(?<![\.\w]){re.escape(name)}\b", text) and not has_import(text, import_line):
            imports_to_add.append(import_line)

    text, datetime_added = fix_datetime_import(text)
    imports_to_add.extend(x for x in datetime_added if x not in text)
    imports_to_add = [x for x in imports_to_add if not has_import(text, x)]

    if not imports_to_add:
        print("No missing module imports detected. No files changed.")
        return

    shutil.copy2(page_path, backup_path)
    print(f"BACKUP {backup_path.relative_to(ROOT)}")

    text = insert_imports(text, imports_to_add)
    page_path.write_text(text, encoding="utf-8")
    print("ADD imports: " + "; ".join(imports_to_add))

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
