from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NOHTUS = ROOT / "nohtus"


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def python_files():
    yield ROOT / "app.py"
    for path in NOHTUS.rglob("*.py"):
        yield path


def function_names(path: Path):
    try:
        tree = ast.parse(read(path))
    except SyntaxError as e:
        return [], [f"{rel(path)} syntax error: {e}"]

    names = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.append(node.name)
    return names, []


def check_duplicate_functions(path: Path):
    names, errors = function_names(path)
    seen = set()
    dupes = []
    for name in names:
        if name in seen:
            dupes.append(name)
        seen.add(name)

    for name in sorted(set(dupes)):
        errors.append(f"{rel(path)} duplicate function: {name}")
    return errors


def check_forbidden_imports(path: Path):
    text = read(path)
    errors = []

    normalized = rel(path)

    if normalized.startswith("nohtus/services/") and "from app import" in text:
        errors.append(f"{normalized} forbidden service import: from app import")

    if normalized.startswith("nohtus/ui/") and "from app import" in text:
        errors.append(f"{normalized} forbidden ui import: from app import")

    if normalized != "app.py":
        module_name = normalized[:-3].replace("/", ".")
        bad = f"from {module_name} import"
        if bad in text:
            errors.append(f"{normalized} self import detected: {bad}")

    return errors


def check_page_app_imports(path: Path):
    normalized = rel(path)
    if not normalized.startswith("nohtus/pages/"):
        return []
    text = read(path)
    allowed = {
        # 현재 남겨둘 예외가 있으면 여기에 추가
    }
    errors = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        if "from app import" in line and normalized not in allowed:
            errors.append(f"{normalized}:{line_no} page still imports app: {line.strip()}")
    return errors


def main() -> int:
    errors = []

    for path in python_files():
        errors.extend(check_duplicate_functions(path))
        errors.extend(check_forbidden_imports(path))
        errors.extend(check_page_app_imports(path))

    if errors:
        print("REFACTOR GUARD FAILED")
        for e in errors:
            print(" - " + e)
        return 1

    print("OK refactor guard")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
