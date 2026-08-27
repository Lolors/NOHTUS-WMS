"""구역명 사인(A4 가로) PDF 생성 스크립트.

data/location_map_layout.json 을 읽어 A1, B2, G2, F1, 옷장1 같은
구역(랙) 이름을 A4 가로 용지 한 장에 하나씩 큼직하게 표시하는
data/zone_signs.pdf 를 생성한다. 랙 위에 걸어두는 대형 표지판용.
"""
from __future__ import annotations

import json
import os
from collections import defaultdict
from pathlib import Path

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = Path(os.environ.get("LOCATION_LABELS_OUT_DIR", PROJECT_ROOT / "data"))
LAYOUT_JSON = PROJECT_ROOT / "data" / "location_map_layout.json"
OUT_PDF = OUT_DIR / "zone_signs.pdf"

PAGE_W, PAGE_H = landscape(A4)
MARGIN = 15 * mm

SKIP_CODES = {"T1", "T2"}
SKIP_PREFIX = ("__shape",)

pdfmetrics.registerFont(TTFont("Malgun", r"C:\Windows\Fonts\malgun.ttf"))
pdfmetrics.registerFont(TTFont("MalgunBold", r"C:\Windows\Fonts\malgunbd.ttf"))


def load_layout() -> dict:
    return json.loads(LAYOUT_JSON.read_text(encoding="utf-8"))


def collect_areas(layout: dict) -> list[dict]:
    items = layout.get("items", [])
    areas: dict[str, dict] = defaultdict(lambda: {"xs": [], "ys": []})

    for item in items:
        kind = item.get("kind")
        code = item.get("code") or ""
        if not code or code.startswith(SKIP_PREFIX) or code in SKIP_CODES:
            continue
        if kind == "location":
            area = code.split("-")[0]
        elif kind == "zone":
            area = code
        else:
            continue
        a = areas[area]
        a["xs"].append(item.get("x", 0))
        a["ys"].append(item.get("y", 0))

    result = []
    for area, info in areas.items():
        cx = sum(info["xs"]) / len(info["xs"])
        cy = sum(info["ys"]) / len(info["ys"])
        result.append({"area": area, "cx": cx, "cy": cy})

    # 창고 실제 배치(위→아래, 왼→오른쪽)와 비슷한 순서로 정렬
    result.sort(key=lambda r: (round(r["cy"] / 50), r["cx"]))
    return result


def fit_font_size(text: str, max_width: float, font_name: str, max_size: float, min_size: float = 40) -> float:
    size = max_size
    while size > min_size and pdfmetrics.stringWidth(text, font_name, size) > max_width:
        size -= 1
    return size


INK = (0.06, 0.09, 0.16)
CORNER = 18 * mm
FRAME_GAP = 6 * mm


def draw_frame(c: canvas.Canvas):
    outer_x, outer_y = MARGIN, MARGIN
    outer_w, outer_h = PAGE_W - 2 * MARGIN, PAGE_H - 2 * MARGIN
    inner_x, inner_y = outer_x + FRAME_GAP, outer_y + FRAME_GAP
    inner_w, inner_h = outer_w - 2 * FRAME_GAP, outer_h - 2 * FRAME_GAP

    c.setStrokeColor(INK)
    c.setLineWidth(2.4)
    c.rect(outer_x, outer_y, outer_w, outer_h, stroke=1, fill=0)
    c.setLineWidth(0.9)
    c.rect(inner_x, inner_y, inner_w, inner_h, stroke=1, fill=0)

    # 네 모서리 장식 (겹꺾쇠)
    c.setLineWidth(2.4)
    for cx, cy, sx, sy in (
        (outer_x, outer_y, 1, 1),
        (outer_x + outer_w, outer_y, -1, 1),
        (outer_x, outer_y + outer_h, 1, -1),
        (outer_x + outer_w, outer_y + outer_h, -1, -1),
    ):
        c.line(cx, cy, cx + sx * CORNER, cy)
        c.line(cx, cy, cx, cy + sy * CORNER)


def draw_sign(c: canvas.Canvas, area: str):
    # 배경
    c.setFillColorRGB(1, 1, 1)
    c.rect(0, 0, PAGE_W, PAGE_H, stroke=0, fill=1)

    draw_frame(c)

    # 중앙 구역명 (프레임 안쪽 영역 가로/세로 가운데 정렬, 폭에 맞춰 자동 축소)
    inner_x = MARGIN + FRAME_GAP
    inner_w = PAGE_W - 2 * (MARGIN + FRAME_GAP)
    max_text_width = inner_w - 20 * mm
    font_size = fit_font_size(area, max_text_width, "MalgunBold", max_size=280)
    c.setFillColor(INK)
    c.setFont("MalgunBold", font_size)
    baseline_y = PAGE_H / 2 - font_size * 0.32
    c.drawCentredString(PAGE_W / 2, baseline_y, area)


def main():
    layout = load_layout()
    areas = collect_areas(layout)

    c = canvas.Canvas(str(OUT_PDF), pagesize=landscape(A4))
    for info in areas:
        draw_sign(c, info["area"])
        c.showPage()
    c.save()
    print(f"saved {OUT_PDF} ({len(areas)} zone signs)")


if __name__ == "__main__":
    main()
