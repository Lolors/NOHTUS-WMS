"""Fix missing runtime imports in nohtus/pages/location_map.py.

Use this after Step9 if location map search raises a NameError such as:

    NameError: name 'page_map_search_results' is not defined

Run from the repository root:

    python tools/fix_location_map_imports.py
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
BACKUP_PAGE = ROOT / "nohtus" / "pages" / "location_map.py.bak_fix_imports"

RUNTIME_HELPERS = [
    "page_map_search_results",
    "render_location_map",
    "render_map",
    "location_detail_panel",
    "render_location_detail",
    "inventory_summary_for_location",
    "display_product_search_results",
    "set_product_search_from_map",
]


def _find_page_func_name(text: str) -> str:
    for name in ["page_map", "page_location_map", "page_locations"]:
        if re.search(rf"^def {re.escape(name)}\s*\(\s*\):", text, re.MULTILINE):
            return name
    raise SystemExit("No location map page function found in nohtus/pages/location_map.py")


def main() -> None:
    if not PAGE.exists():
        raise SystemExit("nohtus/pages/location_map.py not found.")
    if not APP.exists():
        raise SystemExit("app.py not found.")
    if BACKUP_PAGE.exists():
        raise SystemExit(f"Backup already exists: {BACKUP_PAGE.relative_to(ROOT)}. Review/remove it before running again.")

    page_text = PAGE.read_text(encoding="utf-8")
    app_text = APP.read_text(encoding="utf-8")
    func_name = _find_page_func_name(page_text)

    used_helpers = []
    for name in RUNTIME_HELPERS:
        if re.search(rf"\b{name}\s*\(", page_text) and re.search(rf"^def {re.escape(name)}\s*\(", app_text, re.MULTILINE):
            used_helpers.append(name)

    if not used_helpers:
        print("No missing app.py runtime helpers detected. No files changed.")
        return

    shutil.copy2(PAGE, BACKUP_PAGE)
    print(f"BACKUP {BACKUP_PAGE.relative_to(ROOT)}")

    import_line = "    from app import " + ", ".join(sorted(set(used_helpers))) + "\n"
    marker = f"def {func_name}():\n"

    if import_line in page_text:
        print("Runtime import already present. No change needed.")
    elif marker in page_text:
        page_text = page_text.replace(marker, marker + import_line, 1)
        PAGE.write_text(page_text, encoding="utf-8")
        print(f"ADD runtime import inside {func_name}: {', '.join(sorted(set(used_helpers)))}")
    else:
        shutil.copy2(BACKUP_PAGE, PAGE)
        raise SystemExit(f"Could not find function marker for {func_name}.")

    try:
        py_compile.compile(str(PAGE), doraise=True)
        print("OK compile: nohtus/pages/location_map.py")
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
        subprocess.run([sys.executable, "tools/smoke_check.py"], cwd=ROOT, env=env, check=True)
    except Exception:
        shutil.copy2(BACKUP_PAGE, PAGE)
        print("FAILED. Restored location_map.py from backup.")
        raise

    print("DONE. Run: streamlit run app.py")


if __name__ == "__main__":
    main()
