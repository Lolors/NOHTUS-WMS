"""로케이션 맵에서 '이동' 버튼으로 넘어온 재고 행을 이동 등록 화면에 반영한다.

로케이션 맵은 st.components.v1.html(순수 iframe)로 그려지는데, 이 iframe은
Streamlit이 `sandbox="allow-scripts allow-same-origin ..."`로만 열고
`allow-top-navigation`은 주지 않는다. 그래서 iframe 안에서
`window.top.location.assign(...)`으로 최상위 페이지 자체를 이동시키려는 시도는
브라우저가 조용히 차단한다(콘솔에만 "Unsafe attempt to initiate navigation..."
에러가 남고, 사용자 입장에서는 버튼을 눌러도 아무 일도 안 일어나는 것처럼 보인다).

허용되는 것은 같은 출처(allow-same-origin)의 부모 문서 DOM을 직접 읽고 쓰는
것뿐이다(기존 "제품명 검색" 점프의 tryParentSearch()가 쓰는 것과 같은 방식).
그래서 페이지 이동 자체는 iframe이 부모 페이지에 이미 그려져 있는 숨김
입력칸(이 모듈의 _move_js_inv_id_buffer)에 재고 id를 적어 넣고, 그 입력칸의
on_change 콜백이 실제 조회 + 세션 상태 반영 + 페이지 전환을 담당한다.
"""

from __future__ import annotations

import streamlit as st

from nohtus.db import q


def _apply_move_prefill_from_inventory_id(inventory_id):
    """재고 id 하나로 이동 등록 화면의 제품/위치 기본값(_move_prefill)을 채운다."""
    df = q(
        "SELECT id, company, product_name, warehouse_name, lot, exp_date, location, qty "
        "FROM inventory WHERE id=?",
        (int(inventory_id),),
    )
    if df.empty:
        return False
    row = df.iloc[0]
    st.session_state["_move_prefill"] = {
        "inventory_id": int(row["id"]),
        "product": str(row["product_name"] or ""),
        "lot": str(row["lot"] or ""),
        "exp": str(row["exp_date"] or ""),
        "company": str(row["company"] or ""),
        "location": str(row["location"] or ""),
    }
    st.session_state["_move_prefill_token"] = int(st.session_state.get("_move_prefill_token", 0) or 0) + 1
    return True


def _apply_move_prefill_pending():
    """쿼리 파라미터 move_inv_id(재고 id)로도 같은 사전입력을 반영한다.

    실제 로케이션 맵의 "이동" 버튼은 iframe 샌드박스 제약 때문에 이 경로를 타지
    않고 _move_js_inv_id_changed()를 쓰지만, 누군가 move_inv_id가 붙은 URL을
    직접 열거나 붙여넣는 경우를 위해 이 경로도 계속 지원한다.
    """
    pending_id = None
    try:
        raw = st.query_params.get("move_inv_id", "")
        if isinstance(raw, list):
            raw = raw[0] if raw else ""
        raw = str(raw or "").strip()
        if raw:
            pending_id = int(raw)
            try:
                del st.query_params["move_inv_id"]
            except Exception:
                pass
    except Exception:
        pending_id = None
    if not pending_id:
        return
    _apply_move_prefill_from_inventory_id(pending_id)


def _move_js_inv_id_changed():
    """로케이션 맵의 숨김 입력칸(_move_js_inv_id_buffer)에 iframe이 적어 넣은
    재고 id를 소비해, 이동 등록 화면 사전입력 + 페이지 전환을 한 번에 처리한다."""
    raw = str(st.session_state.get("_move_js_inv_id_buffer", "") or "").strip()
    if not raw:
        return
    try:
        inventory_id = int(raw)
    except ValueError:
        return
    if _apply_move_prefill_from_inventory_id(inventory_id):
        st.session_state["page"] = "이동 등록"


def render_move_js_bridge():
    """로케이션 맵 페이지에 숨겨 그려 두는 이동 버튼 브리지 입력칸.

    시각적으로는 보이지 않지만 실제 Streamlit 위젯으로 남아 있어야 iframe의
    JS가 이 입력값을 바꿔서 on_change를 트리거할 수 있다.
    """
    st.markdown(
        """<style>
        div[data-testid="stTextInput"]:has(input[aria-label="__map_move_inv_id_bridge"]) {
            position: absolute; width: 1px; height: 1px; overflow: hidden;
            opacity: 0; pointer-events: none;
        }
        </style>""",
        unsafe_allow_html=True,
    )
    st.text_input(
        "__map_move_inv_id_bridge",
        key="_move_js_inv_id_buffer",
        label_visibility="collapsed",
        on_change=_move_js_inv_id_changed,
    )
