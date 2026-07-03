"""NOHTUS WMS 5.0 refactoring runner.

This script is a safe wrapper around tools/refactor.py.  It does not replace the
local refactoring engine; it adds project-specific presets so large refactors can
be run locally in small, reviewable steps.

Run from the repository root.

Examples:

    python tools/refactor_wms5.py plan
    python tools/refactor_wms5.py auto-outbound
    python tools/refactor_wms5.py auto-inbound
    python tools/refactor_wms5.py clean-pycache
    python tools/refactor_wms5.py smoke

Design goals:
- never run against a dirty working tree unless --allow-dirty is given
- ignore/restore Python bytecode noise before checking the worktree
- skip functions that have already been moved
- stop on the first failed command
- always print the final git status/diff summary
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app.py"
SERVICES = ROOT / "nohtus" / "services"
PAGES = ROOT / "nohtus" / "pages"


@dataclass(frozen=True)
class MovePlan:
    module: str
    functions: tuple[str, ...]


OUTBOUND_SERVICE_PLAN = MovePlan(
    module="outbound",
    functions=(
        "sort_outbound_rows_for_picking",
        "outbound_erp_note_for_row",
        "outbound_excel_bytes",
        "outbound_pdf_bytes",
        "recommend_picks",
        "build_outbound_order_title",
        "load_outbound_order",
        "cancel_outbound_order",
        "restore_inventory_from_log",
        "cancel_saved_order",
    ),
)

OUTBOUND_ORDER_SAVE_PLAN = MovePlan(
    module="outbound_orders",
    functions=(
        "save_outbound_order",
        "update_outbound_order",
    ),
)

INBOUND_SERVICE_PLAN = MovePlan(
    module="inbound",
    functions=(
        "normalize_blank",
        "first_nonblank",
        "product_mapping_name_for",
        "ensure_inbound_first_product_mapping",
        "strip_company_stock_label",
        "inbound_company_options_for",
    ),
)


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    print("\n$ " + " ".join(cmd))
    return subprocess.run(cmd, cwd=ROOT, text=True, check=check)


def git_output(args: list[str]) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True, stderr=subprocess.STDOUT)


def _is_pycache_path(path: str) -> bool:
    normalized = path.replace("\\", "/")
    return "__pycache__/" in normalized or normalized.endswith(".pyc") or normalized.endswith(".pyo")


def clean_pycache() -> None:
    """Remove local bytecode noise and restore tracked bytecode if it still exists in old commits."""
    status = git_output(["status", "--porcelain"])
    tracked_dirty = []
    for raw in status.splitlines():
        path = raw[3:].strip()
        if _is_pycache_path(path):
            tracked_dirty.append(path)
    if tracked_dirty:
        run(["git", "restore", "--", *tracked_dirty], check=False)

    for pycache in ROOT.rglob("__pycache__"):
        if ".git" in pycache.parts:
            continue
        shutil.rmtree(pycache, ignore_errors=True)

    for pattern in ("*.pyc", "*.pyo"):
        for bytecode in ROOT.rglob(pattern):
            if ".git" in bytecode.parts:
                continue
            try:
                bytecode.unlink()
            except FileNotFoundError:
                pass


def ensure_clean_worktree(allow_dirty: bool) -> None:
    clean_pycache()
    status = git_output(["status", "--porcelain"])
    non_pycache_lines = []
    for line in status.splitlines():
        path = line[3:].strip()
        if not _is_pycache_path(path):
            non_pycache_lines.append(line)
    if non_pycache_lines and not allow_dirty:
        print("\n".join(non_pycache_lines))
        raise SystemExit("Working tree is not clean. Commit/stash changes or rerun with --allow-dirty.")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def defined_functions(text: str) -> set[str]:
    return set(re.findall(r"^def ([A-Za-z_][A-Za-z0-9_]*)\s*\(", text, flags=re.MULTILINE))


def service_path(module: str) -> Path:
    return SERVICES / f"{module}.py"


def existing_functions_in_app(functions: tuple[str, ...]) -> list[str]:
    app_defs = defined_functions(read(APP))
    return [name for name in functions if name in app_defs]


def existing_functions_in_service(module: str) -> set[str]:
    return defined_functions(read(service_path(module)))


def filter_move_candidates(plan: MovePlan, *, skip_if_target_exists: bool = True) -> list[str]:
    app_candidates = existing_functions_in_app(plan.functions)
    if not skip_if_target_exists:
        return app_candidates
    target_defs = existing_functions_in_service(plan.module)
    return [name for name in app_candidates if name not in target_defs]


def move_service(plan: MovePlan, *, skip_if_target_exists: bool = True) -> None:
    candidates = filter_move_candidates(plan, skip_if_target_exists=skip_if_target_exists)
    if not candidates:
        print(f"SKIP {plan.module}: no movable functions found in app.py")
        return
    run([sys.executable, "tools/refactor.py", "move-service", plan.module, *candidates])


def fix_page(module: str, *function_names: str) -> None:
    path = PAGES / f"{module}.py"
    if not path.exists():
        print(f"SKIP fix-page {module}: module does not exist")
        return
    cmd = [sys.executable, "tools/refactor.py", "fix-page", module]
    if function_names:
        cmd.extend(function_names)
    run(cmd)


def smoke() -> None:
    run([sys.executable, "tools/smoke_check.py"])
    clean_pycache()


def print_status() -> None:
    print("\n== git status ==")
    run(["git", "status", "--short"], check=False)
    print("\n== git diff --stat ==")
    run(["git", "diff", "--stat"], check=False)


def plan() -> None:
    app_defs = defined_functions(read(APP))
    print("== WMS5 refactor plan ==")
    for move_plan in [OUTBOUND_SERVICE_PLAN, OUTBOUND_ORDER_SAVE_PLAN, INBOUND_SERVICE_PLAN]:
        target_defs = existing_functions_in_service(move_plan.module)
        in_app = [name for name in move_plan.functions if name in app_defs]
        already_target = [name for name in move_plan.functions if name in target_defs]
        movable = [name for name in in_app if name not in target_defs]
        print(f"\n[{move_plan.module}]")
        print("  movable from app.py:", ", ".join(movable) or "-")
        print("  already in service:", ", ".join(already_target) or "-")
        missing = [name for name in move_plan.functions if name not in in_app and name not in target_defs]
        print("  missing/unknown:", ", ".join(missing) or "-")


def auto_outbound(args: argparse.Namespace) -> None:
    ensure_clean_worktree(args.allow_dirty)
    move_service(OUTBOUND_SERVICE_PLAN)
    if args.include_save_update:
        move_service(OUTBOUND_ORDER_SAVE_PLAN, skip_if_target_exists=not args.replace_existing)
    fix_page("outbound", "page_outbound")
    fix_page("saved_outbound", "page_saved_outbound")
    smoke()
    print_status()


def auto_inbound(args: argparse.Namespace) -> None:
    ensure_clean_worktree(args.allow_dirty)
    move_service(INBOUND_SERVICE_PLAN)
    fix_page("inbound", "page_inbound")
    smoke()
    print_status()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="NOHTUS WMS5 local refactoring presets")
    parser.add_argument("--allow-dirty", action="store_true", help="allow running with uncommitted changes")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("plan", help="show what can still be moved")
    sub.add_parser("smoke", help="run smoke_check.py and clean bytecode")
    sub.add_parser("clean-pycache", help="remove Python bytecode and restore tracked pycache noise")

    p_out = sub.add_parser("auto-outbound", help="move outbound helper functions and repair outbound pages")
    p_out.add_argument("--include-save-update", action="store_true", help="also try moving save/update order functions")
    p_out.add_argument("--replace-existing", action="store_true", help="do not skip functions already present in target service")

    sub.add_parser("auto-inbound", help="move inbound helper functions and repair inbound page")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "plan":
        plan()
    elif args.command == "smoke":
        smoke()
    elif args.command == "clean-pycache":
        clean_pycache()
        print_status()
    elif args.command == "auto-outbound":
        auto_outbound(args)
    elif args.command == "auto-inbound":
        auto_inbound(args)
    else:
        raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
