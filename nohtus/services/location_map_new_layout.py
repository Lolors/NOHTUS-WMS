"""Interactive Yongin warehouse map based on the approved floor-plan layout.

This module replaces only the visual map canvas. Inventory/detail/search behavior
continues to be provided by location_map_legacy through the same data-loc buttons.
"""
from __future__ import annotations

from html import escape
import re

from nohtus.services.location_map_layout import load_location_map_layout


_NEW_CSS = r"""
<style id="wms-approved-warehouse-layout">
/* Keep the existing WMS look: large labels, rounded cards and soft shadows. */
.map-scroll{overflow:hidden!important;width:100%!important;height:628px!important;padding:0!important;background:#fff;}
.map-stage{position:relative!important;width:1482px!important;height:910px!important;min-width:1482px!important;background:#fff!important;border:0!important;border-radius:0!important;transform:scale(.69)!important;transform-origin:top left!important;overflow:hidden!important;}

.map-stage .nw-zone,.map-stage .nw-rack,.map-stage .map-cell{
  appearance:none;box-sizing:border-box;color:#0f172a;font-family:Inter,Segoe UI,Arial,'Noto Sans KR',sans-serif;
}
.map-stage .nw-zone{position:absolute;display:flex;align-items:center;justify-content:center;border:1.5px solid #64748b;border-radius:11px;background:#fff;font-size:17px;font-weight:900;cursor:pointer;box-shadow:0 3px 9px rgba(15,23,42,.05);}
.map-stage .nw-rack{position:absolute;display:grid;overflow:hidden;border:1.5px solid #64748b;border-radius:11px;box-shadow:0 3px 9px rgba(15,23,42,.05);}
.map-stage .nw-grid6{grid-template-columns:1fr 1fr;grid-template-rows:repeat(3,1fr)}
.map-stage .nw-grid3{grid-template-columns:1fr;grid-template-rows:repeat(3,1fr)}
.map-stage .nw-grid3h{grid-template-columns:repeat(3,1fr);grid-template-rows:1fr}
.map-stage .nw-grid2h{grid-template-columns:repeat(2,1fr);grid-template-rows:1fr}
.map-stage .map-cell{position:relative!important;left:auto!important;top:auto!important;width:auto!important;height:auto!important;min-width:0!important;display:flex!important;align-items:center!important;justify-content:center!important;border:0!important;border-right:1px solid rgba(51,65,85,.30)!important;border-bottom:1px solid rgba(51,65,85,.30)!important;border-radius:0!important;background:transparent!important;box-shadow:none!important;font-size:16px!important;font-weight:900!important;cursor:pointer!important;}
.map-stage .nw-grid6 .map-cell:nth-child(2n),.map-stage .nw-grid3h .map-cell:last-child,.map-stage .nw-grid2h .map-cell:last-child{border-right:0!important}
.map-stage .nw-grid6 .map-cell:nth-child(n+5),.map-stage .nw-grid3 .map-cell:last-child{border-bottom:0!important}
.map-stage .nw-grid3h .map-cell{border-bottom:0!important}

.map-stage .nw-zone:hover,.map-stage .map-cell:hover{outline:3px solid rgba(37,99,235,.22)!important;z-index:5;}
.map-stage .nw-zone.selected,.map-stage .map-cell.selected{background:#22c55e!important;color:#fff!important;outline:4px solid rgba(34,197,94,.34)!important;box-shadow:0 0 0 3px rgba(255,255,255,.78),0 0 20px rgba(34,197,94,.60)!important;border-color:#15803d!important;z-index:8;}

/* Approved palette. The '비자료' legend is intentionally the same as F1. */
.map-stage .farm{background:#fff0b8;border-color:#e6a700}.map-stage .notus{background:#c9edf7;border-color:#3b9fc1}.map-stage .noh{background:#f7b3df;border-color:#dc5daf}
.map-stage .bidata{background:#c5eceb;border-color:#4aa6a5}.map-stage .cold{background:#d9f2a6;border-color:#86b64a}.map-stage .export{background:#ffe3c7;border-color:#f08a37}.map-stage .expiry{background:#e7d4f1;border-color:#a779c0}.map-stage .support{background:#fff}.map-stage .promo{background:#fff}
.map-stage .export{color:#c2410c!important}.map-stage .expiry{color:#dc2626!important}
.map-stage .export.selected,.map-stage .expiry.selected{color:#fff!important}
.swatch.g{background:#c5eceb!important;border-color:#4aa6a5!important;}

.map-stage .stock-dot,.map-stage .dynamic-stock-dot{position:absolute!important;right:9px!important;top:9px!important;width:10px!important;height:10px!important;background:#62dc58!important;border:1.5px solid #15803d!important;border-radius:999px!important;box-shadow:0 0 0 2px rgba(255,255,255,.85)!important;pointer-events:none!important;z-index:7!important;}

.map-stage .nw-outline{position:absolute;border:1.5px solid #334155;background:transparent;pointer-events:none;}
.map-stage .nw-note{position:absolute;padding:15px 18px;border:1.5px dashed #cbd5e1;border-radius:14px;color:#64748b;font-size:16px;line-height:1.7;background:rgba(255,255,255,.78);pointer-events:none;}
.map-stage .nw-rec-label{position:absolute;color:#0f172a;font-size:14px;font-weight:800;text-align:center;pointer-events:none;}
.map-stage .nw-hatched{background:repeating-linear-gradient(135deg,#fff 0,#fff 8px,#d9efff 8px,#d9efff 10px)!important;border-color:#38a6e8!important;z-index:12!important;isolation:isolate;}
.map-stage .special-menu{position:absolute!important;left:995px!important;top:630px!important;width:180px!important;display:none;grid-template-columns:1fr!important;z-index:30!important;background:#fff!important;border:1px solid #cbd5e1!important;border-radius:12px!important;box-shadow:0 12px 28px rgba(15,23,42,.18)!important;padding:6px!important;}
.map-stage .special-menu.open{display:grid!important;gap:6px!important;}
.map-stage .special-menu button{appearance:none!important;border:1px solid #e2e8f0!important;background:#f8fafc!important;border-radius:9px!important;font-size:13px!important;font-weight:900!important;color:#0f172a!important;padding:8px 10px!important;cursor:pointer!important;}
.map-stage .special-menu button:hover,.map-stage .special-menu button.selected{background:#22c55e!important;color:#fff!important;border-color:#16a34a!important;}

@media(max-width:1500px){.map-stage{transform:scale(.62)!important}.map-scroll{height:565px!important}}
@media(max-width:1250px){.map-stage{transform:scale(.54)!important}.map-scroll{height:492px!important}}
</style>
"""


def _cell(loc: str, label: str | None = None) -> str:
    return f'<button type="button" class="map-cell" data-loc="{loc}">{label or loc}</button>'


def _grid(grid_cls: str, cells: list[str], x: int, y: int, w: int, h: int, cls: str) -> str:
    return f'<div class="nw-rack {grid_cls} {cls}" style="left:{x}px;top:{y}px;width:{w}px;height:{h}px;">{"".join(cells)}</div>'


def _zone(loc: str, label: str, x: int, y: int, w: int, h: int, cls: str = "support", extra_cls: str = "") -> str:
    return f'<button type="button" class="nw-zone zone {cls} {extra_cls}" data-loc="{loc}" style="left:{x}px;top:{y}px;width:{w}px;height:{h}px;">{label}</button>'


def _six(prefix: str) -> list[str]:
    return [_cell(f"{prefix}-03"), _cell(f"{prefix}-04"), _cell(f"{prefix}-02"), _cell(f"{prefix}-05"), _cell(f"{prefix}-01"), _cell(f"{prefix}-06")]


def _map_markup() -> str:
    p: list[str] = []
    p.append(_zone("G2", "G2", 18, 18, 230, 300, "support"))
    p.append(_grid("nw-grid3h", [_cell("G1-01"), _cell("G1-02"), _cell("G1-03")], 18, 318, 230, 70, "support"))

    p.append(_grid("nw-grid6", _six("A2"), 275, 30, 165, 235, "farm"))
    p.append(_grid("nw-grid6", _six("B2"), 458, 30, 165, 235, "farm"))
    p.append(_grid("nw-grid6", _six("C2"), 642, 30, 165, 235, "notus"))
    p.append(_grid("nw-grid6", _six("D1"), 825, 30, 165, 235, "notus"))
    p.append(_grid("nw-grid6", _six("E1"), 1008, 30, 165, 235, "noh"))
    p.append(_grid("nw-grid3h", [_cell("F1-01"), _cell("F1-02"), _cell("F1-03")], 1190, 30, 225, 78, "bidata"))
    p.append(_zone("X2", "X2", 1422, 30, 60, 78, "bidata"))

    p.append(_grid("nw-grid6", _six("A1"), 275, 330, 165, 235, "farm"))
    p.append(_grid("nw-grid6", _six("B1"), 458, 330, 165, 235, "farm"))
    # C1 has only three cells, but each cell matches one C2 cell (82.5 x 78.3px).
    p.append(_grid("nw-grid3", [_cell("C1-03"), _cell("C1-02"), _cell("C1-01")], 650, 330, 83, 235, "farm"))

    p.append(_grid("nw-grid3", [_cell("X1-01"), _cell("X1-02"), _cell("X1-03")], 1418, 250, 64, 240, "bidata"))
    p.append('<div class="nw-note" style="left:1195px;top:335px;width:210px;">X1-01~03 : 폐기<br>X1-01-01 : 대표님 시술용</div>')

    p.append(_zone("P", "P<br>수출대기", 18, 600, 160, 82, "export"))
    p.append(_zone("T1", "T1", 190, 600, 105, 82, "support"))
    p.append(_zone("Q", "Q<br>유통기한임박", 18, 710, 160, 82, "expiry"))
    p.append(_zone("T2", "T2", 190, 710, 105, 82, "support"))

    p.append(_zone("REC", '<span><span style="color:#ef2d22">REC</span><br>Receiving</span>', 490, 690, 130, 72, "support"))
    p.append('<div class="nw-rec-label" style="left:480px;top:770px;width:150px;">매입등록대기</div>')

    # Keep the warehouse structure to the left of the refrigerators.  Only the
    # extension around R1/R2 is open on its top/right, as in the reference plan.
    p.append('<div class="nw-outline" style="left:930px;top:590px;width:330px;height:185px;border-right:0;border-bottom:0;"></div>')
    # Draw the right edge only as far as the refrigerator guide intersection.
    p.append('<div class="nw-outline" style="left:1260px;top:590px;width:1px;height:110px;border-width:0 0 0 1.5px;"></div>')
    p.append('<div class="nw-outline" style="left:1260px;top:590px;width:222px;height:110px;border-width:0 0 1.5px 0;"></div>')
    p.append(_grid("nw-grid2h", [_cell("R2"), _cell("R1")], 1280, 615, 185, 72, "cold"))

    p.append(_zone("N", "기타 위치", 1000, 740, 150, 92, "support", "nw-hatched"))

    p.append(_zone("홍보물랙", "홍보물랙", 18, 830, 290, 62, "promo"))

    p.append('<div class="nw-outline" style="left:410px;top:865px;width:520px;height:45px;border-right:0;border-bottom:0;"></div>')
    p.append('<div class="nw-outline" style="left:930px;top:775px;width:1px;height:90px;border-width:0 0 0 1.5px;"></div>')

    p.append('<div class="special-menu" id="specialMenu"><button type="button" data-special-loc="오른쪽 창고">오른쪽 창고</button><button type="button" data-special-loc="사무실(4층)">사무실(4층)</button><button type="button" data-special-loc="지엠메딕">지엠메딕</button></div>')
    return '<div class="map-scroll"><div class="map-stage">' + ''.join(p) + '</div></div>'


def _layout_class(item: dict) -> str:
    code = str(item.get("code") or "").strip()
    company = str(item.get("company") or "").strip()
    if code == "P":
        return "export"
    if code == "Q":
        return "expiry"
    if code in {"R1", "R2"}:
        return "cold"
    return {
        "노투스팜": "farm", "노투스": "notus", "NOH": "noh",
        "비자료": "bidata", "특수": "support",
    }.get(company, "support")


def _location_fill_style(item: dict, company_colors: dict) -> str:
    fill_type = str(item.get("fill_type") or "company").strip()
    fill_color = str(item.get("fill_color") or "#ffffff").strip()
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", fill_color):
        fill_color = "#ffffff"
    if fill_type == "company":
        company_color = str(company_colors.get(str(item.get("company") or "").strip()) or "").strip()
        if re.fullmatch(r"#[0-9a-fA-F]{6}", company_color):
            return f"background:{company_color};"
        return ""
    if fill_type == "solid":
        return f"background:{fill_color};"
    if fill_type == "hatched":
        return f"background:repeating-linear-gradient(135deg,{fill_color} 0 2px,#fff 2px 8px);"
    if fill_type == "none":
        return "background:transparent;"
    return ""


def _saved_layout_markup(layout: dict) -> str:
    items = []
    company_colors = layout.get("company_colors") or {}
    for layer_index, item in enumerate(layout.get("items") or [], start=1):
        code = str(item.get("code") or "").strip()
        if not code:
            continue
        label = escape(str(item.get("label") or code).strip() or code).replace("\n", "<br>")
        x = max(0, int(item.get("x") or 0))
        y = max(0, int(item.get("y") or 0))
        width = max(36, int(item.get("width") or 80))
        height = max(30, int(item.get("height") or 56))
        rotation = int(item.get("rotation") or 0)
        style = (
            f"left:{x}px;top:{y}px;width:{width}px;height:{height}px;"
            f"transform:rotate({rotation}deg);z-index:{layer_index};"
        )
        if str(item.get("kind") or "") == "shape":
            shape_type = str(item.get("shape_type") or "rounded_rect").strip()
            stroke = escape(str(item.get("stroke") or "#475569").strip(), quote=True)
            fill_style = _location_fill_style(item, {})
            decoration = {
                "rounded_rect": f"border:1.5px solid {stroke};border-radius:18px;{fill_style}",
                "circle": f"border:1.5px solid {stroke};border-radius:50%;{fill_style}",
                "line": (
                    "border:0;background:linear-gradient(to bottom,"
                    f"transparent calc(50% - .75px),{stroke} calc(50% - .75px),"
                    f"{stroke} calc(50% + .75px),transparent calc(50% + .75px));"
                ),
            }.get(shape_type, f"border:1.5px solid {stroke};border-radius:18px;{fill_style}")
            items.append(
                f'<div class="map-shape map-shape-{escape(shape_type, quote=True)}" '
                f'aria-hidden="true" style="{style}{decoration}'
                'position:absolute;pointer-events:none;"></div>'
            )
        else:
            items.append(
                f'<button type="button" class="nw-zone zone {_layout_class(item)}" '
                f'data-loc="{escape(code, quote=True)}" style="{style}{_location_fill_style(item, company_colors)}">'
                f'<span style="display:inline-block;transform:rotate({-rotation}deg);'
                f'transform-origin:center;">{label}</span></button>'
            )
    items.extend([
        '<div class="nw-outline" style="left:930px;top:590px;width:330px;height:185px;border-right:0;border-bottom:0;"></div>',
        '<div class="nw-outline" style="left:1260px;top:590px;width:1px;height:110px;border-width:0 0 0 1.5px;"></div>',
        '<div class="nw-outline" style="left:1260px;top:590px;width:222px;height:110px;border-width:0 0 1.5px 0;"></div>',
        '<div class="nw-outline" style="left:410px;top:865px;width:520px;height:45px;border-right:0;border-bottom:0;"></div>',
        '<div class="nw-outline" style="left:930px;top:775px;width:1px;height:90px;border-width:0 0 0 1.5px;"></div>',
        '<div class="special-menu" id="specialMenu"><button type="button" data-special-loc="오른쪽 창고">오른쪽 창고</button><button type="button" data-special-loc="사무실(4층)">사무실(4층)</button><button type="button" data-special-loc="지엠메딕">지엠메딕</button></div>',
    ])
    return '<div class="map-scroll"><div class="map-stage">' + ''.join(items) + '</div></div>'


_DYNAMIC_DOTS_JS = r"""
function fitApprovedMapToWidth(){
  const scroll=document.querySelector('.map-scroll');
  const stage=scroll&&scroll.querySelector('.map-stage');
  if(!scroll||!stage)return;
  const naturalWidth=Math.max(1,stage.offsetWidth);
  const naturalHeight=Math.max(1,stage.offsetHeight);
  const availableWidth=Math.max(1,scroll.clientWidth);
  const fittedScale=availableWidth/naturalWidth;
  stage.style.setProperty('transform',`scale(${fittedScale})`,'important');
  stage.style.setProperty('transform-origin','top left','important');
  scroll.style.setProperty('height',Math.ceil(naturalHeight*fittedScale)+'px','important');
  scroll.style.setProperty('overflow','hidden','important');
}
function refreshApprovedMapDots(){
  document.querySelectorAll('.map-stage .dynamic-stock-dot').forEach(el=>el.remove());
  const specialStockLocations=['오른쪽 창고','사무실(4층)','지엠메딕'];
  const hasStock = (loc) => {
    if(loc==='N') return specialStockLocations.some(special => (inventory[special]||[]).some(row => Number(row.qty||0)>0));
    return Object.entries(inventory||{}).some(([key, rows]) => {
      if(!(key===loc || key.startsWith(loc+'-'))) return false;
      return (rows||[]).some(row => Number(row.qty||0) > 0);
    });
  };
  document.querySelectorAll('.map-stage [data-loc]').forEach(el=>{
    const loc=String(el.dataset.loc||'').trim();
    if(!loc || !hasStock(loc)) return;
    const dot=document.createElement('span');
    dot.className='dynamic-stock-dot';
    el.appendChild(dot);
  });
}
refreshApprovedMapDots();
requestAnimationFrame(fitApprovedMapToWidth);
window.addEventListener('resize',fitApprovedMapToWidth);
if(window.ResizeObserver){
  const mapScroll=document.querySelector('.map-scroll');
  if(mapScroll)new ResizeObserver(fitApprovedMapToWidth).observe(mapScroll);
}
"""


def apply_new_layout(html: str) -> str:
    """Replace the legacy map canvas with the approved interactive floor plan."""
    layout = load_location_map_layout()
    canvas = layout.get("canvas") or {}
    has_saved_layout = bool(layout.get("items"))
    canvas_css = ""
    if has_saved_layout:
        width = max(400, int(canvas.get("width") or 1482))
        height = max(300, int(canvas.get("height") or 910))
        canvas_css = f"<style>.map-stage{{width:{width}px!important;height:{height}px!important;min-width:{width}px!important;}}</style>"
    html = html.replace("</head>", _NEW_CSS + canvas_css + "</head>", 1)
    replacement = _saved_layout_markup(layout) if has_saved_layout else _map_markup()
    pattern = re.compile(
        r'<div class="map-scroll"><div class="map-stage">.*?</div></div>\s*</div>\s*<div class="side-card"',
        re.S,
    )
    html, count = pattern.subn(replacement + '\n  </div>\n  <div class="side-card"', html, count=1)
    if count != 1:
        return html
    marker = "const inventory = DATA.inventory || {};"
    html = html.replace(marker, marker + "\n" + _DYNAMIC_DOTS_JS, 1)
    return html
