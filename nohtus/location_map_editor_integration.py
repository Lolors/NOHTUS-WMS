from __future__ import annotations

import nohtus.application as application
from nohtus.pages.location_map_editor import page_location_map_editor


def main():
    original_render_sidebar = application.render_sidebar
    original_page_map = application.page_map

    def patched_render_sidebar(*args, **kwargs):
        menu = original_render_sidebar(*args, **kwargs)
        application.st.session_state["_location_map_editor_active"] = menu == "로케이션맵 편집"
        return "로케이션 맵" if menu == "로케이션맵 편집" else menu

    def patched_page_map():
        if application.st.session_state.get("_location_map_editor_active"):
            return page_location_map_editor()
        return original_page_map()

    application.render_sidebar = patched_render_sidebar
    application.page_map = patched_page_map
    return application.main()
