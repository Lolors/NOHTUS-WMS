from __future__ import annotations

import hashlib
import re

import streamlit as st
import streamlit.components.v2 as components_v2

from nohtus.services.location_map_layout import load_location_map_layout
from nohtus.services.location_map_new_layout import (
    _DYNAMIC_DOTS_JS,
    _NEW_CSS,
    _company_legend_css,
    _map_markup,
    _saved_layout_markup,
)

_STYLE_TAG_RE = re.compile(r"^\s*<style[^>]*>|</style>\s*$", re.S)


def _strip_style_tag(css_html: str) -> str:
    return _STYLE_TAG_RE.sub("", css_html.strip())


def _scope_shared_map_js_to_parent(js: str) -> str:
    """document.* 호출을 컴포넌트 루트(parentElement) 기준으로 바꾼다."""
    js = re.sub(r"document\.getElementById\((['\"])([^'\"]+)\1\)", r"parentElement.querySelector('#\2')", js)
    js = js.replace("document.querySelectorAll(", "parentElement.querySelectorAll(")
    js = js.replace("document.querySelector(", "parentElement.querySelector(")
    return js


def _shared_fit_zoom_pan_js() -> str:
    """메인 로케이션맵과 동일한 핏/줌/팬 로직(positionSpecialMenu ~ installApprovedMapPan)을
    입고 도면 컴포넌트에서 재사용한다. fitApprovedMapToWidth는 제외하고
    아래의 fitMapToContainer로 대체한다(고정 높이 컴포넌트에 맞춰 가로+세로를 모두 맞춤)."""
    before_fit = _DYNAMIC_DOTS_JS.split("function fitApprovedMapToWidth(", 1)[0]
    rest = _DYNAMIC_DOTS_JS.split("function setApprovedMapZoom(", 1)
    after_fit = "function setApprovedMapZoom(" + rest[1] if len(rest) > 1 else ""
    before_dots = after_fit.split("function refreshApprovedMapDots(", 1)[0]
    return _scope_shared_map_js_to_parent(before_fit + before_dots)


_BASE_CSS = """
* { box-sizing:border-box; }
.inbound-map-card {
  background:#fff;border:1px solid #dbe4f0;border-radius:18px;padding:14px;
  box-shadow:0 8px 24px rgba(15,23,42,.05);width:100%;height:100%;
  font-family:Inter,Segoe UI,Arial,'Noto Sans KR',sans-serif;color:#0f172a;
  display:flex;flex-direction:column;overflow:hidden;
}
.inbound-map-title { font-size:18px;font-weight:900;margin:0 0 10px;flex:0 0 auto; }
.map-stage button { font-family:inherit; }
.map-scroll { margin:0 auto; }
"""

_COMPONENT_JS_TEMPLATE = r"""
export default function(component) {
  const { data, setStateValue, parentElement } = component;
  const inventory = (data && data.inventory) || {};
  const serverSelectedLocation = String((data && data.selected) || 'REC');
  const fixedContainerHeight = Number(data && data.height) || 0;

  // The server's `selected` prop for THIS render was computed before this
  // click was known (Python reads its saved location, then calls this
  // component, and only after that does it see the click and update the
  // saved location for the *next* render). So the very next remount briefly
  // re-applies the old location and the highlight snaps back before catching
  // up. Trust our own just-clicked location instead until the server prop
  // actually matches it, so the highlight never visibly reverts.
  let selectedLocation = serverSelectedLocation;
  if (parentElement.__pendingClickLoc && parentElement.__pendingClickLoc !== serverSelectedLocation) {
    selectedLocation = parentElement.__pendingClickLoc;
  } else {
    parentElement.__pendingClickLoc = null;
  }
  const pickTarget = String((data && data.pickTarget) || 'start');
  const rangeSet = new Set(((data && data.selectedRange) || []).map(String));

__SHARED_FIT_ZOOM_PAN_JS__

  function fitMapToContainer(){
    const scroll = parentElement.querySelector('.map-scroll');
    const stage = scroll && scroll.querySelector('.map-stage');
    const card = parentElement.querySelector('.inbound-map-card');
    const title = parentElement.querySelector('.inbound-map-title');
    if (!scroll || !stage || !card) return;
    const naturalWidth = Math.max(1, Number(stage.dataset.naturalWidth) || stage.offsetWidth);
    const naturalHeight = Math.max(1, Number(stage.dataset.naturalHeight) || stage.offsetHeight);
    const cardStyles = getComputedStyle(card);
    const padX = parseFloat(cardStyles.paddingLeft) + parseFloat(cardStyles.paddingRight);
    const padY = parseFloat(cardStyles.paddingTop) + parseFloat(cardStyles.paddingBottom);
    const titleHeight = title ? title.offsetHeight + 10 : 0;
    const availableWidth = Math.max(1, card.clientWidth - padX);
    // card.clientHeight is unreliable here: Streamlit wraps this shadow-DOM
    // component in intermediate divs that never pass a real height down
    // through our CSS's height:100%, so it silently grows to fit content
    // instead of the actual fixed component box. Use the pixel height we
    // were given for the component container instead so scaling is correct.
    const containerHeight = fixedContainerHeight || card.clientHeight;
    const availableHeight = Math.max(1, containerHeight - padY - titleHeight);
    const fittedScale = Math.min(1, availableWidth / naturalWidth, availableHeight / naturalHeight);
    mapFitScale = fittedScale;
    const projected = projectSavedMapToPixels(stage, fittedScale);
    const displayWidth = projected ? stage.offsetWidth : Math.ceil(naturalWidth * fittedScale);
    const displayHeight = projected ? stage.offsetHeight : Math.ceil(naturalHeight * fittedScale);
    scroll.style.setProperty('width', displayWidth + 'px', 'important');
    scroll.style.setProperty('height', displayHeight + 'px', 'important');
    scroll.style.setProperty('overflow', 'hidden', 'important');
    applyApprovedMapTransform();
  }

  function locationOf(el) {
    return String(el.dataset.specialLoc || el.dataset.loc || '').trim();
  }
  const rangeList = Array.from(rangeSet);
  // 도면의 클릭 가능한 칸은 구역-라인 단위(예: A1-13)까지만 있고 개별 단으로는
  // 쪼개져 있지 않다. 범위 목록은 단까지 포함한 전체 위치(A1-13-01 등)이므로,
  // 정확히 일치하지 않아도 그 칸 밑에 속하는 범위 위치가 하나라도 있으면
  // 그 칸 전체를 채워진 것으로 표시한다.
  function inRange(value) {
    return rangeList.some(r => r === value || r.startsWith(value + '-'));
  }
  function markSelected(loc) {
    parentElement.querySelectorAll('.map-stage [data-loc],.map-stage [data-special-loc]').forEach(el => {
      const value = locationOf(el);
      const selected = value === loc || (loc && loc.startsWith(value + '-')) ||
        (value === 'N' && ['오른쪽 창고','사무실(4층)','지엠메딕'].includes(loc)) ||
        inRange(value);
      el.classList.toggle('selected', selected);
    });
  }
  function toggleSpecial(forceClose=false) {
    const menu = parentElement.querySelector('#specialMenu');
    if (!menu) return;
    if (forceClose) menu.classList.remove('open');
    else menu.classList.toggle('open');
  }
  function refreshDots() {
    parentElement.querySelectorAll('.map-stage .dynamic-stock-dot').forEach(el => el.remove());
    const special = ['오른쪽 창고','사무실(4층)','지엠메딕'];
    const hasStock = loc => {
      if (loc === 'N') return special.some(key => (inventory[key] || []).some(row => Number(row.qty || 0) > 0));
      return Object.entries(inventory).some(([key, rows]) =>
        (key === loc || key.startsWith(loc + '-')) &&
        (rows || []).some(row => Number(row.qty || 0) > 0));
    };
    parentElement.querySelectorAll('.map-stage [data-loc]').forEach(el => {
      const loc = String(el.dataset.loc || '').trim();
      if (!loc || !hasStock(loc)) return;
      const dot = document.createElement('span');
      dot.className = 'dynamic-stock-dot';
      el.appendChild(dot);
    });
  }

  parentElement.querySelectorAll('.map-stage [data-loc],.map-stage [data-special-loc]').forEach(el => {
    el.onclick = event => {
      event.preventDefault();
      event.stopPropagation();
      const loc = locationOf(el);
      if (!loc) return;
      if (loc === 'N') {
        markSelected('N');
        toggleSpecial(false);
        return;
      }
      toggleSpecial(true);
      markSelected(loc);
      parentElement.__pendingClickLoc = loc;
      // A click sequence stored on the shadow host (not a local variable) so it
      // keeps counting up across remounts. Date.now() has only millisecond
      // resolution and isn't guaranteed to differ between two renders of this
      // component, which let a later click's event look "already seen" and get
      // silently dropped, appearing to revert to the previous selection.
      parentElement.__moveMapClickSeq = (parentElement.__moveMapClickSeq || 0) + 1;
      setStateValue('selection', {location: loc, eventId: parentElement.__moveMapClickSeq, target: pickTarget});
    };
  });

  refreshDots();
  markSelected(selectedLocation);
  requestAnimationFrame(fitMapToContainer);
  positionSpecialMenu();
  installApprovedMapPan();
  const specialMenuEl = parentElement.querySelector('#specialMenu');
  if (specialMenuEl && !specialMenuEl.__observerInstalled) {
    specialMenuEl.__observerInstalled = true;
    new MutationObserver(positionSpecialMenu).observe(specialMenuEl, {attributes:true, attributeFilter:['class']});
  }
  if (!parentElement.__resizeHandlerInstalled) {
    parentElement.__resizeHandlerInstalled = true;
    window.addEventListener('resize', () => { fitMapToContainer(); positionSpecialMenu(); });
  }
  const cardEl = parentElement.querySelector('.inbound-map-card');
  if (window.ResizeObserver && cardEl && !cardEl.__resizeObserverInstalled) {
    cardEl.__resizeObserverInstalled = true;
    new ResizeObserver(fitMapToContainer).observe(cardEl);
  }
}
"""


def _build_component_js() -> str:
    return _COMPONENT_JS_TEMPLATE.replace("__SHARED_FIT_ZOOM_PAN_JS__", _shared_fit_zoom_pan_js())


def _build_markup_and_css() -> tuple[str, str]:
    """메인 로케이션맵(location_map_new_layout.apply_new_layout)과 동일한 로직으로
    도면 markup/CSS를 구성한다. 저장된 커스텀 레이아웃이 있으면 그대로 반영한다."""
    layout = load_location_map_layout()
    has_saved_layout = bool(layout.get("items"))
    markup = _saved_layout_markup(layout) if has_saved_layout else _map_markup()

    canvas_css = ""
    if has_saved_layout:
        canvas = layout.get("canvas") or {}
        width = max(400, int(canvas.get("width") or 1482))
        height = max(300, int(canvas.get("height") or 910))
        canvas_css = (
            f".map-stage{{width:{width}px!important;height:{height}px!important;"
            f"min-width:{width}px!important;}}"
        )
    legend_css_html = _company_legend_css(layout)
    legend_css = _strip_style_tag(legend_css_html) if legend_css_html else ""

    css = _BASE_CSS + _strip_style_tag(_NEW_CSS.strip()) + canvas_css + legend_css
    html = f"""
<div class="inbound-map-card">
  <div class="inbound-map-title">도면에서 위치 선택</div>
  {markup}
</div>
"""
    return html, css


_QUICK_MAP_HEIGHT = 480

_HIDE_ZOOM_CONTROLS_CSS = ".map-zoom-controls{display:none!important;}"
_HIDE_MAP_TITLE_CSS = ".inbound-map-title{display:none!important;}"

_renderer_cache: dict[str, "components_v2.ComponentRenderer"] = {}


def _get_component_renderer(extra_css: str = ""):
    """저장된 레이아웃이 바뀌면(에디터 저장) 새 markup으로 다시 컴포넌트를 등록한다."""
    html, css = _build_markup_and_css()
    css = css + extra_css
    js = _build_component_js()
    digest = hashlib.sha1((html + css + js).encode("utf-8")).hexdigest()[:10]
    renderer = _renderer_cache.get(digest)
    if renderer is None:
        renderer = components_v2.component(
            f"inbound_location_map_{digest}",
            html=html,
            css=css,
            js=js,
        )
        _renderer_cache.clear()
        _renderer_cache[digest] = renderer
    return renderer


def render_inbound_quick_location_map(pick_target="start", range_locations=None):
    """메인 로케이션맵과 완전히 동일한 도면을 표시하고 클릭 위치를 Streamlit 상태로 직접 전달한다.

    pick_target이 "end"이면 클릭 위치를 시작 위치 대신 범위의 끝 위치로 저장한다
    (여러 칸 범위를 통째로 차지하는 제품의 끝 칸을 도면에서 직접 클릭해 지정할 때 사용).
    """
    selected = st.session_state.get("_inbound_selected_loc", "") or "REC"
    try:
        from nohtus.db import q

        rows = q("SELECT location, qty FROM inventory WHERE qty>0")
        inventory = {}
        for row in rows.itertuples(index=False):
            loc = str(row.location or "").strip()
            if loc:
                inventory.setdefault(loc, []).append({"qty": int(row.qty or 0)})
    except Exception:
        inventory = {}

    component = _get_component_renderer()
    result = component(
        key="inbound_location_map",
        data={
            "selected": selected,
            "inventory": inventory,
            "height": _QUICK_MAP_HEIGHT,
            "pickTarget": pick_target,
            "selectedRange": list(range_locations or []),
        },
        # No `default=` here: giving "selection" a persistent state default made
        # it a state value, and the framework's presenter always prefers state
        # over the fresh trigger event, so a click's own event value only
        # surfaced on the *next* rerun (looked like the previous click winning).
        # Leaving it trigger-only means each click's value is fresh immediately.
        width="stretch",
        height=_QUICK_MAP_HEIGHT,
        on_selection_change=lambda: None,
    )
    selection = getattr(result, "selection", None) or {}
    clicked = str(selection.get("location", "") or "").strip() if isinstance(selection, dict) else ""
    event_id = selection.get("eventId") if isinstance(selection, dict) else None
    click_target = str(selection.get("target", "") or "") if isinstance(selection, dict) else ""
    if clicked and event_id != st.session_state.get("_inbound_map_event_id"):
        st.session_state["_inbound_map_event_id"] = event_id
        if click_target == "end":
            st.session_state["_inbound_range_end_loc"] = clicked
        else:
            from nohtus.services.inbound_bridge_runtime import _apply_inbound_location_pending

            st.session_state["_pending_inbound_loc"] = clicked
            _apply_inbound_location_pending()
        # Without this, the map is re-sent this same run with the *pre-click*
        # selected location (computed above, before we knew about the click),
        # which briefly flashes the new pick then snaps back to the old one
        # once that stale prop reaches the frontend. Rerunning immediately
        # means the next paint carries the already-updated location instead.
        st.rerun()
    return clicked


def render_move_quick_location_map(pick_target="start", range_locations=None):
    """이동 등록의 도착 재고 영역에서 참고용 도면을 보여주고, 클릭한 위치를 도착 위치 선택기에 반영한다.

    pick_target이 "end"이면 클릭 위치를 도착 위치 대신 범위의 끝 위치로 저장한다
    (여러 칸 범위를 통째로 차지하는 제품의 끝 칸을 도면에서 직접 클릭해 지정할 때 사용).
    """
    from nohtus.locations import make_location, parse_location

    defaults = st.session_state.get("_move_picker_defaults", {}) or {}
    selected = make_location(defaults.get("area") or "A1", defaults.get("line") or "", defaults.get("level") or "") if defaults else "A1"

    try:
        from nohtus.db import q

        rows = q("SELECT location, qty FROM inventory WHERE qty>0")
        inventory = {}
        for row in rows.itertuples(index=False):
            loc = str(row.location or "").strip()
            if loc:
                inventory.setdefault(loc, []).append({"qty": int(row.qty or 0)})
    except Exception:
        inventory = {}

    component = _get_component_renderer(extra_css=_HIDE_ZOOM_CONTROLS_CSS + _HIDE_MAP_TITLE_CSS)
    result = component(
        key="move_location_map",
        data={
            "selected": selected,
            "inventory": inventory,
            "height": _QUICK_MAP_HEIGHT,
            "pickTarget": pick_target,
            "selectedRange": list(range_locations or []),
        },
        # See render_inbound_quick_location_map for why there's no `default=` here.
        width="stretch",
        height=_QUICK_MAP_HEIGHT,
        on_selection_change=lambda: None,
    )
    selection = getattr(result, "selection", None) or {}
    clicked = str(selection.get("location", "") or "").strip() if isinstance(selection, dict) else ""
    event_id = selection.get("eventId") if isinstance(selection, dict) else None
    click_target = str(selection.get("target", "") or "") if isinstance(selection, dict) else ""
    if clicked and event_id != st.session_state.get("_move_map_event_id"):
        st.session_state["_move_map_event_id"] = event_id
        if click_target == "end":
            st.session_state["_move_range_end_loc"] = clicked
        else:
            if clicked in ("Q1", "Q2", "Q"):
                area, line, level = "Q", "", ""
            else:
                area, line, level = parse_location(clicked)
            st.session_state["_move_picker_defaults"] = {"area": area or "A1", "line": line or "", "level": level or ""}
            st.session_state["_move_picker_token"] = int(st.session_state.get("_move_picker_token", 0) or 0) + 1
        # See render_inbound_quick_location_map for why this rerun is needed:
        # otherwise the map briefly flashes the new pick then bounces back to
        # the old one, because this run already sent the map the pre-click
        # selected location.
        st.rerun()
    return clicked
