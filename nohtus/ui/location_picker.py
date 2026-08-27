"""UI helpers for NOHTUS WMS."""

from __future__ import annotations

import streamlit as st

from nohtus.config import AREA_CONFIG
from nohtus.db import q
from nohtus.locations import make_location, parse_location


def location_picker(prefix, default_area="A1", stock_only=False):
    """구역/라인/단 선택.
    입고 등록과 같은 조합 규칙을 사용한다.
    - 라인/단이 있는 구역은 선택 없음 없이 실제 값만 표시한다.
    - Q 구역은 라인/단 선택 없이 Q로 고정한다.
    - 라인/단이 없는 특수 구역만 비활성 선택 없음으로 표시한다.
    """
    picker_defaults = st.session_state.get(f"_{prefix}_picker_defaults", {}) or {}
    widget_suffix = ""
    if picker_defaults:
        # 외부 값으로 기본 위치를 바꿔야 하는 화면은 token suffix로 위젯을 재생성한다.
        # inbound: 도면 클릭값 반영 / move: 도착 사업장의 기존 재고 위치 자동 반영
        if prefix in ["inbound", "move"]:
            widget_suffix = f"_{st.session_state.get(f'_{prefix}_picker_token', 0)}"
        default_area = picker_defaults.get("area") or default_area

    if stock_only:
        stock_df = q("SELECT DISTINCT location FROM inventory WHERE qty>0 ORDER BY location")
        locs = stock_df["location"].tolist()
        areas = sorted({parse_location(x)[0] for x in locs}) or ["A1"]
    else:
        locs = []
        areas = list(AREA_CONFIG.keys())
    if default_area not in areas:
        default_area = areas[0]

    c1, c2, c3 = st.columns(3)
    with c1:
        area = st.selectbox("구역", areas, index=areas.index(default_area), key=f"{prefix}_area{widget_suffix}")

    cfg = AREA_CONFIG.get(area, {"lines": [], "levels": []})
    if stock_only:
        lines = sorted({parse_location(x)[1] for x in locs if parse_location(x)[0] == area and parse_location(x)[1]})
        levels = []
    else:
        lines = list(cfg.get("lines", []))
        levels = list(cfg.get("levels", []))

    default_line = str(picker_defaults.get("line", "") or "") if picker_defaults else ""
    with c2:
        if lines:
            if default_line not in lines:
                default_line = lines[0]
            line = st.selectbox("라인", lines, index=lines.index(default_line), key=f"{prefix}_line{widget_suffix}")
        else:
            st.selectbox("라인", ["선택 없음"], key=f"{prefix}_line_disabled{widget_suffix}", disabled=True)
            line = ""

    if stock_only:
        if line:
            levels = sorted({parse_location(x)[2] for x in locs if parse_location(x)[0] == area and parse_location(x)[1] == line and parse_location(x)[2]})
        else:
            levels = sorted({parse_location(x)[2] for x in locs if parse_location(x)[0] == area and parse_location(x)[2]})

    default_level = str(picker_defaults.get("level", "") or "") if picker_defaults else ""
    with c3:
        if levels:
            if default_level not in levels:
                default_level = levels[0]
            level = st.selectbox("단", levels, index=levels.index(default_level), key=f"{prefix}_level{widget_suffix}")
        else:
            st.selectbox("단", ["선택 없음"], key=f"{prefix}_level_disabled{widget_suffix}", disabled=True)
            level = ""

    if prefix == "inbound":
        st.session_state["_inbound_selected_loc"] = make_location(area, line, level)
    st.session_state[f"_{prefix}_picker_defaults"] = {"area": area, "line": line, "level": level}
    return make_location(area, line, level)


def inbound_location_picker(default_area="REC"):
    """입고 등록 전용 위치 선택기.
    도면 클릭값은 _inbound_picker_defaults/_inbound_picker_token으로 받아서
    기존 Streamlit widget key를 직접 수정하지 않고 다음 렌더에서 콤보박스 값을 동기화한다.

    운영 규칙:
    - 라인/단이 있는 구역은 "선택 없음"을 표시하지 않는다.
    - 라인/단이 없는 구역(REC/P/R1/R2/N 등)에만 선택 없음/비활성 표시가 나온다.
    """
    defaults = st.session_state.get("_inbound_picker_defaults", {}) or {}
    area_default = str(defaults.get("area") or default_area or "REC")
    line_default = str(defaults.get("line") or "")
    level_default = str(defaults.get("level") or "")
    token = int(st.session_state.get("_inbound_picker_token", 0) or 0)

    areas = [area for area in AREA_CONFIG if area != "N"] + (["N"] if "N" in AREA_CONFIG else [])
    if area_default not in areas:
        area_default = default_area if default_area in areas else areas[0]

    c1, c2, c3 = st.columns(3)
    with c1:
        area = st.selectbox(
            "구역",
            areas,
            index=areas.index(area_default),
            key=f"inbound_area_{token}",
            format_func=lambda value: "기타 위치" if value == "N" else value,
        )

    cfg = AREA_CONFIG.get(area, {"lines": [], "levels": []})
    lines = list(cfg.get("lines", []))
    with c2:
        if lines:
            if line_default not in lines:
                line_default = lines[0]
            line = st.selectbox("라인", lines, index=lines.index(line_default), key=f"inbound_line_{token}")
        else:
            st.selectbox("라인", ["선택 없음"], key=f"inbound_line_disabled_{token}", disabled=True)
            line = ""

    levels = list(cfg.get("levels", []))
    with c3:
        if levels:
            if level_default not in levels:
                level_default = levels[0]
            level = st.selectbox("단", levels, index=levels.index(level_default), key=f"inbound_level_{token}")
        else:
            st.selectbox("단", ["선택 없음"], key=f"inbound_level_disabled_{token}", disabled=True)
            level = ""

    loc = make_location(area, line, level)
    st.session_state["_inbound_selected_loc"] = loc
    st.session_state["_inbound_picker_defaults"] = {"area": area, "line": line, "level": level}
    return loc


def render_location_range_grid_picker_button(prefix, area, *, key=None):
    """"칸 그림으로 범위 선택" 버튼과, 열려 있는 동안 계속 떠 있어야 하는 모달을 함께 그린다.

    st.dialog는 그 함수를 호출한 런에서만 여는 게 아니라, 열려 있어야 하는 동안
    매 런마다 다시 호출해줘야 계속 떠 있는다(다이얼로그 내부 위젯 클릭 한 번마다
    Streamlit이 전체 스크립트를 다시 실행하기 때문). 그래서 버튼 클릭 자체가 아니라
    세션 상태 플래그로 "지금 열려 있어야 하는지"를 기억해뒀다가, 이 함수가 호출될
    때마다(=페이지가 다시 그려질 때마다) 그 플래그를 보고 다이얼로그를 다시 띄운다.
    """
    open_key = f"_{prefix}_grid_dialog_open"
    area_key = f"_{prefix}_grid_dialog_area"
    if st.button("칸 그림으로 범위 선택", key=key or f"{prefix}_grid_open", use_container_width=True):
        cfg = AREA_CONFIG.get(area, {})
        if not cfg.get("lines") or not cfg.get("levels"):
            st.toast(f"{area} 구역은 라인/단이 없어 그림으로 범위를 선택할 수 없습니다.")
        else:
            st.session_state[open_key] = True
            st.session_state[area_key] = area

    if st.session_state.get(open_key):
        dialog_area = st.session_state.get(area_key) or area
        cfg = AREA_CONFIG.get(dialog_area, {})
        lines = list(cfg.get("lines") or [])
        levels = list(cfg.get("levels") or [])
        if lines and levels:
            _location_range_grid_dialog(prefix, dialog_area, lines, levels)
        else:
            st.session_state[open_key] = False


@st.dialog("칸 범위 선택", width="large")
def _location_range_grid_dialog(prefix, area, lines, levels):
    from nohtus.ui.shelf_range_picker import render_shelf_range_picker

    sel_key = f"_{prefix}_shelf_sel"
    initial = st.session_state.get(sel_key) or {"lineLo": 0, "lineHi": 0, "levelLo": 0, "levelHi": 0}

    st.caption(f"{area} 구역 선반입니다. 파란 블록을 드래그해 옮기거나, 모서리를 끌어 범위를 늘리세요.")
    selection = render_shelf_range_picker(lines, levels, initial=initial, height=420, key=f"{prefix}_shelf_range")
    if selection:
        st.session_state[sel_key] = selection

    sel = st.session_state.get(sel_key) or initial
    start_line, end_line = sel["startLine"], sel["endLine"]
    start_level, end_level = sel["startLevel"], sel["endLevel"]
    cell_count = (sel["lineHi"] - sel["lineLo"] + 1) * (sel["levelHi"] - sel["levelLo"] + 1)
    st.info(f"선택 범위: {area}-{start_line}-{start_level} ~ {area}-{end_line}-{end_level} ({cell_count}칸)")

    apply_col, reset_col, cancel_col = st.columns(3)
    with apply_col:
        if st.button("이 범위 적용", type="primary", use_container_width=True, key=f"{prefix}_grid_apply"):
            st.session_state[f"_{prefix}_picker_defaults"] = {
                "area": area, "line": start_line, "level": start_level,
            }
            st.session_state[f"_{prefix}_picker_token"] = int(
                st.session_state.get(f"_{prefix}_picker_token", 0) or 0
            ) + 1
            st.session_state[f"_{prefix}_range_end_loc"] = make_location(area, end_line, end_level)
            st.session_state.pop(sel_key, None)
            st.session_state[f"_{prefix}_grid_dialog_open"] = False
            st.rerun()
    with reset_col:
        if st.button("다시 선택", use_container_width=True, key=f"{prefix}_grid_reset"):
            st.session_state.pop(sel_key, None)
            st.rerun()
    with cancel_col:
        if st.button("취소", use_container_width=True, key=f"{prefix}_grid_cancel"):
            st.session_state.pop(sel_key, None)
            st.session_state[f"_{prefix}_grid_dialog_open"] = False
            st.rerun()
