"""Click/drag shelf range picker.

Renders a shelf graphic (side posts + shelf dividers, in the style of a real
warehouse rack drawing) with an invisible line x level grid of click regions
on top. Clicking a cell toggles it in/out of the selection; dragging paints
every cell the pointer passes over into the selection (like a brush) — the
result can be any shape, not just a rectangle, since a product can occupy an
arbitrary set of cells (e.g. an L-shape spanning part of two racks).
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
.shelf-svg { display: block; width: 100%; height: 100%; }
.shelf-grid-lines { position: absolute; inset: 0; pointer-events: none; }
.h-divider { position: absolute; left: 0; right: 0; height: 0; border-top: 2px solid #94a3b8; }
.h-divider::after {
  content: ""; position: absolute; left: 0; right: 0; top: 4px; height: 0; border-top: 2px solid #94a3b8;
}
.shelf-line-label, .shelf-level-label {
  position: absolute; font-size: 12px; font-weight: 800; color: #475569;
}
.shelf-cells { position: absolute; inset: 0; }
.shelf-cell {
  position: absolute; background: transparent; border-radius: 4px;
  cursor: pointer; transition: background-color .06s ease, border-color .06s ease;
  border: 1px solid transparent;
}
.shelf-cell:hover { background: rgba(100,116,139,.10); }
.shelf-cell.occupied { background: rgba(245,158,11,.12); border: 1px dashed rgba(180,83,9,.45); }
.shelf-cell.selected {
  background: rgba(34,197,94,.35); border: 1px solid rgba(21,128,61,.65);
}
.shelf-cell.occupied.selected {
  background: rgba(34,197,94,.35); border: 1px solid rgba(21,128,61,.65);
}
.shelf-dot { position: absolute; right: 3px; bottom: 3px; width: 8px; height: 8px; border-radius: 999px; background: #d97706; }
"""

# Static decorative frame: two side posts with slot ticks, top rail, bottom
# rail with small feet. The interior grid (line/level guides + click cells)
# is drawn on top by JS, since it depends on the runtime container size and
# the actual line/level counts.
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
  <div class="shelf-cells"></div>
</div>
"""

_JS = r"""
export default function(component) {
  const { data, setStateValue, parentElement } = component;
  const lines = (data && data.lines) || [];
  const levels = (data && data.levels) || [];
  const n = lines.length, m = levels.length;
  const initialCells = (data && data.initial) || [];
  const occupiedSet = new Set(((data && data.occupied) || []).map(c => c.lineIdx + '_' + c.levelIdx));
  // exclusiveClick 모드(입고 등록처럼 "칸 하나 = 위치 하나"가 기본인 화면)에서는
  // 드래그 없이 새 칸을 클릭하면 이전 선택을 지우고 그 칸 하나로 바꾼다(=흔한
  // 단일 선택). 드래그는 그 클릭에서 시작해 계속 이어서 붓칠하듯 범위를 늘릴 수
  // 있다. false(기본, 범위 선택 모달)에서는 클릭마다 계속 더해진다.
  const exclusiveClick = !!(data && data.exclusiveClick);

  const wrap = parentElement.querySelector('.shelf-wrap');
  const svg = parentElement.querySelector('.shelf-svg');
  const guideLayer = parentElement.querySelector('.shelf-grid-lines');
  const cellsLayer = parentElement.querySelector('.shelf-cells');

  // Streamlit wraps this shadow-DOM component in intermediate divs that don't
  // reliably pass a real height down through CSS height:100%, so it can grow
  // to fit content instead of the fixed component box. Force the wrap/svg to
  // the pixel height we were actually given for the component container.
  const fixedHeight = Number(data && data.height) || 420;
  wrap.style.height = fixedHeight + 'px';
  svg.style.height = fixedHeight + 'px';

  // Interior fractions matching the drawn frame (side posts + top/bottom rails).
  const mLeft = 0.072, mRight = 0.072, mTop = 0.057, mBottom = 0.065;

  function cellKey(li, lv) { return li + '_' + lv; }

  // 임의 모양(직사각형이 아니어도 됨)의 선택된 칸 집합. 한 번 그린 칸은 다른
  // 제스처를 시작해도 그대로 남아 있다가, 명시적으로 다시 클릭하거나 "다시
  // 선택" 버튼을 눌러야 지워진다 — 여러 번에 걸쳐 덧칠할 수 있게 하기 위함이다.
  const selected = new Set(
    initialCells
      .filter(c => c && Number.isInteger(c.lineIdx) && Number.isInteger(c.levelIdx))
      .map(c => cellKey(c.lineIdx, c.levelIdx))
  );

  function geom() {
    const rect = wrap.getBoundingClientRect();
    const width = rect.width, height = rect.height;
    const left = width * mLeft, right = width * (1 - mRight);
    const top = height * mTop, bottom = height * (1 - mBottom);
    // `left`/`top`/etc are relative to the wrap box — correct for CSS
    // `style.left`/`style.top` on children of this `position:relative` wrap.
    // Pointer events give viewport-absolute coordinates, so hit-testing needs
    // the wrap's own viewport position added back in.
    return {
      left, top, right, bottom,
      absLeft: rect.left + left, absTop: rect.top + top,
      cellW: (right - left) / n, cellH: (bottom - top) / m,
    };
  }

  function levelFromRow(row) { return m - 1 - row; }
  function rowFromLevel(level) { return m - 1 - level; }

  function renderGuides() {
    guideLayer.innerHTML = '';
    const g = geom();
    // Real shelf boards only exist between levels, not between lines, so only
    // the level boundaries are drawn (no vertical dividers between lines).
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

  const cellEls = {};

  function cellRect(g, lineIdx, levelIdx) {
    const row = rowFromLevel(levelIdx);
    return { left: g.left + lineIdx * g.cellW, top: g.top + row * g.cellH, width: g.cellW, height: g.cellH };
  }

  function buildCells() {
    cellsLayer.innerHTML = '';
    const g = geom();
    for (let li = 0; li < n; li++) {
      for (let lv = 0; lv < m; lv++) {
        const el = document.createElement('div');
        el.className = 'shelf-cell';
        const r = cellRect(g, li, lv);
        el.style.left = r.left + 'px'; el.style.top = r.top + 'px';
        el.style.width = r.width + 'px'; el.style.height = r.height + 'px';
        el.dataset.line = String(li); el.dataset.level = String(lv);
        if (occupiedSet.has(cellKey(li, lv))) {
          el.classList.add('occupied');
          const dot = document.createElement('span');
          dot.className = 'shelf-dot';
          el.appendChild(dot);
        }
        cellsLayer.appendChild(el);
        cellEls[cellKey(li, lv)] = el;
      }
    }
  }

  function layoutCells() {
    const g = geom();
    for (let li = 0; li < n; li++) {
      for (let lv = 0; lv < m; lv++) {
        const el = cellEls[cellKey(li, lv)];
        if (!el) continue;
        const r = cellRect(g, li, lv);
        el.style.left = r.left + 'px'; el.style.top = r.top + 'px';
        el.style.width = r.width + 'px'; el.style.height = r.height + 'px';
      }
    }
  }

  function renderSelection() {
    for (const key in cellEls) {
      cellEls[key].classList.toggle('selected', selected.has(key));
    }
  }

  function commit() {
    const cells = [];
    selected.forEach(key => {
      const [li, lv] = key.split('_').map(Number);
      cells.push({ lineIdx: li, levelIdx: lv, line: lines[li], level: levels[lv] });
    });
    setStateValue('selection', { cells });
  }

  function cellAt(clientX, clientY) {
    const g = geom();
    const col = Math.floor((clientX - g.absLeft) / g.cellW);
    const row = Math.floor((clientY - g.absTop) / g.cellH);
    if (col < 0 || col >= n || row < 0 || row >= m) return null;
    return { line: col, level: levelFromRow(row) };
  }

  let anchor = null;
  let moved = false;
  let anchorWasSelected = false;
  let downX = 0, downY = 0;
  // 클릭할 때 마우스가 완전히 고정돼 있지는 않다 — 몇 픽셀의 자연스러운 떨림이
  // 칸 경계 바로 위에서 일어나면 그 떨림만으로 옆 칸까지 "드래그"로 오인되어,
  // 원래 원하지 않은 칸이 붓칠되고 나면 그 칸은 다시 클릭해도 지워지지 않는
  // 문제가 있었다(드래그로 판정되면 해제 로직을 타지 않기 때문). 포인터가 이
  // 픽셀 거리 이상 실제로 움직이기 전까지는 칸 경계를 넘어도 드래그로 치지
  // 않는다.
  const DRAG_JITTER_PX = 6;

  // Listening on the static, never-moving cellsLayer (not on individual cells
  // or a floating block) means the pointer can never "leave" the drag target
  // mid-gesture, so tracking can't desync into the old block-drag's
  // flip-flopping between the pre-drag and in-progress position.
  cellsLayer.addEventListener('pointerdown', (event) => {
    const cell = cellAt(event.clientX, event.clientY);
    if (!cell) return;
    event.preventDefault();
    try { cellsLayer.setPointerCapture(event.pointerId); } catch (e) { /* non-pointer trigger */ }
    anchor = cell;
    moved = false;
    downX = event.clientX; downY = event.clientY;
    const key = cellKey(cell.line, cell.level);
    anchorWasSelected = selected.has(key);
    if (exclusiveClick && !anchorWasSelected) {
      selected.clear();
    }
    // 클릭한 칸은 곧바로 칠해서(붓을 대는 순간) 즉각적인 피드백을 준다. 드래그
    // 없이 손을 떼면 endDrag()에서 이미 선택돼 있던 칸이었을 경우에만 다시 뺀다.
    selected.add(key);
    renderSelection();
  });

  cellsLayer.addEventListener('pointermove', (event) => {
    if (!anchor) return;
    const dist = Math.hypot(event.clientX - downX, event.clientY - downY);
    if (dist < DRAG_JITTER_PX) return;
    const cell = cellAt(event.clientX, event.clientY);
    if (!cell) return;
    const key = cellKey(cell.line, cell.level);
    if (cell.line !== anchor.line || cell.level !== anchor.level) moved = true;
    if (selected.has(key)) return;
    selected.add(key);
    renderSelection();
  });

  function endDrag() {
    if (!anchor) return;
    if (!moved && anchorWasSelected) {
      // 드래그 없이 이미 선택돼 있던 칸을 다시 클릭한 경우 = 그 칸 하나만 해제.
      // exclusiveClick 모드에서는 위치가 반드시 하나는 있어야 하므로 마지막
      // 남은 한 칸은 클릭으로 지울 수 없게 한다.
      if (!(exclusiveClick && selected.size <= 1)) {
        selected.delete(cellKey(anchor.line, anchor.level));
        renderSelection();
      }
    }
    anchor = null;
    commit();
  }
  cellsLayer.addEventListener('pointerup', endDrag);
  cellsLayer.addEventListener('pointercancel', endDrag);

  window.addEventListener('resize', () => { renderGuides(); layoutCells(); });
  if (!parentElement.__shelfResizeObserverInstalled) {
    parentElement.__shelfResizeObserverInstalled = true;
    new ResizeObserver(() => { renderGuides(); layoutCells(); }).observe(wrap);
  }
  renderGuides();
  buildCells();
  renderSelection();
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


def render_shelf_range_picker(
    lines, levels, *, initial=None, occupied=None, exclusive_click=False, height=420, key="shelf_range_picker"
):
    """Draw the shelf + click/drag cell selector and return the current selection.

    ``initial`` is a list of ``{"lineIdx": int, "levelIdx": int}`` dicts (0-based
    indices into ``lines``/``levels``). ``occupied``는 같은 형식으로, 이미 재고가
    있는 칸을 옅은 점선으로 표시해준다(선택 자체를 막지는 않는다). ``exclusive_click``이
    참이면 드래그 없이 새 칸을 클릭했을 때 이전 선택을 지우고 그 칸 하나로
    바꾼다("칸 하나 = 위치 하나"가 기본인 입고 등록용). 거짓(기본, 범위 선택
    모달)이면 클릭마다 계속 더해진다. 반환값(선택이 바뀌었을 때)은
    ``{"cells": [{"lineIdx", "levelIdx", "line", "level"}, ...]}`` — 클릭/드래그한
    순서 그대로이며, 임의 모양(직사각형이 아니어도 됨)이다. 바뀐 게 없으면
    ``None``을 반환한다.
    """
    component = _get_renderer()
    result = component(
        key=key,
        data={
            "lines": list(lines),
            "levels": list(levels),
            "initial": list(initial or []),
            "occupied": list(occupied or []),
            "exclusiveClick": bool(exclusive_click),
            "height": height,
        },
        width="stretch",
        height=height,
        on_selection_change=lambda: None,
    )
    selection = getattr(result, "selection", None)
    return selection if isinstance(selection, dict) else None
