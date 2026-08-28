"""UI helpers for NOHTUS WMS."""

from __future__ import annotations

import streamlit as st

from nohtus.config import AREA_CONFIG
from nohtus.db import q
from nohtus.locations import expand_row_range, line_group_is_reversed, make_location, parse_location


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

    if st.session_state.get("_inbound_range_cells_area") != area:
        # 구역이 바뀌면 이전 구역 기준으로 고른 범위는 더 이상 의미가 없으므로
        # 함께 비운다(그대로 두면 새 구역에서도 옛 범위가 섞여 나온다).
        st.session_state["_inbound_range_cells"] = []
        st.session_state["_inbound_range_cells_area"] = area

    cfg = AREA_CONFIG.get(area, {"lines": [], "levels": []})
    lines = list(cfg.get("lines", []))
    levels = list(cfg.get("levels", []))

    if lines and levels:
        with c2:
            st.caption("선반 그림에서 칸을 클릭/드래그로 고르세요 ↓")
        line, level = _area_grid_picker("inbound", area, lines, levels, line_default, level_default, token, label="입고 위치")
    elif lines:
        # N(기타 위치)처럼 라인 목록 자체가 실물 칸이 아니라 이름 있는 특수
        # 위치들("오른쪽 창고" 등)이라 단 개념이 없는 구역이다. 단만 비활성으로
        # 두고, 라인은 그 특수 위치 중 하나를 고르는 평범한 선택 상자로 보여준다.
        with c2:
            if line_default not in lines:
                line_default = lines[0]
            line = st.selectbox("라인", lines, index=lines.index(line_default), key=f"inbound_line_{token}")
        with c3:
            st.selectbox("단", ["선택 없음"], key=f"inbound_level_disabled_{token}", disabled=True)
            level = ""
    else:
        with c2:
            st.selectbox("라인", ["선택 없음"], key=f"inbound_line_disabled_{token}", disabled=True)
            line = ""
        with c3:
            st.selectbox("단", ["선택 없음"], key=f"inbound_level_disabled_{token}", disabled=True)
            level = ""

    loc = make_location(area, line, level)
    st.session_state["_inbound_selected_loc"] = loc
    st.session_state["_inbound_picker_defaults"] = {"area": area, "line": line, "level": level}
    return loc


def move_location_picker(default_area="A1"):
    """이동 등록의 도착 위치 선택기 — 입고 등록과 같은 3x3 선반 그림으로 고른다."""
    defaults = st.session_state.get("_move_picker_defaults", {}) or {}
    area_default = str(defaults.get("area") or default_area or "A1")
    line_default = str(defaults.get("line") or "")
    level_default = str(defaults.get("level") or "")
    token = int(st.session_state.get("_move_picker_token", 0) or 0)

    areas = [area for area in AREA_CONFIG if area != "N"] + (["N"] if "N" in AREA_CONFIG else [])
    if area_default not in areas:
        area_default = default_area if default_area in areas else areas[0]

    c1, c2, c3 = st.columns(3)
    with c1:
        area = st.selectbox(
            "구역",
            areas,
            index=areas.index(area_default),
            key=f"move_area_{token}",
            format_func=lambda value: "기타 위치" if value == "N" else value,
        )

    if st.session_state.get("_move_range_cells_area") != area:
        # 구역이 바뀌면 이전 구역 기준으로 고른 범위는 더 이상 의미가 없으므로
        # 함께 비운다(그대로 두면 새 구역에서도 옛 범위가 섞여 나온다).
        st.session_state["_move_range_cells"] = []
        st.session_state["_move_range_cells_area"] = area

    cfg = AREA_CONFIG.get(area, {"lines": [], "levels": []})
    lines = list(cfg.get("lines", []))
    levels = list(cfg.get("levels", []))

    if lines and levels:
        with c2:
            st.caption("선반 그림에서 칸을 클릭/드래그로 고르세요 ↓")
        line, level = _area_grid_picker("move", area, lines, levels, line_default, level_default, token, label="도착 위치")
    elif lines:
        # N(기타 위치)처럼 라인 목록 자체가 실물 칸이 아니라 이름 있는 특수
        # 위치들("오른쪽 창고" 등)이라 단 개념이 없는 구역이다. 단만 비활성으로
        # 두고, 라인은 그 특수 위치 중 하나를 고르는 평범한 선택 상자로 보여준다.
        with c2:
            if line_default not in lines:
                line_default = lines[0]
            line = st.selectbox("라인", lines, index=lines.index(line_default), key=f"move_line_{token}")
        with c3:
            st.selectbox("단", ["선택 없음"], key=f"move_level_disabled_{token}", disabled=True)
            level = ""
    else:
        with c2:
            st.selectbox("라인", ["선택 없음"], key=f"move_line_disabled_{token}", disabled=True)
            line = ""
        with c3:
            st.selectbox("단", ["선택 없음"], key=f"move_level_disabled_{token}", disabled=True)
            level = ""

    loc = make_location(area, line, level)
    st.session_state["_move_picker_defaults"] = {"area": area, "line": line, "level": level}
    return loc


def _area_occupied_rows(area):
    """이 구역에서 재고가 있는 행들을 범위(location_range_cells)까지 펼쳐서 반환한다.

    (행, 그 행이 실제로 차지하는 칸 목록) 튜플의 리스트. 대표 위치만 보면
    메인 로케이션맵과 달리 범위로 채워진 칸을 빈 칸으로 오인하게 되므로,
    범위 전체를 펼친 기준으로 "이미 있는 재고"를 판단한다.
    """
    df = q(
        "SELECT product_name, lot, location, location_range_cells, location_range_end, qty "
        "FROM inventory WHERE qty>0 AND location LIKE ?",
        (f"{area}-%",),
    )
    result = []
    for r in df.itertuples():
        occupied = expand_row_range(r.location, r.location_range_cells, r.location_range_end)
        result.append((r, occupied))
    return result


def _area_grid_picker(prefix, area, lines, levels, line_default, level_default, token, *, label):
    """구역의 실제 랙(3라인) 그림을 보여주고, 칸을 클릭/드래그로 라인+단(+범위)을 고르게 한다.

    입고 등록과 이동 등록이 함께 쓴다(prefix로 세션 상태 키를 구분). 메인
    로케이션 맵과 같은 그림 컴포넌트를 그대로 써서 한 칸만 클릭하면 그 칸이
    대표 위치가 되고, 여러 칸을 이어서 고르면 처음 고른 칸이 대표 위치,
    나머지는 함께 채워지는 범위가 된다. 이미 재고가 있는 칸(범위로 채워진
    칸 포함)은 점선으로 표시하고, 고른 칸에 이미 있는 재고도 바로 아래에
    보여준다.
    """
    from nohtus.ui.shelf_range_picker import render_shelf_range_picker

    range_key = f"_{prefix}_range_cells"
    defaults_key = f"_{prefix}_picker_defaults"
    reset_token_key = f"_{prefix}_shelf_reset_token"

    if line_default not in lines:
        line_default = lines[0]
    if level_default not in levels:
        level_default = levels[0]
    rack_lines = _display_rack_lines(area, lines, line_default)

    occupied_rows = _area_occupied_rows(area)
    occupied_cells = [
        {"lineIdx": li, "levelIdx": lv}
        for li, rline in enumerate(rack_lines)
        for lv, rlevel in enumerate(levels)
        if any(make_location(area, rline, rlevel) in occupied for _r, occupied in occupied_rows)
    ]

    # 범위 칸은 실제 랙 한 대(rack_lines) 안에서만 의미가 있다. 도면에서 다른
    # 랙의 라인을 클릭해 대표 위치가 다른 랙으로 넘어가면, 이전 랙 기준으로
    # 골라뒀던 범위는 화면에 보이지도 않는데 세션에만 남아있다가 저장 시
    # 함께 저장돼버리는 문제가 있었다 — 여기서 매번 걸러내 세션 값 자체를
    # 정리한다.
    extra_cells = [
        extra for extra in (st.session_state.get(range_key) or [])
        if parse_location(extra)[0] == area and parse_location(extra)[1] in rack_lines and parse_location(extra)[2] in levels
    ]
    st.session_state[range_key] = extra_cells

    # 초기 선택 = [대표 위치 자신] + [범위로 함께 채워질 칸들], 이 순서 그대로
    # 그림 컴포넌트에 씨앗값으로 넘긴다 — 맨 앞이 "대표 위치"라는 규칙을
    # 유지해야 다시 열었을 때도 어떤 칸이 대표 위치인지 헷갈리지 않는다.
    initial = []
    if line_default in rack_lines:
        initial.append({"lineIdx": rack_lines.index(line_default), "levelIdx": levels.index(level_default)})
    for extra in extra_cells:
        extra_area, extra_line, extra_level = parse_location(extra)
        initial.append({"lineIdx": rack_lines.index(extra_line), "levelIdx": levels.index(extra_level)})

    shelf_reset_token = int(st.session_state.get(reset_token_key, 0) or 0)
    selection = render_shelf_range_picker(
        rack_lines, levels, initial=initial, occupied=occupied_cells, exclusive_click=True, height=260,
        key=f"{prefix}_shelf_{token}_{area}_{shelf_reset_token}",
    )
    if selection is not None:
        cells = selection.get("cells") or []
        if cells:
            # 클릭/드래그로 고른 순서 그대로 온다: 맨 처음 고른 칸이 대표
            # 위치, 나머지가 범위다. 전부 지워버린 경우(빈 선택)는 대표
            # 위치가 하나도 없다는 뜻이라 무시하고 기존 선택을 유지한다.
            primary, *rest = cells
            line, level = primary["line"], primary["level"]
            st.session_state[defaults_key] = {"area": area, "line": line, "level": level}
            st.session_state[range_key] = [
                make_location(area, c["line"], c["level"]) for c in rest
            ]
            # 그림 컴포넌트는 서버를 한 번 거칠 때마다 칸을 다시 만들면서 "이번
            # 클릭이 반영되기 전" initial로 다시 시드하므로(내부 JS 상태가 다음
            # 렌더까지 안 남는다), 곧바로 또 클릭하면 방금 고른 칸이 누락된
            # 것처럼 취급된다. st.rerun()만 부르면 같은 key의 이번 클릭 값이
            # 안 사라져 무한 리런에 빠지므로, key에 들어가는 리셋 토큰을 먼저
            # 올려 완전히 새 위젯으로 만든 뒤 rerun한다 — 그래야 지금 막 갱신한
            # cells를 initial로 받아 정확하게 다시 마운트된다.
            st.session_state[reset_token_key] = shelf_reset_token + 1
            st.rerun()
        else:
            line = line_default if line_default in rack_lines else rack_lines[0]
            level = level_default
    else:
        line = line_default if line_default in rack_lines else rack_lines[0]
        level = level_default

    selected_locs = [make_location(area, line, level)] + list(st.session_state.get(range_key) or [])
    info_lines = []
    for loc in selected_locs:
        matches = [r for r, occupied in occupied_rows if loc in occupied]
        if matches:
            parts = [f"{r.product_name} {int(r.qty)}EA (LOT {r.lot or '-'})" for r in matches]
            info_lines.append(f"{loc}: " + ", ".join(parts))
    if len(selected_locs) > 1:
        st.caption(f"{label} {selected_locs[0]} + 범위 {len(selected_locs) - 1}칸 ({', '.join(sorted(selected_locs[1:]))})")
    if info_lines:
        st.info("이미 있는 재고\n" + "\n".join(info_lines))
    else:
        st.caption("선택한 칸 모두 현재 비어 있습니다.")
    return line, level


_RACK_LINE_GROUP_SIZE = 3


def _rack_line_group(lines, current_line):
    """구역의 라인 목록 중 실제 랙 한 대에 해당하는 3라인 묶음만 골라낸다.

    예를 들어 C1 구역의 라인이 01~06이면, 실물로는 C1-01~03이 랙 한 대이고
    C1-04~06이 별개의 랙 한 대다. 시작 위치가 속한 라인이 포함된 묶음만
    선반 그림에 보여줘야 실물과 맞는 범위만 고를 수 있다.
    """
    if not lines:
        return []
    try:
        idx = lines.index(current_line) if current_line in lines else 0
    except ValueError:
        idx = 0
    group_start = (idx // _RACK_LINE_GROUP_SIZE) * _RACK_LINE_GROUP_SIZE
    return lines[group_start:group_start + _RACK_LINE_GROUP_SIZE]


def _display_rack_lines(area, lines, current_line):
    """선반 그림에 왼쪽→오른쪽 순서로 그릴 라인 목록.

    같은 알파벳 구역 안에서 두 줄이 마주보는 구조(예: A1 앞줄 01~09 / 뒷줄
    10~15)에서는 뒷줄이 번호 오름차순과 반대로(번호가 클수록 왼쪽) 배치돼
    있으므로, 그 랙 묶음이면 화면에 그릴 순서만 뒤집는다 — 저장되는 실제
    라인 값 자체는 그대로다.
    """
    rack_lines = _rack_line_group(lines, current_line)
    if line_group_is_reversed(area, rack_lines):
        return list(reversed(rack_lines))
    return rack_lines
