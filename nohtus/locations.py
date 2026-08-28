"""Location helpers for NOHTUS WMS.

This module contains pure helpers for parsing, creating, and sorting warehouse
locations. It does not import Streamlit.
"""

from __future__ import annotations

import json
import re

from .config import AREA_CONFIG, SPECIAL_LOCATIONS


def make_location(area: str, line: str | None = None, level: str | None = None) -> str:
    """Build a WMS location code from area, line, and level."""
    area = area or ""
    line = line or ""
    level = level or ""

    if area == "N" and line in SPECIAL_LOCATIONS:
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


def expand_location_block(start: str, end: str) -> list[str]:
    """Expand a start/end location pair into every code in that block.

    A block covers the full line x level rectangle between the two corners
    (matching how a product physically occupies a range of shelves), not a
    depletion sequence. Falls back to ``[start]`` whenever ``end`` is empty,
    in a different area, or either endpoint isn't a real line/level for that
    area (special/bare locations, area-only codes, unknown lines, etc.).
    """
    start = (start or "").strip()
    end = (end or "").strip()
    if not start:
        return []
    if not end or end == start:
        return [start]

    start_area, start_line, start_level = parse_location(start)
    end_area, end_line, end_level = parse_location(end)
    if start_area != end_area or not start_line or not start_level or not end_line or not end_level:
        return [start]

    config = AREA_CONFIG.get(start_area)
    if not config:
        return [start]
    lines = list(config.get("lines") or [])
    levels = list(config.get("levels") or [])
    if start_line not in lines or end_line not in lines or start_level not in levels or end_level not in levels:
        return [start]

    line_i, line_j = lines.index(start_line), lines.index(end_line)
    level_i, level_j = levels.index(start_level), levels.index(end_level)
    line_lo, line_hi = min(line_i, line_j), max(line_i, line_j)
    level_lo, level_hi = min(level_i, level_j), max(level_i, level_j)

    return [
        make_location(start_area, line, level)
        for line in lines[line_lo:line_hi + 1]
        for level in levels[level_lo:level_hi + 1]
    ]


def expand_row_range(location, location_range_cells=None, location_range_end=None) -> list[str]:
    """재고 행 하나가 실제로 차지하는 모든 칸(자기 자신 포함)을 계산한다.

    location_range_cells(신규, 임의 모양의 칸 목록 - JSON 문자열 또는 리스트)가
    있으면 그대로 쓰고, 없으면 구버전 location_range_end(직사각형 끝 칸)를
    직사각형으로 펼쳐 호환한다. 메인 로케이션맵과 입고 등록의 위치 선택
    화면이 "이미 있는 재고"를 똑같은 기준으로 계산하도록 여기 한 곳에만 둔다.
    """
    loc = str(location or "").strip()
    cells = location_range_cells
    if isinstance(cells, str):
        raw = cells.strip()
        cells = None
        if raw:
            try:
                cells = json.loads(raw)
            except (ValueError, TypeError):
                cells = None
    if isinstance(cells, list) and cells:
        return sorted({loc} | {str(c) for c in cells if str(c or "").strip()})
    return expand_location_block(loc, str(location_range_end or ""))


def location_picking_key(loc: str) -> tuple[int, int, int, int, str]:
    """Return a stable sort key for outbound picking order."""
    loc = (loc or "").strip()
    area, line, level = parse_location(loc)
    area_order = [
        "REC", "A1", "B1", "C1", "D1", "E1", "F1",
        "G1", "X1", "X2", "Q", "N", "홍보물랙", "T1", "T2", "P", "R1", "R2",
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
