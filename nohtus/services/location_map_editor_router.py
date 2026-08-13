from __future__ import annotations

import sys


def activate_location_map_editor_route():
    app = sys.modules.get("nohtus.application")
    if app is None:
        return
    from nohtus.pages.location_map_editor import page_location_map_editor
    app.page_shippable_inventory = page_location_map_editor
