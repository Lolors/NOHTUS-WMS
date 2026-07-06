from __future__ import annotations

import json
from html import escape

import streamlit as st
import streamlit.components.v1 as components

from nohtus.db import q


_SPECIAL_LOCATIONS = ["홍보물랙", "회색 카트", "오른쪽 창고", "사무실(4층)"]


def render_inbound_quick_location_map():
    """입고 등록용 로케이션 도면.

    도면 디자인은 유지하고, 클릭값은 URL query param(inbound_loc)으로 전달한다.
    클릭 시 페이지를 이동하지 않고 history.replaceState로 값만 남겨 새로고침을 피한다.
    """
    try:
        df = q("SELECT DISTINCT location FROM inventory WHERE qty>0 ORDER BY location")
        stock_locs = set(df["location"].dropna().astype(str).tolist()) if not df.empty else set()
    except Exception:
        stock_locs = set()

    selected = st.session_state.get("_inbound_selected_loc", "") or "REC"
    selected_js = json.dumps(selected, ensure_ascii=False)
    special_locations_js = json.dumps(_SPECIAL_LOCATIONS, ensure_ascii=False)

    def has_stock(loc):
        if loc == "N":
            return any(x in stock_locs for x in _SPECIAL_LOCATIONS)
        return loc in stock_locs or any(k.startswith(loc + "-") for k in stock_locs)

    def dot(loc):
        return '<span class="stock-dot"></span>' if has_stock(loc) else ""

    def selected_cls(loc):
        return " selected" if selected == loc or (selected and selected.startswith(loc + "-")) else ""

    def cell(loc, text=None):
        text = text or loc
        return f'<button type="button" class="map-cell{selected_cls(loc)}" data-loc="{escape(loc)}">{escape(text)}{dot(loc)}</button>'

    def rack(area, labels, left, top, cls):
        cells = ''.join(cell(x) for x in labels)
        return f'<div class="rack {cls}" style="left:{left}px;top:{top}px;">{cells}</div>'

    def zone(loc, text, left, top, w, h, cls="white", extra=""):
        return f'<button type="button" class="zone {cls}{selected_cls(loc)}" data-loc="{escape(loc)}" style="left:{left}px;top:{top}px;width:{w}px;height:{h}px;{extra}">{text}{dot(loc)}</button>'

    html = f"""
<!doctype html><html><head><meta charset="utf-8">
<style>
*{{box-sizing:border-box}} body{{margin:0;background:#f8fafc;font-family:Inter,Segoe UI,Arial,'Noto Sans KR',sans-serif;color:#0f172a;}}
.wms-wrap{{display:block;width:100%;}}
.map-card{{background:#fff;border:1px solid #dbe4f0;border-radius:18px;padding:16px;box-shadow:0 8px 24px rgba(15,23,42,.06);}}
.legend-wrap{{display:flex;gap:12px;flex-wrap:wrap;margin:0 0 14px 0;}}
.legend-chip{{display:flex;align-items:center;gap:8px;border:1px solid #dbe4f0;background:#fff;border-radius:12px;padding:9px 14px;font-weight:800;color:#111827;font-size:14px;}}
.swatch{{width:18px;height:18px;border-radius:5px;border:1px solid rgba(15,23,42,.12);display:inline-block;}}
.swatch.y{{background:#fff39b}} .swatch.b{{background:#68d2e7}} .swatch.p{{background:#f0a7e6}} .swatch.g{{background:#f3f4f6}}
.map-scroll{{overflow:hidden;padding-bottom:0;height:565px;}}
.map-stage{{position:relative;width:1064px;height:618px;min-width:1064px;background:#fff;border-radius:14px;transform:scale(0.90);transform-origin:top left;}}
.rack{{position:absolute;width:116px;height:154px;display:grid;grid-template-columns:1fr 1fr;grid-template-rows:1fr 1fr 1fr;border:1px solid #334155;border-radius:9px;overflow:hidden;box-shadow:0 6px 14px rgba(15,23,42,.06);}}
.map-cell,.zone{{appearance:none;position:relative;display:flex;align-items:center;justify-content:center;text-decoration:none;color:#0f172a;font-weight:900;font-size:14px;border:0;border-right:1px solid rgba(51,65,85,.38);border-bottom:1px solid rgba(51,65,85,.38);cursor:pointer;font-family:inherit;}}
.map-cell:hover,.zone:hover{{outline:3px solid rgba(37,99,235,.22);z-index:2;}}
.map-cell:nth-child(2n){{border-right:none;}}
.map-cell:nth-child(n+5){{border-bottom:none;}}
.special-menu{{position:absolute;display:none;z-index:30;background:#fff;border:1px solid #cbd5e1;border-radius:12px;box-shadow:0 12px 28px rgba(15,23,42,.18);padding:6px;}}
.special-menu.open{{display:grid;gap:5px;}}
.special-menu button,.special-menu a{{appearance:none;border:1px solid #e2e8f0;background:#f8fafc;border-radius:9px;padding:8px 7px;font-size:12px;font-weight:900;color:#0f172a;cursor:pointer;font-family:inherit;text-align:center;text-decoration:none;}}
.special-menu button:hover,.special-menu button.selected,.special-menu a:hover,.special-menu a.selected{{background:#22c55e;color:#fff;border-color:#16a34a;}}
.map-cell.selected,.zone.selected{{background:#22c55e!important;color:#ffffff!important;outline:3px solid rgba(34,197,94,.35)!important;box-shadow:0 0 0 3px rgba(255,255,255,.8),0 0 18px rgba(34,197,94,.75)!important;border-color:#16a34a!important;z-index:4;}}
.yellow{{background:#fff39b;}} .blue{{background:#68d2e7;}} .pink{{background:#f0a7e6;}} .gray{{background:#f7f8fa;}} .bidata{{background:#d1d5db;}} .white{{background:#fff;}} .yellow .map-cell,.zone.yellow{{background:#fff39b;}} .blue .map-cell,.zone.blue{{background:#68d2e7;}} .pink .map-cell,.zone.pink{{background:#f0a7e6;}} .gray .map-cell,.zone.gray{{background:#f7f8fa;}} .bidata .map-cell,.zone.bidata{{background:#d1d5db;}} .white .map-cell,.zone.white{{background:#fff;}}
.stock-dot{{position:absolute;right:7px;top:7px;width:9px;height:9px;background:#65d84f;border:1.5px solid #166534;border-radius:999px;box-shadow:0 0 0 2px rgba(255,255,255,.65);}}
.zone{{position:absolute;border:1px solid #334155;border-radius:9px;box-shadow:0 6px 14px rgba(15,23,42,.04);}}
.big-left{{position:absolute;left:0;top:0;width:170px;height:258px;border:1px solid #334155;border-radius:10px;overflow:hidden;background:#fff;}}
.big-left button,.big-left a{{appearance:none;position:relative;display:flex;align-items:center;justify-content:center;width:100%;border:0;border-bottom:1px solid #cbd5e1;background:#f7f8fa;color:#0f172a;font-weight:900;cursor:pointer;font-family:inherit;text-decoration:none;}}
.big-left button:hover,.big-left a:hover{{outline:3px solid rgba(37,99,235,.22);z-index:2;}}
.big-left button.selected,.big-left a.selected{{background:#22c55e!important;color:#fff!important;outline:3px solid rgba(34,197,94,.35)!important;box-shadow:0 0 0 3px rgba(255,255,255,.8),0 0 18px rgba(34,197,94,.75)!important;z-index:4;}}
.g2{{height:205px;background:#f7f8fa;}} .g1row{{height:52px;display:grid;grid-template-columns:1fr 1fr 1fr;}}
.g1row button,.g1row a{{height:52px;border-right:1px solid #cbd5e1;border-bottom:none;}} .g1row button:last-child,.g1row a:last-child{{border-right:none;}}
.label{{position:absolute;text-align:center;font-weight:900;color:#111827;font-size:14px;}}
.memo{{position:absolute;color:#334155;font-size:15px;line-height:2.6;}}
.qp{{position:absolute;left:0;top:480px;width:150px;height:135px;border:1px solid #cbd5e1;border-radius:10px;overflow:hidden;background:#fff;}}
.qp button,.qp a{{position:relative;display:grid;grid-template-columns:54px 1fr;align-items:center;width:100%;height:67px;border:0;border-bottom:1px solid #e2e8f0;background:#fff;color:#111827;font-weight:900;cursor:pointer;text-align:left;font-family:inherit;text-decoration:none;}}
.qp button:last-child{{border-bottom:none;}}
.qp button.selected{{background:#22c55e!important;color:#ffffff!important;outline:3px solid rgba(34,197,94,.35)!important;box-shadow:0 0 0 3px rgba(255,255,255,.8),0 0 18px rgba(34,197,94,.75)!important;border-color:#16a34a!important;z-index:4;}}
.qp button.selected .qp-key{{background:#16a34a!important;color:#fff!important;}}
.qp-key{{height:100%;display:flex;align-items:center;justify-content:center;color:#ff221a;font-weight:900;font-size:18px;border-right:1px solid #e2e8f0;}}
.qp .qkey{{background:#f186ca;color:#ff0d0d;}}
.rec-red{{color:#ff1e12;font-weight:900;}}
.small-title{{position:absolute;font-size:14px;font-weight:900;color:#111827;text-align:center;}}
</style></head><body>
<div class="wms-wrap">
  <div class="map-card">
    <div class="legend-wrap">
      <div class="legend-chip"><span class="swatch y"></span>노투스팜</div>
      <div class="legend-chip"><span class="swatch b"></span>노투스</div>
      <div class="legend-chip"><span class="swatch p"></span>NOH</div>
      <div class="legend-chip"><span class="swatch g"></span>비자료</div>
    </div>
    <div class="map-scroll"><div class="map-stage">
      <div class="big-left">
        <button type="button" class="g2 gray{selected_cls('G2')}" data-loc="G2">G2{dot('G2')}</button>
        <div class="g1row">
          <button type="button" data-loc="G1-01">G1-01{dot('G1-01')}</button>
          <button type="button" data-loc="G1-02">G1-02{dot('G1-02')}</button>
          <button type="button" data-loc="G1-03">G1-03{dot('G1-03')}</button>
        </div>
      </div>
      {rack('A2',['A2-03','A2-04','A2-02','A2-05','A2-01','A2-06'],210,0,'yellow')}
      {rack('B2',['B2-03','B2-04','B2-02','B2-05','B2-01','B2-06'],340,0,'yellow')}
      {rack('C2',['C2-03','C2-04','C2-02','C2-05','C2-01','C2-06'],470,0,'blue')}
      {rack('D1',['D1-03','D1-04','D1-02','D1-05','D1-01','D1-06'],600,0,'blue')}
      {zone('T1','T1',600,154,116,48,'white')}
      {rack('E1',['E1-03','E1-04','E1-02','E1-05','E1-01','E1-06'],730,0,'pink')}
      {zone('T2','T2',730,154,116,48,'white')}
      {zone('F1-01','F1-01',875,0,58,48,'bidata')}
      {zone('F1-02','F1-02',933,0,58,48,'bidata')}
      {zone('F1-03','F1-03',991,0,58,48,'bidata')}
      <div class="small-title" style="left:915px;top:66px;width:100px;">비자료</div>
      {zone('X2','X2',1070,0,64,48,'gray')}
      {rack('A1',['A1-03','A1-04','A1-02','A1-05','A1-01','A1-06'],210,245,'yellow')}
      {rack('B1',['B1-03','B1-04','B1-02','B1-05','B1-01','B1-06'],340,245,'yellow')}
      {rack('C1',['C1-03','C1-04','C1-02','C1-05','C1-01','C1-06'],470,245,'yellow')}
      <div class="memo" style="left:760px;top:270px;line-height:1.55;">X1-01~03 : 폐기<br>X1-01-01 : 대표님 시술용</div>
      {zone('X1-01','X1-01',1010,245,58,52,'gray')}
      {zone('X1-02','X1-02',1010,297,58,52,'gray')}
      {zone('X1-03','X1-03',1010,349,58,52,'gray')}
      <div class="qp">
        <button type="button" data-loc="Q"><span class="qp-key qkey">Q</span><span>유통기간임박</span>{dot('Q')}</button>
        <button type="button" data-loc="P"><span class="qp-key">P</span><span>수출대기</span>{dot('P')}</button>
      </div>
      {zone('REC','<span><span class="rec-red">REC</span>eiving</span>',340,520,130,52,'white')}
      <div class="label" style="left:340px;top:582px;width:130px;">매입등록대기</div>
      {zone('R2','R2',725,420,58,52,'white')}
      {zone('R1','R1',783,420,58,52,'white')}
      <div class="label" style="left:706px;top:482px;width:170px;">R2 비자료 / R1 자료</div>
      {zone('N','기타 위치',930,565,155,60,'white')}
      <div class="special-menu" id="specialMenu" style="left:930px;top:428px;width:155px;"><button type="button" data-special-loc="홍보물랙">홍보물랙</button><button type="button" data-special-loc="회색 카트">회색 카트</button><button type="button" data-special-loc="오른쪽 창고">오른쪽 창고</button><button type="button" data-special-loc="사무실(4층)">사무실(4층)</button></div>
    </div></div>
  </div>
</div>
<script>
const specialLocations = {special_locations_js};
const initialSelectedLocation = {selected_js};
function markSelected(loc) {{
  document.querySelectorAll('[data-loc]').forEach(function(b) {{
    const cellLoc = b.dataset.loc || '';
    b.classList.toggle('selected', cellLoc === loc || String(loc || '').startsWith(cellLoc + '-') || (cellLoc === 'N' && specialLocations.includes(loc || '')));
  }});
  document.querySelectorAll('[data-special-loc]').forEach(function(x) {{ x.classList.toggle('selected', x.dataset.specialLoc === loc); }});
}}
function parentBaseHref() {{
  try {{ return window.top.location.href; }} catch(e) {{}}
  try {{ return window.parent.location.href; }} catch(e) {{}}
  return document.referrer || window.location.href;
}}
function writeInboundLoc(loc) {{
  try {{
    const url = new URL(parentBaseHref());
    url.searchParams.set('inbound_loc', loc);
    try {{
      window.top.history.replaceState(null, '', url.toString());
      return true;
    }} catch(e) {{}}
    try {{
      window.parent.history.replaceState(null, '', url.toString());
      return true;
    }} catch(e) {{}}
  }} catch(e) {{}}
  return false;
}}
function applyInboundLoc(loc) {{
  if (!loc) return;
  markSelected(loc);
  try {{ sessionStorage.setItem('nohtus_inbound_loc', loc); }} catch(e) {{}}
  writeInboundLoc(loc);
}}
function toggleSpecialMenu(forceClose) {{
  const menu = document.getElementById('specialMenu');
  if (!menu) return;
  if (forceClose) {{ menu.classList.remove('open'); return; }}
  menu.classList.toggle('open');
}}
function bindActivate(el, handler) {{
  let lastRun = 0;
  function run(ev) {{
    if (ev && ev.type === 'pointerup' && ev.pointerType === 'mouse') return;
    const now = Date.now();
    if (now - lastRun < 350) return;
    lastRun = now;
    if (ev) {{ ev.preventDefault(); ev.stopPropagation(); }}
    handler(ev);
  }}
  el.addEventListener('click', run);
  el.addEventListener('touchend', run, {{passive:false}});
  el.addEventListener('pointerup', run);
}}
document.querySelectorAll('[data-special-loc]').forEach(function(btn) {{
  bindActivate(btn, function() {{
    toggleSpecialMenu(true);
    applyInboundLoc(btn.dataset.specialLoc || '');
  }});
}});
document.querySelectorAll('[data-loc]').forEach(function(btn) {{
  bindActivate(btn, function() {{
    const loc = btn.dataset.loc || '';
    if (loc === 'N') {{
      markSelected('N');
      toggleSpecialMenu(false);
      return;
    }}
    toggleSpecialMenu(true);
    applyInboundLoc(loc);
  }});
}});
if (initialSelectedLocation) {{
  setTimeout(function() {{ markSelected(initialSelectedLocation); }}, 80);
}}
</script></body></html>
"""
    components.html(html, height=650, scrolling=False)
