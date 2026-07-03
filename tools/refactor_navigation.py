from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app.py"
NAV = ROOT / "nohtus" / "navigation.py"

SIDEBAR_CODE = r'''
import streamlit as st

DEFAULT_PAGE = "로케이션 맵"

def apply_query_page_redirects():
    try:
        if st.query_params.get("map_search_product", ""):
            st.session_state["page"] = "로케이션 맵"
        elif st.query_params.get("inbound_loc", ""):
            st.session_state["page"] = "입고 등록"
    except Exception:
        pass

def render_sidebar(app_title, version):
    st.sidebar.markdown(f"# {app_title}")
    st.sidebar.caption(version)

    if "page" not in st.session_state:
        st.session_state["page"] = DEFAULT_PAGE

    apply_query_page_redirects()

    def nav_button(label):
        active = st.session_state.get("page") == label
        if st.sidebar.button(label, use_container_width=True, type="primary" if active else "secondary"):
            st.session_state["page"] = label
            if label == "로케이션 맵":
                st.session_state["_scroll_map_top"] = True
            st.rerun()

    for section, labels in MENU_SECTIONS:
        if section:
            st.sidebar.markdown(f"### {section}")
        for label in labels:
            if label not in HIDDEN_PAGES:
                nav_button(label)

    return st.session_state["page"]
'''

def ensure_navigation():
    text = NAV.read_text(encoding="utf-8")
    if "def render_sidebar(" not in text:
        text = text.rstrip() + "\n\n" + SIDEBAR_CODE.strip() + "\n"
        NAV.write_text(text, encoding="utf-8")
        print("UPDATED navigation.py")

def update_app():
    text = APP.read_text(encoding="utf-8")

    if "from nohtus.navigation import render_sidebar" not in text:
        text = text.replace(
            "from nohtus.navigation import MENU_SECTIONS, HIDDEN_PAGES",
            "from nohtus.navigation import MENU_SECTIONS, HIDDEN_PAGES, render_sidebar"
        )

    start = text.find("def main():")
    if start == -1:
        raise SystemExit("def main() not found")

    end = text.find('\nif __name__ == "__main__":', start)
    if end == -1:
        raise SystemExit('__main__ block not found')

    main_block = text[start:end]

    route_start = main_block.find('    if menu == "로케이션 맵":')
    if route_start == -1:
        raise SystemExit("route block not found")

    route_block = main_block[route_start:]

    new_main = '''def main():
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    init_db()
    apply_style()
    menu = render_sidebar(APP_TITLE, VERSION)

''' + route_block

    text = text[:start] + new_main.rstrip() + "\n\n" + text[end+1:]
    APP.write_text(text, encoding="utf-8")
    print("UPDATED app.py")

def main():
    ensure_navigation()
    update_app()
    subprocess.run([sys.executable, "tools/smoke_check.py"], cwd=ROOT, check=True)

if __name__ == "__main__":
    main()
