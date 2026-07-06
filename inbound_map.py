import streamlit as st

from nohtus.locations import make_location, parse_location


def _apply_inbound_map_location(loc: str):
    loc = str(loc or "").strip()
    if not loc:
        return
    if loc in ["Q", "Q1", "Q2"]:
        area, line, level = "Q", "", ""
    else:
        area, line, level = parse_location(loc)
    st.session_state["_inbound_picker_defaults"] = {
        "area": area or "REC",
        "line": line or "",
        "level": level or "",
    }
    st.session_state["_inbound_selected_loc"] = make_location(area or "REC", line or "", level or "")
    st.session_state["_inbound_picker_token"] = int(st.session_state.get("_inbound_picker_token", 0) or 0) + 1


def _loc_button(loc: str, label: str | None = None):
    selected = st.session_state.get("_inbound_selected_loc", "")
    active = selected == loc or (selected and selected.startswith(str(loc) + "-"))
    if st.button(label or loc, key=f"inbound_map_btn_{loc}", use_container_width=True, type="primary" if active else "secondary"):
        _apply_inbound_map_location(loc)
        st.rerun()


def _rack(title: str, locs: list[str]):
    st.markdown(f"**{title}**")
    rows = [locs[i:i + 2] for i in range(0, len(locs), 2)]
    for row in rows:
        cols = st.columns(len(row), gap="small")
        for col, loc in zip(cols, row):
            with col:
                _loc_button(loc)


def render_inbound_quick_location_map():
    """입고 등록용 로케이션 도면.

    기존 iframe/JS 방식은 브라우저와 Streamlit rerun 타이밍에 따라 위치가 반영되지 않는 문제가 있어,
    이 화면은 Streamlit 네이티브 버튼으로 위치 선택 상태를 직접 갱신한다.
    """
    st.markdown("### 도면에서 입고 위치 선택")
    st.caption("위치를 누르면 오른쪽 입고 위치의 구역/라인/단이 바로 바뀝니다.")

    top_cols = st.columns([1.1, 1, 1, 1, 1, 1, 1.2], gap="small")
    with top_cols[0]:
        st.markdown("**G / 기타**")
        _loc_button("G2")
        g_cols = st.columns(3, gap="small")
        for c, loc in zip(g_cols, ["G1-01", "G1-02", "G1-03"]):
            with c:
                _loc_button(loc)
    with top_cols[1]:
        _rack("A2", ["A2-03", "A2-04", "A2-02", "A2-05", "A2-01", "A2-06"])
    with top_cols[2]:
        _rack("B2", ["B2-03", "B2-04", "B2-02", "B2-05", "B2-01", "B2-06"])
    with top_cols[3]:
        _rack("C2", ["C2-03", "C2-04", "C2-02", "C2-05", "C2-01", "C2-06"])
    with top_cols[4]:
        _rack("D1", ["D1-03", "D1-04", "D1-02", "D1-05", "D1-01", "D1-06"])
        _loc_button("T1")
    with top_cols[5]:
        _rack("E1", ["E1-03", "E1-04", "E1-02", "E1-05", "E1-01", "E1-06"])
        _loc_button("T2")
    with top_cols[6]:
        _rack("F1 비자료", ["F1-01", "F1-02", "F1-03"])
        _loc_button("X2")

    st.markdown("---")
    bottom_cols = st.columns([1, 1, 1, 1.2, 1.4, 1.2], gap="small")
    with bottom_cols[0]:
        st.markdown("**특수 위치**")
        _loc_button("Q", "Q 유통기간임박")
        _loc_button("P", "P 수출대기")
        _loc_button("REC", "REC 매입등록대기")
    with bottom_cols[1]:
        _rack("A1", ["A1-03", "A1-04", "A1-02", "A1-05", "A1-01", "A1-06"])
    with bottom_cols[2]:
        _rack("B1", ["B1-03", "B1-04", "B1-02", "B1-05", "B1-01", "B1-06"])
    with bottom_cols[3]:
        _rack("C1", ["C1-03", "C1-04", "C1-02", "C1-05", "C1-01", "C1-06"])
    with bottom_cols[4]:
        st.markdown("**폐기 / 자료 구분**")
        _loc_button("X1-01")
        _loc_button("X1-02")
        _loc_button("X1-03")
        _loc_button("R2", "R2 비자료")
        _loc_button("R1", "R1 자료")
    with bottom_cols[5]:
        st.markdown("**기타 위치**")
        _loc_button("홍보물랙")
        _loc_button("회색 카트")
        _loc_button("오른쪽 창고")
        _loc_button("사무실(4층)")
