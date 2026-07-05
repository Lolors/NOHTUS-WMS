from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app.py"
TARGET = ROOT / "nohtus" / "services" / "location_map.py"

HEADER = '''"""Location map service helpers."""

from __future__ import annotations

import json
from html import escape
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from nohtus.config import AREA_CONFIG, SPECIAL_LOCATIONS
from nohtus.db import q
from nohtus.dates import display_date_only

'''


def extract_func_ast(path: Path, name: str) -> str:
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    lines = text.splitlines()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return "\n".join(lines[node.lineno - 1 : node.end_lineno])
    return ""


def extract_func_regex(path: Path, name: str) -> str:
    text = path.read_text(encoding="utf-8")
    match = re.search(rf"^def {re.escape(name)}\s*\([^\n]*\):\n", text, re.M)
    if not match:
        return ""
    next_match = re.search(r"^def [A-Za-z_][A-Za-z0-9_]*\s*\([^\n]*\):\n", text[match.end() :], re.M)
    end = match.end() + next_match.start() if next_match else len(text)
    return text[match.start() : end].strip()


def main() -> None:
    get_product_image_path = (
        extract_func_ast(TARGET, "get_product_image_path")
        or extract_func_ast(APP, "get_product_image_path")
        or extract_func_regex(TARGET, "get_product_image_path")
    )

    render_location_map = (
        extract_func_ast(TARGET, "render_location_map")
        or extract_func_ast(APP, "render_location_map")
        or extract_func_regex(TARGET, "render_location_map")
    )

    loc_group = (
        extract_func_ast(APP, "_loc_group_from_df")
        or extract_func_ast(TARGET, "_loc_group_from_df")
        or extract_func_regex(TARGET, "_loc_group_from_df")
    )

    missing = []
    if not get_product_image_path:
        missing.append("get_product_image_path")
    if not render_location_map:
        missing.append("render_location_map")
    if not loc_group:
        missing.append("_loc_group_from_df")

    if missing:
        raise SystemExit("함수 추출 실패: " + ", ".join(missing))

    new_text = (
        HEADER
        + get_product_image_path.strip()
        + "\n\n\n"
        + loc_group.strip()
        + "\n\n\n"
        + render_location_map.strip()
        + "\n"
    )

    TARGET.write_text(new_text, encoding="utf-8")

    subprocess.run([sys.executable, "-m", "py_compile", str(TARGET)], cwd=ROOT, check=True)
    subprocess.run([sys.executable, "tools/smoke_check.py"], cwd=ROOT, check=True)
    print("OK repaired nohtus/services/location_map.py")


if __name__ == "__main__":
    main()