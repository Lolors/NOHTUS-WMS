"""Location helpers for NOHTUS WMS.

This module contains pure helpers for parsing, creating, and sorting warehouse
locations. It does not import Streamlit.
"""

from __future__ import annotations

import re

from .config import SPECIAL_LOCATIONS


def make_location(area: str, line: str | None = None, level: str | None = None) -> str:
    """Build a WMS location code from area, line, and level."""
    area = area or ""
    line = line or ""
    level = level or ""

    if area == "N" and line in SPECIAL_LOCATIONS:
        return line
    if area == "Q" and line in ["Q1", "Q2"]:
        return line
    if line and level:
        return f"{area}-{line}-{level}"
    if line:
        return f"{area}-{line}"
    return area


def parse_location(loc: str) -> tuple[str, str, str]:
    """Split a WMS location into area, line, and level."""
    loc = (loc or "").strip()
    if loc in SPECIAL_LOCATIONS:
        return "N", loc, ""
    parts = loc.split("-")
    area = parts[0] if parts else ""
    line = parts[1] if len(parts) >= 2 else ""
    level = parts[2] if len(parts) >= 3 else ""
    return area, line, level


def location_picking_key(loc: str) -> tuple[int, int, int, int, str]:
    """Return a stable sort key for outbound picking order."""
    loc = (loc or "").strip()
    area, line, level = parse_location(loc)
    area_order = [
        "REC", "A1", "A2", "B1", "B2", "C1", "C2", "D1", "E1", "F1",
        "G1", "G2", "X1", "X2", "Q", "N", "T1", "T2", "P", "R1", "R2",
    ]
    try:
        area_idx = area_order.index(area)
    except ValueError:
        area_idx = 999

    def _num(value: str) -> int:
        match = re.search(r"\d+", str(value or ""))
        return int(match.group()) if match else 999

    special_idx = SPECIAL_LOCATIONS.index(line) if area == "N" and line in SPECIAL_LOCATIONS else 999
    return (area_idx, special_idx, _num(line), _num(level), loc)
