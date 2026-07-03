from __future__ import annotations

import argparse, re, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app.py"
UI_DIR = ROOT / "nohtus" / "ui"

HEADER = '''"""UI helpers for NOHTUS WMS."""

from __future__ import annotations

import streamlit as st

from nohtus.config import AREA_CONFIG
from nohtus.db import q
from nohtus.locations import make_location, parse_location

'''

def find_func(text, name):
    m = re.search(rf"^def {re.escape(name)}\s*\([^\n]*\):\n", text, re.M)
    if not m:
        return None
    start = m.start()
    nxt = re.search(r"^def [A-Za-z_][A-Za-z0-9_]*\s*\([^\n]*\):\n", text[m.end():], re.M)
    end = m.end() + nxt.start() if nxt else len(text)
    return start, end

def move_ui(module, names):
    UI_DIR.mkdir(parents=True, exist_ok=True)
    target = UI_DIR / f"{module}.py"

    app = APP.read_text(encoding="utf-8")
    ui = target.read_text(encoding="utf-8") if target.exists() else HEADER

    backup = APP.with_name(APP.name + f".bak_move_ui_{module}")
    if backup.exists():
        raise SystemExit(f"Backup exists: {backup}")
    shutil.copy2(APP, backup)

    moved = []
    for name in names:
        span = find_func(app, name)
        if not span:
            print(f"SKIP missing: {name}")
            continue
        s, e = span
        block = app[s:e].strip()
        app = app[:s] + app[e:]
        if f"def {name}(" not in ui:
            ui = ui.rstrip() + "\n\n\n" + block + "\n"
        moved.append(name)
        print(f"MOVE UI: {name}")

    if not moved:
        print("No UI functions moved.")
        return

    APP.write_text(app, encoding="utf-8")
    target.write_text(ui.rstrip() + "\n", encoding="utf-8")

    subprocess.run([sys.executable, "-m", "py_compile", str(APP), str(target)], cwd=ROOT, check=True)
    subprocess.run([sys.executable, "tools/smoke_check.py"], cwd=ROOT, check=True)
    print("DONE. Review diff, then commit.")

def main():
    p = argparse.ArgumentParser()
    p.add_argument("module")
    p.add_argument("functions", nargs="+")
    args = p.parse_args()
    move_ui(args.module, args.functions)

if __name__ == "__main__":
    main()
