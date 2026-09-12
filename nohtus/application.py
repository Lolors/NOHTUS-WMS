import streamlit as st
import streamlit.components.v1 as components

from nohtus import app_mode, bootstrap, sidebar_backup_panel
from nohtus.auth import allowed_pages_for_current_user, can_access_page, current_role, is_admin, render_user_box, require_login
import nohtus.services.export_waiting_history_patch  # noqa: F401
from nohtus.navigation import render_sidebar
from nohtus.pages.location_map_editor import _consume_save_payload
from nohtus.pages.mobile_stock_business import page_mobile_stock_finder
from nohtus.pages.registry import PAGE_REGISTRY


def main():
    bootstrap.configure_page()
    bootstrap.init_services()
    mobile_view = bootstrap.resolve_mobile_view()

    if not require_login():
        return

    if is_admin() and _consume_save_payload():
        st.info("저장 완료 창은 잠시 후 자동으로 닫힙니다.")
        components.html(
            """<script>
            setTimeout(function(){
              try {
                const opener = window.parent.opener;
                if (opener) {
                  opener.document.querySelectorAll('iframe').forEach(function(frame){
                    try { frame.contentWindow.postMessage({type:'nohtus-layout-saved'}, '*'); } catch(e) {}
                  });
                }
              } catch(e) {}
              try { window.parent.close(); } catch(e) {}
            }, 700);
            </script>""",
            height=0,
            scrolling=False,
        )
        return

    if mobile_view:
        page_mobile_stock_finder()
        return

    current_mode = app_mode.render_mode_section(current_role())
    if current_mode == "order_management":
        from nohtus.order_management_bridge import render_order_management
        render_order_management()
        return

    allowed_pages = allowed_pages_for_current_user()
    menu = render_sidebar(allowed_pages=allowed_pages)
    render_user_box()
    if is_admin():
        sidebar_backup_panel.render()
    if not can_access_page(menu):
        st.warning("이 계정은 해당 메뉴에 접근할 수 없습니다.")
        return

    page = PAGE_REGISTRY.get(menu)
    if page is not None:
        page()
