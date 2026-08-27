"""Drag-based shelf range picker.

Renders a shelf graphic (side posts + shelf dividers, in the style of a real
warehouse rack drawing) with a draggable/resizable block overlay. The block
represents "the product occupies this line x level rectangle" and the user
positions/resizes it directly on the shelf instead of picking two corners
from a button grid.
"""

from __future__ import annotations

import hashlib

import streamlit as st
import streamlit.components.v2 as components_v2


_CSS = """
* { box-sizing: border-box; }
.shelf-wrap {
  position: relative; width: 100%; user-select: none; touch-action: none;
  font-family: Inter, "Segoe UI", Arial, "Noto Sans KR", sans-serif;
}
.shelf-svg { display: block; width: 100%; height: auto; }
.shelf-grid-lines { position: absolute; inset: 0; pointer-events: none; }
.v-guide { position: absolute; top: 0; bottom: 0; width: 0; border-left: 1px dashed #cbd5e1; }
.h-divider { position: absolute; left: 0; right: 0; height: 0; border-top: 2px solid #94a3b8; }
.h-divider::after {
  content: ""; position: absolute; left: 0; right: 0; top: 4px; height: 0; border-top: 2px solid #94a3b8;
}
.shelf-line-label, .shelf-level-label {
  position: absolute; font-size: 12px; font-weight: 800; color: #475569;
}
.shelf-block {
  position: absolute; background: rgba(37,99,235,.20); border: 2px solid #2563eb;
  border-radius: 8px; cursor: grab; display: flex; align-items: center; justify-content: center;
  color: #1d4ed8; font-weight: 800; font-size: 13px; text-align: center; padding: 4px;
  box-shadow: 0 2px 10px rgba(37,99,235,.25);
}
.shelf-block:active { cursor: grabbing; }
.shelf-handle {
  position: absolute; width: 16px; height: 16px; background: #2563eb; border: 2px solid #fff;
  border-radius: 50%; box-shadow: 0 1px 4px rgba(0,0,0,.4);
}
.shelf-handle.nw { top: -8px; left: -8px; cursor: nwse-resize; }
.shelf-handle.ne { top: -8px; right: -8px; cursor: nesw-resize; }
.shelf-handle.sw { bottom: -8px; left: -8px; cursor: nesw-resize; }
.shelf-handle.se { bottom: -8px; right: -8px; cursor: nwse-resize; }
"""

# Static decorative frame: two side posts with slot ticks, top rail, bottom
# rail with small feet. The interior grid (line/level guides + the movable
# block) is drawn on top by JS, since it depends on the runtime container
# size and the actual line/level counts.
_SVG_BODY = """
<rect x="20" y="14" width="16" height="432" fill="#fff" stroke="#1f2937" stroke-width="2.5"/>
<rect x="464" y="14" width="16" height="432" fill="#fff" stroke="#1f2937" stroke-width="2.5"/>
__TICKS__
<line x1="36" y1="26" x2="464" y2="26" stroke="#1f2937" stroke-width="2.5"/>
<line x1="36" y1="434" x2="464" y2="434" stroke="#1f2937" stroke-width="2.5"/>
<polygon points="16,446 40,446 34,458 22,458" fill="#fff" stroke="#1f2937" stroke-width="2"/>
<polygon points="460,446 484,446 478,458 466,458" fill="#fff" stroke="#1f2937" stroke-width="2"/>
"""


def _ticks_svg():
    rows = []
    for i in range(20):
        y = 22 + i * 20
        if y > 440:
            break
        rows.append(f'<rect x="24" y="{y}" width="8" height="5" fill="#1f2937"/>')
        rows.append(f'<rect x="468" y="{y}" width="8" height="5" fill="#1f2937"/>')
    return "\n".join(rows)


_MARKUP = f"""
<div class="shelf-wrap">
  <svg class="shelf-svg" viewBox="0 0 500 460" preserveAspectRatio="none">
    {_SVG_BODY.replace("__TICKS__", _ticks_svg())}
  </svg>
  <div class="shelf-grid-lines"></div>
  <div class="shelf-block">
    <div class="shelf-handle nw"></div>
    <div class="shelf-handle ne"></div>
    <div class="shelf-handle sw"></div>
    <div class="shelf-handle se"></div>
    <span class="shelf-block-label"></span>
  </div>
</div>
"""

_JS = r"""
export default function(component) {
  const { data, setStateValue, parentElement } = component;
  const lines = (data && data.lines) || [];
  const levels = (data && data.levels) || [];
  const n = lines.length, m = levels.length;
  const initial = (data && data.initial) || {lineLo: 0, lineHi: 0, levelLo: 0, levelHi: 0};

  const wrap = parentElement.querySelector('.shelf-wrap');
  const block = parentElement.querySelector('.shelf-block');
  const guideLayer = parentElement.querySelector('.shelf-grid-lines');

  // Interior fractions matching the drawn frame (side posts + top/bottom rails).
  const mLeft = 0.072, mRight = 0.072, mTop = 0.057, mBottom = 0.065;

  const sel = {
    lineLo: Math.max(0, Math.min(initial.lineLo, n - 1)),
    lineHi: Math.max(0, Math.min(initial.lineHi, n - 1)),
    levelLo: Math.max(0, Math.min(initial.levelLo, m - 1)),
    levelHi: Math.max(0, Math.min(initial.levelHi, m - 1)),
  };

  function geom() {
    const rect = wrap.getBoundingClientRect();
    const width = rect.width, height = rect.height;
    const left = width * mLeft, right = width * (1 - mRight);
    const top = height * mTop, bottom = height * (1 - mBottom);
    return { left, top, right, bottom, cellW: (right - left) / n, cellH: (bottom - top) / m };
  }

  function levelFromRow(row) { return m - 1 - row; }
  function rowFromLevel(level) { return m - 1 - level; }

  function renderGuides() {
    guideLayer.innerHTML = '';
    const g = geom();
    for (let i = 1; i < n; i++) {
      const el = document.createElement('div');
      el.className = 'v-guide';
      el.style.left = (g.left + i * g.cellW) + 'px';
      guideLayer.appendChild(el);
    }
    for (let i = 1; i < m; i++) {
      const el = document.createElement('div');
      el.className = 'h-divider';
      el.style.top = (g.top + i * g.cellH) + 'px';
      guideLayer.appendChild(el);
    }
    lines.forEach((label, i) => {
      const el = document.createElement('div');
      el.className = 'shelf-line-label';
      el.style.left = (g.left + (i + 0.5) * g.cellW - 10) + 'px';
      el.style.top = (g.top - 20) + 'px';
      el.textContent = label;
      guideLayer.appendChild(el);
    });
    levels.forEach((label, levelIdx) => {
      const row = rowFromLevel(levelIdx);
      const el = document.createElement('div');
      el.className = 'shelf-level-label';
      el.style.left = (g.left - 24) + 'px';
      el.style.top = (g.top + (row + 0.5) * g.cellH - 8) + 'px';
      el.textContent = label;
      guideLayer.appendChild(el);
    });
  }

  function renderBlock() {
    const g = geom();
    const rowTop = rowFromLevel(sel.levelHi);
    const rowBottom = rowFromLevel(sel.levelLo);
    const left = g.left + sel.lineLo * g.cellW;
    const width = (sel.lineHi - sel.lineLo + 1) * g.cellW;
    const top = g.top + rowTop * g.cellH;
    const height = (rowBottom - rowTop + 1) * g.cellH;
    block.style.left = left + 'px';
    block.style.top = top + 'px';
    block.style.width = width + 'px';
    block.style.height = height + 'px';
    const startLine = lines[sel.lineLo], endLine = lines[sel.lineHi];
    const startLevel = levels[sel.levelLo], endLevel = levels[sel.levelHi];
    const label = (startLine === endLine && startLevel === endLevel)
      ? `${startLine}-${startLevel}`
      : `${startLine}-${startLevel} ~ ${endLine}-${endLevel}`;
    block.querySelector('.shelf-block-label').textContent = label;
  }

  function commit() {
    setStateValue('selection', {
      lineLo: sel.lineLo, lineHi: sel.lineHi, levelLo: sel.levelLo, levelHi: sel.levelHi,
      startLine: lines[sel.lineLo], endLine: lines[sel.lineHi],
      startLevel: levels[sel.levelLo], endLevel: levels[sel.levelHi],
    });
  }

  function colFromX(x) {
    const g = geom();
    return Math.max(0, Math.min(n - 1, Math.round((x - g.left) / g.cellW - 0.5)));
  }
  function rowFromY(y) {
    const g = geom();
    return Math.max(0, Math.min(m - 1, Math.round((y - g.top) / g.cellH - 0.5)));
  }

  let dragMode = null;
  let dragStart = null;
  let dragSelStart = null;

  function beginDrag(mode) {
    return (event) => {
      event.preventDefault();
      event.stopPropagation();
      dragMode = mode;
      dragStart = { x: event.clientX, y: event.clientY };
      dragSelStart = { ...sel };
      try { block.setPointerCapture(event.pointerId); } catch (e) { /* non-pointer trigger */ }
    };
  }

  block.addEventListener('pointerdown', beginDrag('move'));
  ['nw', 'ne', 'sw', 'se'].forEach(corner => {
    const handle = block.querySelector('.shelf-handle.' + corner);
    if (handle) handle.addEventListener('pointerdown', beginDrag(corner));
  });

  block.addEventListener('pointermove', (event) => {
    if (!dragMode) return;
    const g = geom();
    if (dragMode === 'move') {
      const dCols = Math.round((event.clientX - dragStart.x) / g.cellW);
      const dRows = Math.round((event.clientY - dragStart.y) / g.cellH);
      const colSpan = dragSelStart.lineHi - dragSelStart.lineLo;
      const rowSpan = rowFromLevel(dragSelStart.levelLo) - rowFromLevel(dragSelStart.levelHi);
      const startRowTop = rowFromLevel(dragSelStart.levelHi);
      const newLineLo = Math.max(0, Math.min(n - 1 - colSpan, dragSelStart.lineLo + dCols));
      const newRowTop = Math.max(0, Math.min(m - 1 - rowSpan, startRowTop + dRows));
      sel.lineLo = newLineLo;
      sel.lineHi = newLineLo + colSpan;
      sel.levelHi = levelFromRow(newRowTop);
      sel.levelLo = levelFromRow(newRowTop + rowSpan);
    } else {
      const col = colFromX(event.clientX);
      const row = rowFromY(event.clientY);
      const level = levelFromRow(row);
      const anchorLine = dragMode.includes('w') ? dragSelStart.lineHi : dragSelStart.lineLo;
      const anchorLevel = dragMode.includes('n') ? dragSelStart.levelLo : dragSelStart.levelHi;
      sel.lineLo = Math.min(col, anchorLine);
      sel.lineHi = Math.max(col, anchorLine);
      sel.levelLo = Math.min(level, anchorLevel);
      sel.levelHi = Math.max(level, anchorLevel);
    }
    renderBlock();
  });

  function endDrag() {
    if (!dragMode) return;
    dragMode = null;
    commit();
  }
  block.addEventListener('pointerup', endDrag);
  block.addEventListener('pointercancel', endDrag);

  window.addEventListener('resize', () => { renderGuides(); renderBlock(); });
  if (!parentElement.__shelfResizeObserverInstalled) {
    parentElement.__shelfResizeObserverInstalled = true;
    new ResizeObserver(() => { renderGuides(); renderBlock(); }).observe(wrap);
  }
  renderGuides();
  renderBlock();
  commit();
}
"""

_renderer_cache: dict[str, "components_v2.ComponentRenderer"] = {}


def _get_renderer():
    digest = hashlib.sha1((_MARKUP + _CSS + _JS).encode("utf-8")).hexdigest()[:10]
    renderer = _renderer_cache.get(digest)
    if renderer is None:
        renderer = components_v2.component(
            f"shelf_range_picker_{digest}",
            html=_MARKUP,
            css=_CSS,
            js=_JS,
        )
        _renderer_cache.clear()
        _renderer_cache[digest] = renderer
    return renderer


def render_shelf_range_picker(lines, levels, *, initial=None, height=420, key="shelf_range_picker"):
    """Draw the shelf + draggable block and return the current selection dict.

    ``initial``/return value use 0-based indices into ``lines``/``levels`` plus
    the corresponding label strings (``startLine``/``endLine``/``startLevel``/
    ``endLevel``), so callers don't need to re-derive labels from indices.
    """
    component = _get_renderer()
    result = component(
        key=key,
        data={
            "lines": list(lines),
            "levels": list(levels),
            "initial": initial or {"lineLo": 0, "lineHi": 0, "levelLo": 0, "levelHi": 0},
        },
        width="stretch",
        height=height,
        on_selection_change=lambda: None,
    )
    selection = getattr(result, "selection", None)
    return selection if isinstance(selection, dict) else None
