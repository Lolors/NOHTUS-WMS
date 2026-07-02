"""NOHTUS WMS 5.0 final import stabilization patch.

Run from repository root:

    python tools/stabilize_wms5_imports.py

Then:

    python tools/smoke_check.py
    python -m streamlit run app.py

What it fixes:
- Adds missing `date` / `datetime` imports to page modules that use them.
- Adds common standard imports only when referenced.
- Detects top-level `from app import ...` in nohtus modules and warns because it can
  create circular imports. It does not blindly move these because that needs function
  context, but it prints the exact file/line to fix.
- Specifically ensures outbound.py can use both date.today() and datetime.now().
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

TARGET_DIRS = [ROOT / "nohtus" / "pages", ROOT / "nohtus" / "services"]

IMPORT_RULES = [
    (r"(?<![\w\.])sqlite3\b", "import sqlite3"),
    (r"(?<![\w\.])json\b", "import json"),
    (r"(?<![\w\.])calendar\b", "import calendar"),
    (r"(?<![\w\.])BytesIO\b", "from io import BytesIO"),
    (r"(?<![\w\.])escape\b", "from html import escape"),
    (r"(?<![\w\.])quote\b", "from urllib.parse import quote"),
    (r"(?<![\w\.])components\b", "import streamlit.components.v1 as components"),
]


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


def merge_datetime_import(text: str) -> tuple[str, list[str]]:
    needed: set[str] = set()
    if re.search(r"(?<![\w\.])date\.today\s*\(", text) or re.search(r"(?<![\w\.])date\s*\(", text):
        needed.add("date")
    if re.search(r"(?<![\w\.])datetime\.now\s*\(", text) or re.search(r"(?<![\w\.])datetime\s*\(", text):
        needed.add("datetime")
    if not needed:
        return text, []

    match = re.search(r"^from datetime import ([^\n]+)$", text, flags=re.MULTILINE)
    if match:
        existing = {x.strip() for x in match.group(1).split(",") if x.strip()}
        merged = sorted(existing | needed)
        new_line = "from datetime import " + ", ".join(merged)
        old_line = match.group(0)
        if new_line != old_line:
            text = text.replace(old_line, new_line, 1)
            return text, [new_line]
        return text, []

    new_line = "from datetime import " + ", ".join(sorted(needed))
    return insert_imports(text, [new_line]), [new_line]


def detect_top_level_app_imports(text: str) -> list[tuple[int, str]]:
    warnings: list[tuple[int, str]] = []
    for i, line in enumerate(text.splitlines(), start=1):
        if line.startswith("def "):
            break
        if line.startswith("from app import"):
            warnings.append((i, line))
    return warnings


def patch_file(path: Path) -> tuple[bool, list[str], list[str]]:
    text = path.read_text(encoding="utf-8")
    original = text
    changes: list[str] = []
    warnings: list[str] = []

    text, dt_changes = merge_datetime_import(text)
    changes.extend(dt_changes)

    for pattern, import_line in IMPORT_RULES:
        if re.search(pattern, text) and import_line not in text:
            text = insert_imports(text, [import_line])
            changes.append(import_line)

    for line_no, line in detect_top_level_app_imports(text):
        warnings.append(f"{path.relative_to(ROOT)}:{line_no}: top-level app import can cause circular import: {line}")

    if text == original:
        return False, changes, warnings

    backup = path.with_name(path.name + ".bak_stabilize_wms5_imports")
    if backup.exists():
        raise SystemExit(f"Backup already exists: {backup.relative_to(ROOT)}. Review/remove it before running again.")
    shutil.copy2(path, backup)
    print(f"BACKUP {backup.relative_to(ROOT)}")
    path.write_text(text.rstrip() + "\n", encoding="utf-8")
    return True, changes, warnings


def main() -> None:
    touched: list[Path] = []
    all_warnings: list[str] = []

    try:
        for folder in TARGET_DIRS:
            if not folder.exists():
                continue
            for path in sorted(folder.glob("*.py")):
                if path.name == "__init__.py":
                    continue
                changed, changes, warnings = patch_file(path)
                all_warnings.extend(warnings)
                if changed:
                    touched.append(path)
                    print(f"PATCH {path.relative_to(ROOT)}")
                    for change in changes:
                        print(f"  ADD/MERGE {change}")

        for path in touched:
            py_compile.compile(str(path), doraise=True)
            print(f"OK compile: {path.relative_to(ROOT)}")

        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
        subprocess.run([sys.executable, "tools/smoke_check.py"], cwd=ROOT, env=env, check=True)
    except Exception:
        print("FAILED. Restore from generated .bak_stabilize_wms5_imports files if needed.")
        raise

    if all_warnings:
        print("\nWARNINGS:")
        for warning in all_warnings:
            print("- " + warning)

    if not touched:
        print("No import changes needed.")
    print("DONE. Run: python -m streamlit run app.py")


if __name__ == "__main__":
    main()
