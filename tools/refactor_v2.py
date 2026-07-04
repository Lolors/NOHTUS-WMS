from __future__ import annotations

import ast
import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app.py"
NOHTUS = ROOT / "nohtus"

COMMON_IMPORTS = {
    "st": "import streamlit as st",
    "pd": "import pandas as pd",
    "q": "from nohtus.db import q",
    "connect": "from nohtus.db import connect",
    "exec_sql": "from nohtus.db import exec_sql",
    "datetime": "from datetime import datetime",
    "date": "from datetime import date",
    "BytesIO": "from io import BytesIO",
    "escape": "from html import escape",
    "json": "import json",
    "Path": "from pathlib import Path",
    "display_date_only": "from nohtus.dates import display_date_only",
    "normalize_exp_date": "from nohtus.dates import normalize_exp_date",
    "expiry_status": "from nohtus.dates import expiry_status",
    "insert_transaction_log": "from nohtus.services.inventory import insert_transaction_log",
}


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write(path: Path, text: str) -> None:
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def module_path(kind: str, name: str) -> Path:
    if kind == "service":
        return NOHTUS / "services" / f"{name}.py"
    if kind == "ui":
        return NOHTUS / "ui" / f"{name}.py"
    if kind == "page":
        return NOHTUS / "pages" / f"{name}.py"
    raise ValueError(kind)


def parse(text: str) -> ast.Module:
    return ast.parse(text)


def top_level_functions(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    return {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}


def node_source(text: str, node: ast.AST) -> str:
    lines = text.splitlines()
    return "\n".join(lines[node.lineno - 1: node.end_lineno])


def remove_functions(text: str, names: set[str]) -> str:
    tree = parse(text)
    spans = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in names:
            spans.append((node.lineno - 1, node.end_lineno))
    lines = text.splitlines()
    for start, end in sorted(spans, reverse=True):
        del lines[start:end]
    return "\n".join(lines) + "\n"


def used_names(source: str) -> set[str]:
    tree = parse(source)
    names = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Name):
            names.add(n.id)
    return names


def ensure_header(path: Path) -> str:
    if path.exists():
        return read(path)
    return '"""Refactored module."""\n\nfrom __future__ import annotations\n'


def remove_existing_defs(text: str, names: set[str]) -> str:
    return remove_functions(text, names)


def insert_import(text: str, line: str) -> str:
    if line in text:
        return text
    lines = text.splitlines()
    idx = 0
    if lines and lines[0].startswith('"""'):
        for i in range(1, len(lines)):
            if lines[i].strip().endswith('"""'):
                idx = i + 1
                break
    while idx < len(lines) and not lines[idx].strip():
        idx += 1
    if idx < len(lines) and lines[idx].startswith("from __future__ import"):
        idx += 1
    while idx < len(lines) and not lines[idx].strip():
        idx += 1
    lines.insert(idx, line)
    return "\n".join(lines) + "\n"


def add_common_imports(text: str, block: str) -> str:
    names = used_names(block)
    for name, imp in COMMON_IMPORTS.items():
        if name in names:
            text = insert_import(text, imp)
    return text


def validate():
    subprocess.run([sys.executable, "tools/smoke_check.py"], cwd=ROOT, check=True)
    guard = ROOT / "tools" / "refactor_guard.py"
    if guard.exists():
        subprocess.run([sys.executable, str(guard)], cwd=ROOT, check=True)


def move(kind: str, target: str, funcs: list[str], include_helpers: bool):
    app_text = read(APP)
    app_tree = parse(app_text)
    app_funcs = top_level_functions(app_tree)

    wanted = set(funcs)
    if include_helpers:
        changed = True
        while changed:
            changed = False
            source = "\n\n".join(node_source(app_text, app_funcs[n]) for n in wanted if n in app_funcs)
            refs = used_names(source)
            for ref in refs:
                if ref.startswith("_") and ref in app_funcs and ref not in wanted:
                    wanted.add(ref)
                    changed = True

    missing = [n for n in funcs if n not in app_funcs]
    if missing:
        raise SystemExit(f"Missing in app.py: {', '.join(missing)}")

    blocks = []
    for name in sorted(wanted, key=lambda x: app_funcs[x].lineno):
        if name in app_funcs:
            blocks.append(node_source(app_text, app_funcs[name]))

    target_path = module_path(kind, target)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_text = ensure_header(target_path)
    target_text = remove_existing_defs(target_text, wanted)

    moved_block = "\n\n\n".join(blocks)
    target_text = add_common_imports(target_text, moved_block)
    target_text = target_text.rstrip() + "\n\n\n" + moved_block + "\n"

    app_text = remove_functions(app_text, wanted)

    write(APP, app_text)
    write(target_path, target_text)

    subprocess.run([sys.executable, "-m", "py_compile", str(APP), str(target_path)], cwd=ROOT, check=True)
    validate()

    print("MOVED:")
    for name in sorted(wanted):
        print(" -", name)
    print("TARGET:", target_path.relative_to(ROOT))


def main():
    p = argparse.ArgumentParser(description="NOHTUS AST-based refactor engine v2")
    p.add_argument("kind", choices=["service", "ui", "page"])
    p.add_argument("target")
    p.add_argument("functions", nargs="+")
    p.add_argument("--helpers", action="store_true", help="also move private helper functions referenced by selected functions")
    args = p.parse_args()
    move(args.kind, args.target, args.functions, args.helpers)


if __name__ == "__main__":
    main()
