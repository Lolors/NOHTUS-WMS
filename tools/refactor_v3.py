from __future__ import annotations

import ast
import builtins
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app.py"

IMPORT_RULES = {
    "st": "import streamlit as st",
    "components": "import streamlit.components.v1 as components",
    "pd": "import pandas as pd",
    "q": "from nohtus.db import q",
    "connect": "from nohtus.db import connect",
    "exec_sql": "from nohtus.db import exec_sql",
    "json": "import json",
    "re": "import re",
    "Path": "from pathlib import Path",
    "escape": "from html import escape",
    "BytesIO": "from io import BytesIO",
    "datetime": "from datetime import datetime",
    "date": "from datetime import date",
    "display_date_only": "from nohtus.dates import display_date_only",
    "normalize_exp_date": "from nohtus.dates import normalize_exp_date",
    "expiry_status": "from nohtus.dates import expiry_status",
    "insert_transaction_log": "from nohtus.services.inventory import insert_transaction_log",
    "AREA_CONFIG": "from nohtus.config import AREA_CONFIG",
    "SPECIAL_LOCATIONS": "from nohtus.config import SPECIAL_LOCATIONS",
    "COMPANIES": "from nohtus.config import COMPANIES",
    "dataframe_to_excel_bytes": "from nohtus.services.closing import dataframe_to_excel_bytes",
}

MODULE_FILES = {
    "location_map": ROOT / "nohtus/services/location_map.py",
    "closing": ROOT / "nohtus/services/closing.py",
    "master": ROOT / "nohtus/services/master.py",
    "stocktake": ROOT / "nohtus/services/stocktake.py",
    "outbound": ROOT / "nohtus/services/outbound.py",
    "outbound_cart": ROOT / "nohtus/services/outbound_cart.py",
    "outbound_orders": ROOT / "nohtus/services/outbound_orders.py",
    "inbound": ROOT / "nohtus/services/inbound.py",
}


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write(path: Path, text: str) -> None:
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def parse(path: Path) -> ast.Module:
    return ast.parse(read(path), filename=str(path))


def top_level_defs(path: Path) -> dict[str, ast.FunctionDef]:
    tree = parse(path)
    return {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}


def node_source(path: Path, node: ast.AST) -> str:
    lines = read(path).splitlines()
    return "\n".join(lines[node.lineno - 1 : node.end_lineno])


def imported_names(tree: ast.Module) -> set[str]:
    names = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.asname or alias.name)
    return names


def defined_names(tree: ast.Module) -> set[str]:
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


def used_names(tree: ast.Module) -> set[str]:
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            names.add(node.id)
    return names


def unresolved_names(path: Path) -> set[str]:
    tree = parse(path)
    known = set(dir(builtins))
    known |= imported_names(tree)
    known |= defined_names(tree)
    used = used_names(tree)
    return {x for x in used - known if not x.startswith("__")}


def import_signature(node: ast.stmt) -> str | None:
    if isinstance(node, ast.Import):
        return ast.unparse(node).strip()
    if isinstance(node, ast.ImportFrom):
        return ast.unparse(node).strip()
    return None


def import_node_from_source(source: str) -> ast.stmt:
    module = ast.parse(source)
    if len(module.body) != 1 or not isinstance(module.body[0], (ast.Import, ast.ImportFrom)):
        raise ValueError(f"Not an import statement: {source}")
    return module.body[0]


def module_docstring_index(tree: ast.Module) -> int:
    if tree.body and isinstance(tree.body[0], ast.Expr) and isinstance(tree.body[0].value, ast.Constant) and isinstance(tree.body[0].value.value, str):
        return 1
    return 0


def import_insert_index(tree: ast.Module) -> int:
    """Return a top-level AST body index after docstring, __future__, and imports."""
    idx = module_docstring_index(tree)

    while idx < len(tree.body):
        node = tree.body[idx]
        if isinstance(node, ast.ImportFrom) and node.module == "__future__":
            idx += 1
            continue
        break

    while idx < len(tree.body):
        node = tree.body[idx]
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            idx += 1
            continue
        break

    return idx


def add_imports(path: Path, imports: list[str]) -> bool:
    """Add imports using AST nodes only, never by string insertion inside functions."""
    tree = parse(path)

    existing = {sig for node in tree.body if (sig := import_signature(node))}
    nodes_to_add: list[ast.stmt] = []
    for source in imports:
        node = import_node_from_source(source)
        sig = import_signature(node)
        if sig and sig not in existing:
            nodes_to_add.append(node)
            existing.add(sig)

    if not nodes_to_add:
        return False

    idx = import_insert_index(tree)
    new_body = list(tree.body)
    new_body[idx:idx] = nodes_to_add
    tree.body = new_body

    ast.fix_missing_locations(tree)
    write(path, ast.unparse(tree))
    return True


def append_helper_from_app(target: Path, helper_name: str) -> bool:
    app_defs = top_level_defs(APP)
    if helper_name not in app_defs:
        return False

    target_text = read(target)
    if f"def {helper_name}(" in target_text:
        return False

    helper_src = node_source(APP, app_defs[helper_name])
    write(target, target_text.rstrip() + "\n\n\n" + helper_src + "\n")
    return True


def py_compile(path: Path) -> None:
    subprocess.run([sys.executable, "-m", "py_compile", str(path)], cwd=ROOT, check=True)


def smoke() -> None:
    subprocess.run([sys.executable, "tools/smoke_check.py"], cwd=ROOT, check=True)


def guard() -> None:
    guard_path = ROOT / "tools/refactor_guard.py"
    if guard_path.exists():
        subprocess.run([sys.executable, str(guard_path)], cwd=ROOT, check=True)


def repair_once(path: Path) -> bool:
    changed = False
    missing = unresolved_names(path)

    imports = [IMPORT_RULES[name] for name in sorted(missing) if name in IMPORT_RULES]
    if imports:
        changed = add_imports(path, imports) or changed

    missing = unresolved_names(path)
    for name in sorted(missing):
        changed = append_helper_from_app(path, name) or changed

    return changed


def repair(module: str) -> None:
    if module not in MODULE_FILES:
        raise SystemExit(f"Unknown module: {module}")

    path = MODULE_FILES[module]
    original = read(path)

    try:
        py_compile(path)

        for _ in range(10):
            if not repair_once(path):
                break
            py_compile(path)
        else:
            raise RuntimeError(f"repair did not stabilize: {module}")

        unresolved = unresolved_names(path)
        actionable = sorted(x for x in unresolved if x in IMPORT_RULES or x in top_level_defs(APP))
        if actionable:
            raise RuntimeError(f"unresolved after repair: {', '.join(actionable)}")

        py_compile(path)
        smoke()
        guard()
        print(f"OK repair: {module}")

    except Exception:
        write(path, original)
        print(f"ROLLBACK repair: {module}")
        raise


def doctor() -> None:
    print("NOHTUS Refactor V3 Doctor")
    print("=" * 40)

    app_defs = top_level_defs(APP)
    for name, path in MODULE_FILES.items():
        if not path.exists():
            print(f"MISS {name}: file not found")
            continue

        try:
            py_compile(path)
            missing = unresolved_names(path)
            actionable = sorted(x for x in missing if x in IMPORT_RULES or x in app_defs)
            if actionable:
                print(f"WARN {name}: {', '.join(actionable)}")
            else:
                print(f"OK   {name}")
        except Exception as e:
            print(f"FAIL {name}: {e}")

    print("=" * 40)


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python tools/refactor_v3.py doctor")
        print("  python tools/refactor_v3.py repair location_map")
        raise SystemExit(1)

    cmd = sys.argv[1]

    if cmd == "doctor":
        doctor()
    elif cmd == "repair":
        if len(sys.argv) < 3:
            raise SystemExit("repair 대상 모듈명을 입력하세요.")
        repair(sys.argv[2])
    elif cmd == "smoke":
        smoke()
    elif cmd == "guard":
        guard()
    else:
        raise SystemExit(f"Unknown command: {cmd}")


if __name__ == "__main__":
    main()
