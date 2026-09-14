import html
import os
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
        (function() {
          try {
            const url = new URL(window.parent.location.href);
            if (url.searchParams.get("force_desktop") === "1") {
              return;
            }
            const isMobile = window.parent.innerWidth <= 768;
            const current = url.searchParams.get("wms_mobile");
            if (isMobile && current !== "1") {
              url.searchParams.set("wms_mobile", "1");
              window.parent.history.replaceState(null, "", url.toString());
              window.parent.location.reload();
            } else if (!isMobile && current !== null) {
              url.searchParams.delete("wms_mobile");
              window.parent.history.replaceState(null, "", url.toString());
              window.parent.location.reload();
            }
          } catch(e) {}
        })();
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


def mobile_app_url():
    """새 모바일 전용 앱(mobile_app/ + nohtus/mobile_api/)의 접속 주소.

    기본값은 같은 도메인의 "/mobile" (Cloudflare Tunnel이 이미 그 경로를
    mobile_api로 넘겨주도록 설정돼 있음). NOHTUS_MOBILE_APP_URL 환경변수를
    설정하면 그 값으로 덮어쓸 수 있다 (예: 로컬 테스트 시
    http://localhost:8535, 또는 모바일 전용 서브도메인을 쓸 때).

    예전엔 이 값이 비어 있으면 기존 스트림릿 모바일 화면
    (page_mobile_stock_finder)으로 빠졌는데, 그 경로는 더 이상 쓰지 않는다.
    """
    override = str(os.environ.get("NOHTUS_MOBILE_APP_URL", "") or "").strip()
    return override or "/mobile"


def redirect_to_mobile_app(url):
    """모바일 접속을 새 앱으로 즉시 리다이렉트하고 이후 렌더링을 막는다.

    components.html()이 만드는 iframe은 sandbox 속성에 allow-top-navigation이
    없어서 그 안에서 window.parent.location을 바꾸는 스크립트는 브라우저가
    차단한다(콘솔에 "Unsafe attempt to initiate navigation" 에러). 그래서 JS
    대신, 최상위 문서에 직접 꽂히는 st.markdown으로 meta refresh를 쓴다.
    """
    safe_url = html.escape(url, quote=True)
    st.markdown(
        f'<meta http-equiv="refresh" content="0;url={safe_url}">'
        f'<div style="padding:32px 16px;text-align:center;font-size:14px;color:#6b7280;">'
        f'이동 중입니다… 자동으로 넘어가지 않으면 '
        f'<a href="{safe_url}">여기를 눌러주세요</a>.'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.stop()
