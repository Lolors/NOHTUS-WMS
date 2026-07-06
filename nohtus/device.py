import re

import streamlit as st
import streamlit.components.v1 as components


_MOBILE_USER_AGENT_RE = re.compile(
    r"android|iphone|ipod|ipad|mobile|windows phone|blackberry|opera mini|iemobile",
    re.IGNORECASE,
)


def _query_value(name, default=""):
    try:
        value = st.query_params.get(name, default)
        if isinstance(value, list):
            value = value[0] if value else default
        return str(value)
    except Exception:
        return str(default)


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
    if _query_value("force_desktop", "0") == "1":
        return False

    if _query_value("wms_mobile", "0") == "1":
        return True

    try:
        user_agent = st.context.headers.get("user-agent", "")
    except Exception:
        user_agent = ""
    return bool(_MOBILE_USER_AGENT_RE.search(user_agent or ""))
