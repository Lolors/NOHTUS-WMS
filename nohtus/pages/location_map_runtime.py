"""Backward-compatible location map runtime helpers.

The active location map page now lives in nohtus.pages.location_map.
This module remains temporarily so older imports do not break.
"""

from nohtus.pages.location_map import page_map, page_map_search_results
from nohtus.services.location_map import render_location_map


__all__ = [
    "page_map",
    "page_map_search_results",
    "render_location_map",
]
