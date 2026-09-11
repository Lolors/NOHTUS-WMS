"""모바일 재고 상세 화면에 띄우는 미니 로케이션맵용 조회 함수.

데스크톱 로케이션맵(nohtus/services/location_map*.py)은 Streamlit
components.html 안에 통째로 그려지는 큰 인터랙티브 지도라 그대로 가져다
쓸 수 없다. 여기서는 저장된 레이아웃 JSON(data/location_map_layout.json,
nohtus.services.location_map_layout.load_location_map_layout()이 읽는
바로 그 파일)에서 위치 좌표만 뽑아 모바일 쪽에서 가벼운 SVG로 다시 그릴
수 있게 내려준다. 불이 들어올 칸을 찾는 매칭 규칙도 데스크톱의
showDetail()과 동일하게 "정확히 같거나, 재고 위치가 그 칸 코드로
시작하면" 매칭되는 것으로 맞춘다.
"""

from __future__ import annotations

from nohtus.services.location_map_layout import load_location_map_layout


def get_layout():
    layout = load_location_map_layout()
    canvas = layout.get("canvas") or {"width": 1740, "height": 980}
    items = []
    for item in layout.get("items") or []:
        kind = str(item.get("kind") or "")
        if kind not in ("location", "zone"):
            continue
        code = str(item.get("code") or "").strip()
        if not code:
            continue
        items.append(
            {
                "code": code,
                "label": str(item.get("label") or code),
                "x": item.get("x", 0),
                "y": item.get("y", 0),
                "width": item.get("width", 70),
                "height": item.get("height", 70),
            }
        )
    return {
        "canvas": {"width": canvas.get("width", 1740), "height": canvas.get("height", 980)},
        "items": items,
    }
