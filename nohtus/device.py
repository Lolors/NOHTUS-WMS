import streamlit as st
import streamlit.components.v1 as components


def sync_mobile_flag():
    """브라우저 폭 기준으로 모바일 여부를 query param에 동기화한다."""
    components.html(
        """
        <script>
        try {
          const url = new URL(window.parent.location.href);
          if (url.searchParams.get("force_desktop") === "1") {
            return;
          }
          const isMobile = window.parent.innerWidth <= 768 ? "1" : "0";
          if (url.searchParams.get("wms_mobile") !== isMobile) {
            url.searchParams.set("wms_mobile", isMobile);
            window.parent.history.replaceState(null, "", url.toString());
            window.parent.location.reload();
          }
        } catch(e) {}
        </script>
        """,
        height=0,
        scrolling=False,
    )


def is_mobile():
    try:
        force_desktop = st.query_params.get("force_desktop", "0")
        if isinstance(force_desktop, list):
            force_desktop = force_desktop[0] if force_desktop else "0"
        if str(force_desktop) == "1":
            return False

        value = st.query_params.get("wms_mobile", "0")
        if isinstance(value, list):
            value = value[0] if value else "0"
        return str(value) == "1"
    except Exception:
        return False
