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

    NOHTUS_MOBILE_APP_URL 환경변수가 설정된 경우에만 값을 반환한다.
    설정하지 않으면 빈 문자열을 반환하고, 이 경우 기존 스트림릿 모바일
    화면(page_mobile_stock_finder)이 그대로 쓰인다 — 즉 이 값을 넣기
    전까지는 아무 동작도 바뀌지 않는다.

    로컬 테스트: NOHTUS_MOBILE_APP_URL=http://localhost:8535
    운영(도메인+Cloudflare): 모바일 앱을 위한 서브도메인을 Cloudflare에서
    새로 만들어 mobile_api가 떠 있는 오리진(포트)으로 연결한 뒤,
    NOHTUS_MOBILE_APP_URL=https://그-서브도메인 으로 설정하면 된다.
    """
    return str(os.environ.get("NOHTUS_MOBILE_APP_URL", "") or "").strip()


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
