"""pandas 버전에 관계없이 사용할 수 있는 표 스타일 도우미."""
from __future__ import annotations


def map_cells(styler, func, subset=None):
    """Apply a cell style with the current or legacy pandas Styler API."""
    if hasattr(styler, "map"):
        return styler.map(func, subset=subset)
    return styler.applymap(func, subset=subset)
