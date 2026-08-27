"""로케이션 네임택 PDF 생성 스크립트.

data/location_labels.xlsx (로케이션 코드, 사업장명)를 읽어
가로 7.2cm x 세로 4.9cm 네임택을 A4 용지에 2열 x 6행(12개)으로 배치한
data/location_labels.pdf 를 생성한다.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = Path(os.environ.get("LOCATION_LABELS_OUT_DIR", PROJECT_ROOT / "data"))
LABELS_XLSX = OUT_DIR / "location_labels.xlsx"
LAYOUT_JSON = PROJECT_ROOT / "data" / "location_map_layout.json"
OUT_PDF = OUT_DIR / "location_labels.pdf"

TAG_W = 72 * mm
TAG_H = 49 * mm
COLS, ROWS = 2, 6

PAGE_W, PAGE_H = A4
MARGIN_X = (PAGE_W - COLS * TAG_W) / 2
MARGIN_Y = (PAGE_H - ROWS * TAG_H) / 2

pdfmetrics.registerFont(TTFont("Malgun", r"C:\Windows\Fonts\malgun.ttf"))
pdfmetrics.registerFont(TTFont("MalgunBold", r"C:\Windows\Fonts\malgunbd.ttf"))


def load_company_colors() -> dict[str, str]:
    data = json.loads(LAYOUT_JSON.read_text(encoding="utf-8"))
    return data.get("company_colors", {})


def fit_font_size(text: str, max_width: float, font_name: str, max_size: float, min_size: float = 14) -> float:
    size = max_size
    while size > min_size and pdfmetrics.stringWidth(text, font_name, size) > max_width:
        size -= 0.5
    return size


def draw_tag(c: canvas.Canvas, x: float, y: float, code: str, company: str, color_hex: str):
    # 컷팅 가이드선
    c.setStrokeColorRGB(0.75, 0.75, 0.75)
    c.setLineWidth(0.4)
    c.rect(x, y, TAG_W, TAG_H, stroke=1, fill=0)

    # 상단 회사 컬러 바
    bar_h = 10 * mm
    c.setFillColor(color_hex)
    c.rect(x, y + TAG_H - bar_h, TAG_W, bar_h, stroke=0, fill=1)
    c.setFillColorRGB(0.06, 0.09, 0.16)
    c.setFont("MalgunBold", 12)
    c.drawCentredString(x + TAG_W / 2, y + TAG_H - bar_h + 3.0 * mm, company)

    # 중앙 로케이션 코드 (남은 영역 전체를 가로/세로 가운데 정렬, 폭에 맞춰 자동 축소)
    c.setFillColorRGB(0.06, 0.09, 0.16)
    max_text_width = TAG_W - 6 * mm
    font_size = fit_font_size(code, max_text_width, "MalgunBold", max_size=44)
    c.setFont("MalgunBold", font_size)
    body_top = y + TAG_H - bar_h
    # 폰트 기준선 보정을 위해 캡하이트의 절반만큼 아래로 내려 시각적 중앙에 맞춘다
    baseline_y = y + (body_top - y) / 2 - font_size * 0.32
    c.drawCentredString(x + TAG_W / 2, baseline_y, code)


def main():
    df = pd.read_excel(LABELS_XLSX)
    company_colors = load_company_colors()
    default_color = "#f1f5f9"

    c = canvas.Canvas(str(OUT_PDF), pagesize=A4)
    per_page = COLS * ROWS
    total = len(df)

    for page_start in range(0, total, per_page):
        chunk = df.iloc[page_start:page_start + per_page]
        for i, (_, row) in enumerate(chunk.iterrows()):
            col = i % COLS
            r = i // COLS
            x = MARGIN_X + col * TAG_W
            y = PAGE_H - MARGIN_Y - (r + 1) * TAG_H
            code = str(row["로케이션 코드"])
            company = str(row["사업장(회사)명"])
            color_hex = company_colors.get(company, default_color)
            draw_tag(c, x, y, code, company, color_hex)
        c.showPage()

    c.save()
    print(f"saved {OUT_PDF} ({total} labels, {(total + per_page - 1) // per_page} pages)")


if __name__ == "__main__":
    main()
