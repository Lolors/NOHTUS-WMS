import streamlit as st

from nohtus.locations import make_location, parse_location


def _inbound_js_loc_changed():
    """입고 도면 iframe에서 부모 페이지의 숨김 입력칸으로 넘긴 위치값을 받는다."""
    loc = str(st.session_state.get("_inbound_js_loc_buffer", "") or "").strip()
    if loc:
        st.session_state["_pending_inbound_loc"] = loc


def _apply_inbound_location_pending():
    pending = st.session_state.pop("_pending_inbound_loc", None)
    if not pending:
        try:
            qloc = st.query_params.get("inbound_loc", "")
            if isinstance(qloc, list):
                qloc = qloc[0] if qloc else ""
            pending = str(qloc or "").strip()
            if pending:
                try:
                    del st.query_params["inbound_loc"]
                except Exception:
                    pass
        except Exception:
            pending = ""
    if not pending:
        return
    if pending in ["Q1", "Q2", "Q"]:
        area, line, level = "Q", "", ""
    else:
        area, line, level = parse_location(pending)

    # 위젯 key(inbound_area/line/level)를 직접 수정하지 않고,
    # 별도 기본값 + 위젯 토큰으로 다음 렌더에서 콤보박스 값을 맞춘다.
    st.session_state["_inbound_picker_defaults"] = {"area": area or "REC", "line": line or "", "level": level or ""}
    st.session_state["_inbound_selected_loc"] = make_location(area or "REC", line or "", level or "")
    st.session_state["_inbound_picker_token"] = int(st.session_state.get("_inbound_picker_token", 0) or 0) + 1
