"""Fresh warehouse-map layout based on the latest Yongin warehouse drawing.

This replaces only the visual map canvas. Existing inventory/detail/search JS from
location_map_legacy remains in place and continues to work through data-loc buttons.
"""

from __future__ import annotations

import re


_NEW_CSS = r"""
<style id="wms-new-warehouse-layout">
.map-scroll{overflow:auto!important;height:690px!important;padding:0!important;border-radius:14px;background:#fff;}
.map-stage{position:relative!important;width:1279px!important;height:919px!important;min-width:1279px!important;background:#fff!important;border-radius:0!important;transform:scale(.72)!important;transform-origin:top left!important;}
.map-stage .nw-zone,.map-stage .nw-cell{appearance:none;position:absolute;display:flex;align-items:center;justify-content:center;border:1px solid #334155;background:#fff;color:#0f172a;font:700 14px Inter,Segoe UI,Arial,'Noto Sans KR',sans-serif;cursor:pointer;box-shadow:0 4px 10px rgba(15,23,42,.08);padding:0;margin:0;}
.map-stage .nw-zone:hover,.map-stage .nw-cell:hover{outline:3px solid rgba(37,99,235,.24);z-index:4;}
.map-stage .nw-zone.selected,.map-stage .nw-cell.selected{background:#22c55e!important;color:#fff!important;outline:4px solid rgba(34,197,94,.30)!important;border-color:#15803d!important;z-index:6;}
.map-stage .farm{background:#fff2cc;border-color:#d6b656}.map-stage .notus{background:#dae8fc;border-color:#6c8ebf}.map-stage .noh{background:#f8cecc;border-color:#b85450}.map-stage .etc{background:#d5e8d4;border-color:#82b366}.map-stage .bidata{background:#b7c8d6;border-color:#64748b}.map-stage .export{background:#ffe6cc;border-color:#d79b00}.map-stage .expiry{background:#e1d5e7;border-color:#9673a6}.map-stage .support{background:#fff}.map-stage .promo{background:#fff}
.map-stage .nw-split-v:after{content:"";position:absolute;top:0;bottom:0;left:50%;border-left:1px solid rgba(51,65,85,.38);pointer-events:none}.map-stage .nw-split-h:after{content:"";position:absolute;left:0;right:0;top:50%;border-top:1px solid rgba(51,65,85,.38);pointer-events:none}
.map-stage .nw-grid6{display:grid!important;grid-template-columns:1fr 1fr;grid-template-rows:repeat(3,1fr);overflow:hidden}.map-stage .nw-grid3{display:grid!important;grid-template-rows:repeat(3,1fr);overflow:hidden}.map-stage .nw-grid3h{display:grid!important;grid-template-columns:repeat(3,1fr);overflow:hidden}.map-stage .nw-grid2h{display:grid!important;grid-template-columns:repeat(2,1fr);overflow:hidden}
.map-stage .nw-grid6 .map-cell,.map-stage .nw-grid3 .map-cell,.map-stage .nw-grid3h .map-cell,.map-stage .nw-grid2h .map-cell{position:relative!important;left:auto!important;top:auto!important;width:auto!important;height:auto!important;min-width:0!important;border:0!important;border-right:1px solid rgba(51,65,85,.35)!important;border-bottom:1px solid rgba(51,65,85,.35)!important;border-radius:0!important;box-shadow:none!important;background:transparent!important;font-size:13px!important;}
.map-stage .nw-grid6 .map-cell:nth-child(2n),.map-stage .nw-grid3h .map-cell:last-child,.map-stage .nw-grid2h .map-cell:last-child{border-right:0!important}.map-stage .nw-grid6 .map-cell:nth-child(n+5),.map-stage .nw-grid3 .map-cell:last-child{border-bottom:0!important}
.map-stage .stock-dot{right:6px!important;top:6px!important}.map-stage .nw-outline{position:absolute;border:1px solid #334155;background:#fff;pointer-events:none}.map-stage .nw-label{position:absolute;font:700 13px Inter,Segoe UI,Arial,'Noto Sans KR',sans-serif;color:#334155;text-align:center;pointer-events:none}.map-stage .nw-note{position:absolute;font:500 13px Inter,Segoe UI,Arial,'Noto Sans KR',sans-serif;color:#475569;line-height:1.45;pointer-events:none}
.map-stage .special-menu{display:none!important}
@media(max-width:1450px){.map-stage{transform:scale(.66)!important}.map-scroll{height:625px!important}}
@media(max-width:1200px){.map-stage{transform:scale(.58)!important}.map-scroll{height:550px!important}}
</style>
"""


def _button(loc: str, label: str, x: int, y: int, w: int, h: int, cls: str = "support") -> str:
    return f'<button type="button" class="nw-zone zone {cls}" data-loc="{loc}" style="left:{x}px;top:{y}px;width:{w}px;height:{h}px;">{label}</button>'


def _cell(loc: str, label: str | None = None) -> str:
    return f'<button type="button" class="map-cell" data-loc="{loc}">{label or loc}</button>'


def _grid(loc_cls: str, cells: list[str], x: int, y: int, w: int, h: int, cls: str) -> str:
    return f'<div class="nw-zone {loc_cls} {cls}" style="left:{x}px;top:{y}px;width:{w}px;height:{h}px;">{"".join(cells)}</div>'


def _map_markup() -> str:
    parts: list[str] = []

    # Left wall / package-storage block.
    parts.append(_button("G2", "G2", 0, 0, 220, 410, "support"))
    parts.append(_grid("nw-grid3h", [_cell("G1-01"), _cell("G1-02"), _cell("G1-03")], 70, 210, 150, 52, "support"))
    parts.append('<div class="nw-outline" style="left:0;top:410px;width:150px;height:51px;"></div>')

    # Upper main racks: preserve the new drawing proportions but keep rack-area click behavior.
    parts.append(_button("A2", "A2", 270, 0, 100, 150, "farm nw-split-v"))
    parts.append(_button("B2", "B2", 420, 0, 100, 150, "farm nw-split-v"))
    parts.append(_button("C2", "C2", 570, 0, 100, 150, "notus nw-split-v"))
    parts.append(_button("D1", "D1", 720, 0, 100, 150, "notus nw-split-v"))
    parts.append(_button("E1", "E1", 870, 0, 100, 150, "noh nw-split-v"))

    # F1 / X2 top-right strip.
    parts.append(_grid("nw-grid3h", [_cell("F1-01"), _cell("F1-02"), _cell("F1-03")], 970, 0, 230, 52, "bidata"))
    parts.append(_button("X2", "X2", 1200, 0, 70, 52, "bidata"))

    # Lower main racks. A1 keeps six exact locations; B1 remains an area; C1 has ONLY 01-03.
    parts.append(_grid("nw-grid6", [_cell("A1-03"), _cell("A1-04"), _cell("A1-02"), _cell("A1-05"), _cell("A1-01"), _cell("A1-06")], 270, 220, 100, 150, "farm"))
    parts.append(_button("B1", "B1", 420, 220, 100, 150, "farm nw-split-v"))
    parts.append(_grid("nw-grid3", [_cell("C1-03"), _cell("C1-02"), _cell("C1-01")], 570, 220, 52, 150, "farm"))

    # Right-side X1 stack and cold-storage R1/R2.
    parts.append(_grid("nw-grid3", [_cell("X1-01"), _cell("X1-02"), _cell("X1-03")], 1220, 180, 50, 180, "bidata"))
    parts.append(_grid("nw-grid2h", [_cell("R2"), _cell("R1")], 1150, 430, 120, 52, "etc"))

    # Warehouse wall outlines shown in the uploaded drawing.
    parts.append('<div class="nw-outline" style="left:970px;top:52px;width:300px;height:378px;border-top:1px solid #334155;border-right:1px solid #334155;border-bottom:0;border-left:0;"></div>')
    parts.append('<div class="nw-outline" style="left:800px;top:400px;width:122px;height:120px;"></div>')
    parts.append('<div class="nw-outline" style="left:920px;top:400px;width:172px;height:80px;"></div>')
    parts.append('<div class="nw-outline" style="left:330px;top:640px;width:510px;height:279px;border-right:0;border-bottom:0;"></div>')
    parts.append('<div class="nw-outline" style="left:840px;top:520px;width:1px;height:120px;border-width:0 0 0 1px;"></div>')

    # Receiving and misc locations.
    parts.append(_button("REC", "REC", 427, 485, 88, 62, "support"))
    parts.append(_button("N", "기타 위치", 870, 575, 122, 62, "support"))

    # Export / expiry / T blocks, exactly on the left as in the new diagram.
    parts.append(_button("P", "P", 0, 560, 150, 52, "export"))
    parts.append(_button("T1", "T1", 150, 510, 100, 102, "support"))
    parts.append(_button("Q", "Q", 0, 685, 150, 52, "expiry"))
    parts.append(_button("T2", "T2", 150, 685, 100, 102, "support"))

    # Promotion racks along the bottom-left.
    parts.append(_button("홍보물랙", "홍보물랙", 0, 860, 120, 52, "promo"))
    parts.append(_button("홍보물랙", "홍보물랙", 120, 860, 120, 52, "promo"))

    # Keep the legacy special-menu node because its JS expects the element to exist.
    parts.append('<div class="special-menu" id="specialMenu"><button type="button" data-special-loc="홍보물랙">홍보물랙</button><button type="button" data-special-loc="회색 카트">회색 카트</button><button type="button" data-special-loc="오른쪽 창고">오른쪽 창고</button><button type="button" data-special-loc="사무실(4층)">사무실(4층)</button></div>')

    return '<div class="map-scroll"><div class="map-stage">' + ''.join(parts) + '</div></div>'


def apply_new_layout(html: str) -> str:
    """Replace the legacy map canvas wholesale with the latest warehouse drawing."""
    # Add CSS once, after legacy CSS so these rules win.
    html = html.replace("</head>", _NEW_CSS + "</head>", 1)

    replacement = _map_markup()
    pattern = re.compile(
        r'<div class="map-scroll"><div class="map-stage">.*?</div></div>\s*</div>\s*<div class="side-card"',
        re.S,
    )
    html, count = pattern.subn(replacement + '\n  </div>\n  <div class="side-card"', html, count=1)
    if count != 1:
        # Fail safely: keep the legacy map rather than returning broken HTML.
        return html
    return html
