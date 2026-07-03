from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

IMPORT_MAP = {
    "save_outbound_order": "nohtus.services.outbound_orders",
    "update_outbound_order": "nohtus.services.outbound_orders",
    "build_outbound_order_title": "nohtus.services.outbound",
    "outbound_excel_bytes": "nohtus.services.outbound",
    "outbound_pdf_bytes": "nohtus.services.outbound",
    "recommend_picks": "nohtus.services.outbound",
    "get_cart": "nohtus.services.outbound_cart",
    "_add_rows_to_outbound_cart": "nohtus.services.outbound_cart",
    "_cart_expiry_warnings": "nohtus.services.outbound_cart",
    "_clear_outbound_inputs_before_render": "nohtus.services.outbound_cart",
}

def merge_from_import(text, module, names):
    if not names:
        return text
    pattern = re.compile(rf"^from {re.escape(module)} import ([^\n]+)$", re.MULTILINE)
    m = pattern.search(text)
    if m:
        old = {x.strip() for x in m.group(1).split(",") if x.strip()}
        merged = sorted(old | set(names))
        return text.replace(m.group(0), f"from {module} import " + ", ".join(merged), 1)

    lines = text.splitlines()
    insert_at = 0
    for i, line in enumerate(lines):
        if line.startswith("from __future__ import"):
            insert_at = i + 1
            break
    while insert_at < len(lines) and lines[insert_at].strip() == "":
        insert_at += 1
    lines.insert(insert_at, f"from {module} import " + ", ".join(sorted(names)))
    return "\n".join(lines) + "\n"

def rewrite_one(path):
    text = path.read_text(encoding="utf-8")
    moved = {}

    pattern = re.compile(r"^(?P<indent>[ \t]*)from app import (?P<body>[^\n]+)$", re.MULTILINE)

    def repl(m):
        indent = m.group("indent")
        names = [x.strip() for x in m.group("body").split(",") if x.strip()]
        keep = []
        for name in names:
            target = IMPORT_MAP.get(name)
            if target:
                moved.setdefault(target, set()).add(name)
            else:
                keep.append(name)
        if keep:
            return indent + "from app import " + ", ".join(keep)
        return ""

    new = pattern.sub(repl, text)

    for module, names in sorted(moved.items()):
        new = merge_from_import(new, module, names)

    new = re.sub(r"\n{4,}", "\n\n\n", new)
    if new != text:
        path.write_text(new.rstrip() + "\n", encoding="utf-8")
        return True
    return False

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+")
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()

    changed = []
    for raw in args.paths:
        path = ROOT / raw
        if rewrite_one(path):
            changed.append(raw)

    if changed:
        print("UPDATED:")
        for x in changed:
            print("  " + x)
    else:
        print("No changes.")

    if args.smoke:
        subprocess.run([sys.executable, "tools/smoke_check.py"], cwd=ROOT, check=True)

if __name__ == "__main__":
    main()
