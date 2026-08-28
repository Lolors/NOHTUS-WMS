"""UI helpers for NOHTUS WMS."""

from __future__ import annotations

import streamlit as st

from nohtus.config import AREA_CONFIG
from nohtus.db import q
from nohtus.locations import expand_row_range, make_location, parse_location


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
        with c3:
            st.caption("(도면에서 라인을 먼저 클릭해도 됩니다)")
        line, level = _inbound_grid_picker(area, lines, levels, line_default, level_default, token)
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


def _inbound_occupied_rows(area):
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


def _inbound_grid_picker(area, lines, levels, line_default, level_default, token):
    """구역의 실제 랙(3라인) 그림을 보여주고, 칸을 클릭/드래그로 라인+단(+범위)을 고르게 한다.

    메인 로케이션 맵/이동 등록의 "칸 범위 선택"과 같은 그림 컴포넌트를 그대로
    써서 한 칸만 클릭하면 그 칸이 입고 위치가 되고, 여러 칸을 이어서 고르면
    처음 고른 칸이 입고 위치, 나머지는 함께 채워지는 범위가 된다. 이미 재고가
    있는 칸(범위로 채워진 칸 포함)은 점선으로 표시하고, 고른 칸에 이미 있는
    재고도 바로 아래에 보여준다.
    """
    from nohtus.ui.shelf_range_picker import render_shelf_range_picker

    if line_default not in lines:
        line_default = lines[0]
    if level_default not in levels:
        level_default = levels[0]
    rack_lines = _rack_line_group(lines, line_default)

    occupied_rows = _inbound_occupied_rows(area)
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
        extra for extra in (st.session_state.get("_inbound_range_cells") or [])
        if parse_location(extra)[0] == area and parse_location(extra)[1] in rack_lines and parse_location(extra)[2] in levels
    ]
    st.session_state["_inbound_range_cells"] = extra_cells

    # 초기 선택 = [입고 위치 자신] + [범위로 함께 채워질 칸들], 이 순서 그대로
    # 그림 컴포넌트에 씨앗값으로 넘긴다 — 맨 앞이 "대표 위치"라는 규칙을
    # 유지해야 다시 열었을 때도 어떤 칸이 입고 위치인지 헷갈리지 않는다.
    initial = []
    if line_default in rack_lines:
        initial.append({"lineIdx": rack_lines.index(line_default), "levelIdx": levels.index(level_default)})
    for extra in extra_cells:
        extra_area, extra_line, extra_level = parse_location(extra)
        initial.append({"lineIdx": rack_lines.index(extra_line), "levelIdx": levels.index(extra_level)})

    selection = render_shelf_range_picker(
        rack_lines, levels, initial=initial, occupied=occupied_cells, exclusive_click=True, height=260,
        key=f"inbound_shelf_{token}_{area}",
    )
    if selection is not None:
        cells = selection.get("cells") or []
        if cells:
            # 클릭/드래그로 고른 순서 그대로 온다: 맨 처음 고른 칸이 대표
            # 입고 위치, 나머지가 범위다. 전부 지워버린 경우(빈 선택)는
            # 입고 위치가 하나도 없다는 뜻이라 무시하고 기존 선택을 유지한다.
            primary, *rest = cells
            line, level = primary["line"], primary["level"]
            st.session_state["_inbound_picker_defaults"] = {"area": area, "line": line, "level": level}
            st.session_state["_inbound_range_cells"] = [
                make_location(area, c["line"], c["level"]) for c in rest
            ]
        else:
            line = line_default if line_default in rack_lines else rack_lines[0]
            level = level_default
    else:
        line = line_default if line_default in rack_lines else rack_lines[0]
        level = level_default

    selected_locs = [make_location(area, line, level)] + list(st.session_state.get("_inbound_range_cells") or [])
    info_lines = []
    for loc in selected_locs:
        matches = [r for r, occupied in occupied_rows if loc in occupied]
        if matches:
            parts = [f"{r.product_name} {int(r.qty)}EA (LOT {r.lot or '-'})" for r in matches]
            info_lines.append(f"{loc}: " + ", ".join(parts))
    if len(selected_locs) > 1:
        st.caption(f"입고 위치 {selected_locs[0]} + 범위 {len(selected_locs) - 1}칸 ({', '.join(sorted(selected_locs[1:]))})")
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


def render_location_range_grid_picker_button(prefix, area, current_line=None, *, key=None):
    """"칸 그림으로 범위 선택" 버튼과, 열려 있는 동안 계속 떠 있어야 하는 모달을 함께 그린다.

    st.dialog는 그 함수를 호출한 런에서만 여는 게 아니라, 열려 있어야 하는 동안
    매 런마다 다시 호출해줘야 계속 떠 있는다(다이얼로그 내부 위젯 클릭 한 번마다
    Streamlit이 전체 스크립트를 다시 실행하기 때문). 그래서 버튼 클릭 자체가 아니라
    세션 상태 플래그로 "지금 열려 있어야 하는지"를 기억해뒀다가, 이 함수가 호출될
    때마다(=페이지가 다시 그려질 때마다) 그 플래그를 보고 다이얼로그를 다시 띄운다.
    """
    open_key = f"_{prefix}_grid_dialog_open"
    area_key = f"_{prefix}_grid_dialog_area"
    lines_key = f"_{prefix}_grid_dialog_lines"
    if st.button("칸 그림으로 범위 선택", key=key or f"{prefix}_grid_open", use_container_width=True):
        cfg = AREA_CONFIG.get(area, {})
        all_lines = list(cfg.get("lines") or [])
        if not all_lines or not cfg.get("levels"):
            st.toast(f"{area} 구역은 라인/단이 없어 그림으로 범위를 선택할 수 없습니다.")
        else:
            # 이전에 열었을 때 적용/취소 없이 닫았을 수도 있으니(예: 모달의 X
            # 버튼), 매번 새로 열 때는 이전 선택이 남아있지 않도록 확실히 비운다.
            # 세션 값만 지우는 게 아니라 컴포넌트 key에 들어가는 토큰도 올려서,
            # 그림 컴포넌트 쪽 내부 JS 상태(closure)까지 완전히 새로 만들어지게
            # 한다 — key가 그대로면 Streamlit이 기존 컴포넌트 인스턴스를 그대로
            # 재사용해 이전 클릭이 남긴 내부 상태가 섞여 나올 수 있기 때문이다.
            st.session_state.pop(f"_{prefix}_shelf_sel", None)
            st.session_state[f"_{prefix}_shelf_reset_token"] = int(
                st.session_state.get(f"_{prefix}_shelf_reset_token", 0) or 0
            ) + 1
            st.session_state[open_key] = True
            st.session_state[area_key] = area
            st.session_state[lines_key] = _rack_line_group(all_lines, current_line)

    if st.session_state.get(open_key):
        dialog_area = st.session_state.get(area_key) or area
        cfg = AREA_CONFIG.get(dialog_area, {})
        lines = st.session_state.get(lines_key) or _rack_line_group(list(cfg.get("lines") or []), current_line)
        levels = list(cfg.get("levels") or [])
        if lines and levels:
            _location_range_grid_dialog(prefix, dialog_area, lines, levels)
        else:
            st.session_state[open_key] = False


def _on_shelf_dialog_dismiss():
    """모달을 적용/취소 버튼이 아니라 X(또는 Esc)로 닫았을 때도 선택 상태를 비운다.

    안 그러면 다음에 이 버튼을 눌렀을 때 지난번 그리다 만 선택이 그대로 남아
    있어서, 새로 클릭해도 옛 칸이 계속 같이 붙어 나오는 것처럼 보인다.
    """
    prefix = st.session_state.pop("_shelf_dialog_active_prefix", None)
    if prefix:
        st.session_state.pop(f"_{prefix}_shelf_sel", None)
        st.session_state[f"_{prefix}_shelf_reset_token"] = int(
            st.session_state.get(f"_{prefix}_shelf_reset_token", 0) or 0
        ) + 1
        st.session_state[f"_{prefix}_grid_dialog_open"] = False


@st.dialog("칸 범위 선택", width="small", on_dismiss=_on_shelf_dialog_dismiss)
def _location_range_grid_dialog(prefix, area, lines, levels):
    from nohtus.ui.shelf_range_picker import render_shelf_range_picker

    st.session_state["_shelf_dialog_active_prefix"] = prefix
    sel_key = f"_{prefix}_shelf_sel"
    reset_token = int(st.session_state.get(f"_{prefix}_shelf_reset_token", 0) or 0)
    cells = st.session_state.get(sel_key) or []

    st.caption(f"{area} 구역 선반입니다. 칸을 클릭하면 선택되고, 누른 채 끌면 지나간 칸이 모두 붓칠하듯 선택됩니다(직사각형이 아니어도 됨). 선택된 칸을 드래그 없이 다시 클릭하면 그 칸만 해제됩니다.")
    initial = [{"lineIdx": c["lineIdx"], "levelIdx": c["levelIdx"]} for c in cells]
    # key에 리셋 토큰을 넣어서, 다시 열거나/다시 선택할 때마다 그림 컴포넌트를
    # 완전히 새 인스턴스로 만든다. key가 그대로면 내부 JS의 이전 클릭 상태가
    # 남아있다가 다음 선택에 섞여 들어올 수 있다.
    selection = render_shelf_range_picker(
        lines, levels, initial=initial, height=420, key=f"{prefix}_shelf_range_{reset_token}"
    )
    if selection is not None:
        cells = selection.get("cells") or []
        st.session_state[sel_key] = cells

    if cells:
        labels = sorted(f"{area}-{c['line']}-{c['level']}" for c in cells)
        st.info(f"선택 범위 ({len(cells)}칸): " + ", ".join(labels))
    else:
        st.caption("칸을 클릭하거나 드래그해 범위를 선택하세요.")

    apply_col, reset_col, cancel_col = st.columns(3)
    with apply_col:
        if st.button("이 범위 적용", type="primary", use_container_width=True, key=f"{prefix}_grid_apply", disabled=not cells):
            st.session_state[f"_{prefix}_range_cells"] = [
                make_location(area, c["line"], c["level"]) for c in cells
            ]
            st.session_state.pop(sel_key, None)
            st.session_state[f"_{prefix}_shelf_reset_token"] = reset_token + 1
            st.session_state[f"_{prefix}_grid_dialog_open"] = False
            st.rerun()
    with reset_col:
        if st.button("다시 선택", use_container_width=True, key=f"{prefix}_grid_reset"):
            st.session_state.pop(sel_key, None)
            st.session_state[f"_{prefix}_shelf_reset_token"] = reset_token + 1
            st.rerun()
    with cancel_col:
        if st.button("취소", use_container_width=True, key=f"{prefix}_grid_cancel"):
            st.session_state.pop(sel_key, None)
            st.session_state[f"_{prefix}_shelf_reset_token"] = reset_token + 1
            st.session_state[f"_{prefix}_grid_dialog_open"] = False
            st.rerun()
