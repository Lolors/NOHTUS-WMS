"""Stocktake walking route: follow the area route with ascending line numbers.

Numbers within a rack remain ascending. Unmapped locations stay in the export
and follow the mapped route rather than being discarded.
"""
from __future__ import annotations

import re


def _lines(prefix, start, end):
    return tuple(f"{prefix}-{number:02d}" for number in range(start, end + 1))


# Each tuple is one stop/rack. Order follows the operator's annotated map.
STOCKTAKE_STOPS = (
    _lines("G1", 1, 3),
    _lines("A1", 1, 3), _lines("A1", 4, 6), _lines("A1", 7, 9),
    _lines("A1", 10, 12), _lines("A1", 13, 15),
    _lines("B1", 1, 3), _lines("B1", 4, 6),
    _lines("B1", 7, 9), _lines("B1", 10, 12),
    _lines("C1", 1, 3), _lines("C1", 4, 6),
    ("REC",), ("박스(기타)",),
    _lines("D1", 1, 3), _lines("D1", 4, 6),
    _lines("D1", 7, 9), _lines("D1", 10, 12),
    ("R1", "R2"), ("옷장1",), ("옷장2",), ("옷장3",), ("X2",),
    _lines("F1", 1, 3), ("Q",), ("옷장4",), ("옷장5",),
    _lines("E1", 1, 3), _lines("E1", 4, 6),
    _lines("X1", 1, 3), ("N", "기타 위치"),
    ("T1",), ("T2",), ("T3",), ("T4",), ("T5",),
    ("P",), ("다용도랙",),
)


def _normalize(value):
    return re.sub(r"[\s_-]+", "", str(value or "").upper())


_ROUTE = {_normalize(code): (stop, line)
          for stop, codes in enumerate(STOCKTAKE_STOPS)
          for line, code in enumerate(codes)}
_CODES = sorted(_ROUTE, key=len, reverse=True)


def stocktake_route_key(location):
    normalized = _normalize(location)
    for code in _CODES:
        suffix = normalized[len(code):] if normalized.startswith(code) else None
        if suffix == "" or (suffix is not None and suffix.isdigit()):
            return (*_ROUTE[code], int(suffix or 0))
    return (len(STOCKTAKE_STOPS), 0, 0)
