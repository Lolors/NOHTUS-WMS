from __future__ import annotations

import re

import streamlit as st
import streamlit.components.v2 as components_v2

from nohtus.services.location_map_new_layout import _NEW_CSS, _map_markup


_COMPONENT_HTML = f"""
<div class="inbound-map-card">
  <div class="inbound-map-title">도면에서 입고 위치 선택</div>
  {_map_markup()}
</div>
"""

_COMPONENT_CSS = """
* { box-sizing:border-box; }
.inbound-map-card {
  background:#fff;border:1px solid #dbe4f0;border-radius:18px;padding:14px;
  box-shadow:0 8px 24px rgba(15,23,42,.05);width:100%;
  font-family:Inter,Segoe UI,Arial,'Noto Sans KR',sans-serif;color:#0f172a;
}
.inbound-map-title { font-size:18px;font-weight:900;margin:0 0 10px; }
.map-stage button { font-family:inherit; }
""" + re.sub(r"^\s*<style[^>]*>|</style>\s*$", "", _NEW_CSS.strip(), flags=re.S) + """
/* 입고 화면에서는 메인 도면보다 약 4% 작게 표시해 페이지 스크롤을 줄인다. */
.map-stage { transform:scale(.627,.596)!important; }
.map-scroll { height:543px!important; }
@media(max-width:1500px) {
  .map-stage { transform:scale(.56,.532)!important; }
  .map-scroll { height:485px!important; }
}
@media(max-width:1250px) {
  .map-stage { transform:scale(.484,.46)!important; }
  .map-scroll { height:419px!important; }
}
"""

_COMPONENT_JS = r"""
export default function(component) {
  const { data, setStateValue, parentElement } = component;
  const inventory = (data && data.inventory) || {};
  const selectedLocation = String((data && data.selected) || 'REC');

  function locationOf(el) {
    return String(el.dataset.specialLoc || el.dataset.loc || '').trim();
  }
  function markSelected(loc) {
    parentElement.querySelectorAll('.map-stage [data-loc],.map-stage [data-special-loc]').forEach(el => {
      const value = locationOf(el);
      const selected = value === loc || (loc && loc.startsWith(value + '-')) ||
        (value === 'N' && ['오른쪽 창고','사무실(4층)','지엠메딕'].includes(loc));
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
      setStateValue('selection', {location: loc, eventId: Date.now()});
    };
  });
  refreshDots();
  markSelected(selectedLocation);
}
"""

_INBOUND_LOCATION_MAP = components_v2.component(
    "inbound_location_map",
    html=_COMPONENT_HTML,
    css=_COMPONENT_CSS,
    js=_COMPONENT_JS,
)


def render_inbound_quick_location_map():
    """메인 도면을 표시하고 클릭 위치를 Streamlit 상태로 직접 전달한다."""
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

    result = _INBOUND_LOCATION_MAP(
        key="inbound_location_map",
        data={"selected": selected, "inventory": inventory},
        default={"selection": None},
        width="stretch",
        height=587,
        on_selection_change=lambda: None,
    )
    selection = getattr(result, "selection", None) or {}
    clicked = str(selection.get("location", "") or "").strip() if isinstance(selection, dict) else ""
    event_id = selection.get("eventId") if isinstance(selection, dict) else None
    if clicked and event_id != st.session_state.get("_inbound_map_event_id"):
        from nohtus.services.inbound_bridge_runtime import _apply_inbound_location_pending

        st.session_state["_inbound_map_event_id"] = event_id
        st.session_state["_pending_inbound_loc"] = clicked
        _apply_inbound_location_pending()
    return clicked
