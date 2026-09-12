"""모바일 재고 상세 화면에 띄우는 미니 로케이션맵용 조회 함수.

데스크톱 로케이션맵(nohtus/services/location_map*.py)은 Streamlit
components.html 안에 통째로 그려지는 큰 인터랙티브 지도라 그대로 가져다
쓸 수 없다. 여기서는 저장된 레이아웃 JSON(data/location_map_layout.json,
nohtus.services.location_map_layout.load_location_map_layout()이 읽는
바로 그 파일)을 데스크톱과 최대한 같은 모양으로 보이도록 필요한 필드
(회사별 색상, 채우기, 벽/문 같은 배경 도형)까지 그대로 내려주고,
모바일 쪽에서 가벼운 SVG로 다시 그린다.

불이 들어올 칸을 찾는 매칭 규칙, 그리고 실시간 재고 유무를 나타내는
초록 점(dynamic-stock-dot)도 데스크톱의 refreshApprovedMapDots()와 같은
규칙("정확히 같거나, 재고 위치가 그 칸 코드로 시작하면 매칭")으로 맞춘다.
"""

from __future__ import annotations

from nohtus.db import q
from nohtus.services.location_map_layout import load_location_map_layout

# refreshApprovedMapDots()의 specialStockLocations와 동일 — 'N' 칸은 이
# 실제 위치들 중 하나에라도 재고가 있으면 초록 점이 켜진다.
_SPECIAL_STOCK_LOCATIONS = ("오른쪽 창고", "사무실(4층)", "지엠메딕", "거래처 창고")


def _stock_locations():
    """qty>0인 재고가 실제로 존재하는 로케이션 문자열 집합."""
    df = q("SELECT DISTINCT location FROM inventory WHERE qty > 0")
    if df.empty:
        return set()
    return {str(v).strip() for v in df["location"].dropna() if str(v).strip()}


def _matches(code, locations):
    return any(loc == code or loc.startswith(code + "-") for loc in locations)


def _has_stock(code, locations):
    if code == "N":
        return any(_matches(special, locations) for special in _SPECIAL_STOCK_LOCATIONS)
    return _matches(code, locations)


def get_layout():
    layout = load_location_map_layout()
    canvas = layout.get("canvas") or {"width": 1740, "height": 980}
    company_colors = layout.get("company_colors") or {}
    locations = _stock_locations()

    items = []
    for item in layout.get("items") or []:
        kind = str(item.get("kind") or "")
        if kind not in ("location", "zone", "shape"):
            continue
        code = str(item.get("code") or "").strip()
        x, y = item.get("x", 0), item.get("y", 0)
        width, height = item.get("width", 70), item.get("height", 70)
        # 90도(또는 -270도, 즉 같은 방향) 회전은 실제로는 칸을 눕히는 게
        # 아니라 가로/세로를 맞바꾼 채 중심을 고정하고 다시 그리는 것과
        # 같다(P/Q/박스(기타)처럼 세로로 긴 칸). 텍스트 자체는 회전하지
        # 않고 그대로 여러 줄로 보인다.
        if item.get("rotation", 0) % 360 in (90, 270):
            cx, cy = x + width / 2, y + height / 2
            width, height = height, width
            x, y = cx - width / 2, cy - height / 2
        entry = {
            "kind": kind,
            "code": code,
            "label": str(item.get("label") or code),
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "company": str(item.get("company") or ""),
            "fill_type": str(item.get("fill_type") or "none"),
            "fill_color": str(item.get("fill_color") or "#ffffff"),
            "stroke": str(item.get("stroke") or "#94a3b8"),
            "shape_type": str(item.get("shape_type") or ""),
            "path_points": item.get("path_points") or [],
        }
        if kind in ("location", "zone") and code:
            entry["has_stock"] = _has_stock(code, locations)
        items.append(entry)

    return {
        "canvas": {"width": canvas.get("width", 1740), "height": canvas.get("height", 980)},
        "company_colors": company_colors,
        "items": items,
    }
