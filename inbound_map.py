from html import escape
from urllib.parse import quote

import streamlit as st
import streamlit.components.v1 as components


def render_inbound_quick_location_map():
    """입고 등록용 로케이션 도면.
    로케이션맵과 같은 components.html 기반 도면을 유지하되,
    클릭은 target="_top" 링크로 부모 Streamlit 앱에 inbound_loc 파라미터를 넘긴다.
    """
    selected = st.session_state.get("_inbound_selected_loc", "") or "REC"

    def is_selected(loc):
        return selected == loc or (selected and selected.startswith(loc + "-"))

    def href(loc):
        return f"?inbound_loc={quote(loc)}"

    def cell(loc, text=None):
        text = text or loc
        cls = " selected" if is_selected(loc) else ""
        return f'<a class="map-cell{cls}" href="{href(loc)}" target="_top" data-inbound-loc="{escape(loc)}" data-loc="{escape(loc)}">{escape(text)}</a>'

    def rack(labels, left, top, cls):
        cells = ''.join(cell(x) for x in labels)
        return f'<div class="rack {cls}" style="left:{left}px;top:{top}px;">{cells}</div>'

    def zone(loc, text, left, top, w, h, cls="white", extra=""):
        selected_cls = " selected" if is_selected(loc) else ""
        return f'<a class="zone {cls}{selected_cls}" href="{href(loc)}" target="_top" data-inbound-loc="{escape(loc)}" data-loc="{escape(loc)}" style="left:{left}px;top:{top}px;width:{w}px;height:{h}px;{extra}">{text}</a>'

    html = f"""
<!doctype html><html><head><meta charset="utf-8">
<style>
*{{box-sizing:border-box}} body{{margin:0;background:#f8fafc;font-family:Inter,Segoe UI,Arial,'Noto Sans KR',sans-serif;color:#0f172a;}}
.inbound-map-card{{background:#fff;border:1px solid #dbe4f0;border-radius:18px;padding:14px 14px 18px;box-shadow:0 8px 24px rgba(15,23,42,.05);width:100%;}}
.title{{font-weight:900;font-size:18px;margin:0 0 10px;color:#111827;}}
.map-scroll{{overflow:visible;height:760px;padding:0;}}
.map-stage{{position:relative;width:1160px;height:704px;min-width:1160px;background:#fff;border-radius:14px;transform:scale(.98);transform-origin:top left;}}
.rack{{position:absolute;width:126px;height:168px;display:grid;grid-template-columns:1fr 1fr;grid-template-rows:1fr 1fr 1fr;border:1px solid #334155;border-radius:9px;overflow:hidden;box-shadow:0 6px 14px rgba(15,23,42,.06);}}
.map-cell,.zone{{appearance:none;position:relative;display:flex;align-items:center;justify-content:center;text-decoration:none;color:#0f172a;font-weight:900;font-size:14px;border:0;border-right:1px solid rgba(51,65,85,.38);border-bottom:1px solid rgba(51,65,85,.38);cursor:pointer;font-family:inherit;}}
.map-cell:hover,.zone:hover{{outline:3px solid rgba(37,99,235,.22);z-index:2;}}
.map-cell:nth-child(2n){{border-right:none;}}
.map-cell:nth-child(n+5){{border-bottom:none;}}

.special-menu{{position:absolute;display:none;z-index:30;background:#fff;border:1px solid #cbd5e1;border-radius:12px;box-shadow:0 12px 28px rgba(15,23,42,.18);padding:6px;}}
.special-menu.open{{display:grid;gap:5px;}}
.special-menu button,.special-menu a{{appearance:none;border:1px solid #e2e8f0;background:#f8fafc;border-radius:9px;padding:8px 7px;font-size:12px;font-weight:900;color:#0f172a;cursor:pointer;font-family:inherit;text-align:center;text-decoration:none;}}
.special-menu button:hover,.special-menu button.selected,.special-menu a:hover,.special-menu a.selected{{background:#22c55e;color:#fff;border-color:#16a34a;}}
.map-cell.selected,.zone.selected{{background:#22c55e!important;color:#ffffff!important;outline:3px solid rgba(34,197,94,.35)!important;box-shadow:0 0 0 3px rgba(255,255,255,.8),0 0 18px rgba(34,197,94,.75)!important;border-color:#16a34a!important;z-index:4;}}
.yellow{{background:#fff39b;}} .blue{{background:#68d2e7;}} .pink{{background:#f0a7e6;}} .gray{{background:#f7f8fa;}} .bidata{{background:#d1d5db;}} .white{{background:#fff;}}
.yellow .map-cell,.zone.yellow{{background:#fff39b;}} .blue .map-cell,.zone.blue{{background:#68d2e7;}} .pink .map-cell,.zone.pink{{background:#f0a7e6;}} .gray .map-cell,.zone.gray{{background:#f7f8fa;}} .bidata .map-cell,.zone.bidata{{background:#d1d5db;}} .white .map-cell,.zone.white{{background:#fff;}}
.zone{{position:absolute;border:1px solid #334155;border-radius:9px;box-shadow:0 6px 14px rgba(15,23,42,.04);}}
.big-left{{position:absolute;left:0;top:0;width:185px;height:282px;border:1px solid #334155;border-radius:10px;overflow:hidden;background:#fff;}}
.big-left a{{appearance:none;position:relative;display:flex;align-items:center;justify-content:center;width:100%;border:0;border-bottom:1px solid #cbd5e1;background:#f7f8fa;color:#0f172a;font-weight:900;cursor:pointer;font-family:inherit;text-decoration:none;}}
.big-left a:hover{{outline:3px solid rgba(37,99,235,.22);z-index:2;}}
.big-left a.selected{{background:#22c55e!important;color:#fff!important;outline:3px solid rgba(34,197,94,.35)!important;box-shadow:0 0 0 3px rgba(255,255,255,.8),0 0 18px rgba(34,197,94,.75)!important;z-index:4;}}
.g2{{height:225px;background:#f7f8fa;}} .g1row{{height:57px;display:grid;grid-template-columns:1fr 1fr 1fr;}}
.g1row a{{height:57px;border-right:1px solid #cbd5e1;border-bottom:none;}} .g1row a:last-child{{border-right:none;}}
.label{{position:absolute;text-align:center;font-weight:900;color:#111827;font-size:14px;}}
.memo{{position:absolute;color:#334155;font-size:15px;line-height:1.65;}}
.qp{{position:absolute;left:0;top:525px;width:165px;height:148px;border:1px solid #cbd5e1;border-radius:10px;overflow:hidden;background:#fff;}}
.qp a{{position:relative;display:grid;grid-template-columns:58px 1fr;align-items:center;width:100%;height:74px;border:0;border-bottom:1px solid #e2e8f0;background:#fff;color:#111827;font-weight:900;cursor:pointer;text-align:left;font-family:inherit;text-decoration:none;}}
.qp a:last-child{{border-bottom:none;}}
.qp a.selected{{background:#22c55e!important;color:#ffffff!important;outline:3px solid rgba(34,197,94,.35)!important;box-shadow:0 0 0 3px rgba(255,255,255,.8),0 0 18px rgba(34,197,94,.75)!important;border-color:#16a34a!important;z-index:4;}}
.qp-key{{height:100%;display:flex;align-items:center;justify-content:center;color:#ff221a;font-weight:900;font-size:18px;border-right:1px solid #e2e8f0;}}
.qp .qkey{{background:#f186ca;color:#ff0d0d;}}
.rec-red{{color:#ff1e12;font-weight:900;}}
.small-title{{position:absolute;font-size:14px;font-weight:900;color:#111827;text-align:center;}}
</style></head><body>
<div class="inbound-map-card">
  <div class="title">도면에서 입고 위치 선택</div>
  <div class="map-scroll"><div class="map-stage">
    <div class="big-left">
      <a class="g2 gray{' selected' if is_selected('G2') else ''}" href="?inbound_loc=G2" target="_top" data-inbound-loc="G2">G2</a>
      <div class="g1row">
        {cell('G1-01')}{cell('G1-02')}{cell('G1-03')}
      </div>
    </div>
    {rack(['A2-03','A2-04','A2-02','A2-05','A2-01','A2-06'],230,0,'yellow')}
    {rack(['B2-03','B2-04','B2-02','B2-05','B2-01','B2-06'],372,0,'yellow')}
    {rack(['C2-03','C2-04','C2-02','C2-05','C2-01','C2-06'],514,0,'blue')}
    {rack(['D1-03','D1-04','D1-02','D1-05','D1-01','D1-06'],656,0,'blue')}
    {zone('T1','T1',656,168,126,52,'white')}
    {rack(['E1-03','E1-04','E1-02','E1-05','E1-01','E1-06'],798,0,'pink')}
    {zone('T2','T2',798,168,126,52,'white')}
    {zone('F1-01','F1-01',955,0,64,52,'bidata')}
    {zone('F1-02','F1-02',1019,0,64,52,'bidata')}
    {zone('F1-03','F1-03',1083,0,64,52,'bidata')}
    <div class="small-title" style="left:996px;top:72px;width:110px;">비자료</div>
    {zone('X2','X2',1070,78,70,52,'gray')}
    {rack(['A1-03','A1-04','A1-02','A1-05','A1-01','A1-06'],230,268,'yellow')}
    {rack(['B1-03','B1-04','B1-02','B1-05','B1-01','B1-06'],372,268,'yellow')}
    {rack(['C1-03','C1-04','C1-02','C1-05','C1-01','C1-06'],514,268,'yellow')}
    <div class="memo" style="left:800px;top:292px;">X1-01~03 : 폐기<br>X1-01-01 : 대표님 시술용</div>
    {zone('X1-01','X1-01',1090,268,64,56,'gray')}
    {zone('X1-02','X1-02',1090,324,64,56,'gray')}
    {zone('X1-03','X1-03',1090,380,64,56,'gray')}
    <div class="qp">
      <a class="{'selected' if is_selected('Q1') or is_selected('Q2') else ''}" href="?inbound_loc=Q" target="_top" data-inbound-loc="Q"><span class="qp-key qkey">Q</span><span>유통기간임박</span></a>
      <a class="{'selected' if is_selected('P') else ''}" href="?inbound_loc=P" target="_top" data-inbound-loc="P"><span class="qp-key">P</span><span>수출대기</span></a>
    </div>
    {zone('REC','<span><span class="rec-red">REC</span>eiving</span>',372,568,142,56,'white')}
    <div class="label" style="left:372px;top:635px;width:142px;">매입등록대기</div>
    {zone('R2','R2',790,460,64,56,'white')}
    {zone('R1','R1',854,460,64,56,'white')}
    <div class="label" style="left:770px;top:526px;width:190px;">R2 비자료 / R1 자료</div>
    {zone('N','기타 위치',975,628,168,60,'white')}
    <div class="special-menu" id="inboundSpecialMenu" style="left:975px;top:492px;width:168px;"><a href="?inbound_loc=홍보물랙" target="_top" data-inbound-loc="홍보물랙">홍보물랙</a><a href="?inbound_loc=회색 카트" target="_top" data-inbound-loc="회색 카트">회색 카트</a><a href="?inbound_loc=오른쪽 창고" target="_top" data-inbound-loc="오른쪽 창고">오른쪽 창고</a><a href="?inbound_loc=사무실(4층)" target="_top" data-inbound-loc="사무실(4층)">사무실(4층)</a></div>
  </div></div>
</div>
<script>
function parentBaseHref(){{
  try {{ return window.top.location.href; }} catch(e) {{}}
  try {{ return window.parent.location.href; }} catch(e) {{}}
  return document.referrer || window.location.href;
}}
function buildParentUrl(key, value){{
  const url = new URL(parentBaseHref());
  url.searchParams.set(key, value);
  url.searchParams.delete('map_search_product');
  return url.toString();
}}
function navigateTop(href){{
  try {{ window.top.location.assign(href); return; }} catch(e) {{}}
  try {{ window.parent.location.assign(href); return; }} catch(e) {{}}
  try {{ window.open(href, '_top'); return; }} catch(e) {{}}
  const a = document.createElement('a');
  a.href = href;
  a.target = '_top';
  document.body.appendChild(a);
  a.click();
}}
function markSelected(loc){{
  document.querySelectorAll('[data-inbound-loc]').forEach(x => {{
    const v = x.getAttribute('data-inbound-loc') || '';
    x.classList.toggle('selected', v === loc || (loc && loc.startsWith(v + '-')) || (v === 'N' && ['홍보물랙','회색 카트','오른쪽 창고','사무실(4층)'].includes(loc)));
  }});
}}
function tryParentInbound(loc){{
  try {{
    const doc = window.parent.document;
    // 핵심: Streamlit text_input 값 확정 타이밍에 의존하지 않는다.
    // 먼저 부모 URL의 query parameter에 클릭 위치를 심고, 숨김 버튼은 rerun 트리거로만 사용한다.
    try {{
      const url = new URL(parentBaseHref());
      url.searchParams.set('inbound_loc', loc);
      url.searchParams.delete('map_search_product');
      if (window.parent && window.parent.history && window.parent.history.replaceState) {{
        window.parent.history.replaceState(null, '', url.toString());
      }} else if (window.top && window.top.history && window.top.history.replaceState) {{
        window.top.history.replaceState(null, '', url.toString());
      }}
    }} catch(e) {{}}

    const input = doc.querySelector('input[aria-label="__입고도면선택값"]');
    if (input) {{
      try {{
        const setter = Object.getOwnPropertyDescriptor(window.parent.HTMLInputElement.prototype, 'value').set;
        setter.call(input, loc);
      }} catch(e) {{
        input.value = loc;
      }}
      input.dispatchEvent(new InputEvent('input', {{bubbles:true, inputType:'insertText', data:loc}}));
      input.dispatchEvent(new Event('change', {{bubbles:true}}));
    }}

    let applied = false;
    doc.querySelectorAll('button').forEach(btn => {{
      if ((btn.innerText || '').trim() === '__입고도면적용') {{
        setTimeout(() => btn.click(), 30);
        applied = true;
      }}
    }});
    return applied;
  }} catch(e) {{
    return false;
  }}
}}
function toggleInboundSpecialMenu(forceClose=false){{
  const menu=document.getElementById('inboundSpecialMenu');
  if(!menu) return;
  if(forceClose){{menu.classList.remove('open'); return;}}
  menu.classList.toggle('open');
}}
document.querySelectorAll('[data-inbound-loc]').forEach(el => {{
  el.addEventListener('click', (ev) => {{
    ev.preventDefault();
    ev.stopPropagation();
    const loc = el.getAttribute('data-inbound-loc') || '';
    if(!loc) return;
    if(loc === 'N'){{
      markSelected('N');
      toggleInboundSpecialMenu(false);
      return;
    }}
    toggleInboundSpecialMenu(true);
    markSelected(loc);
    if(tryParentInbound(loc)) return;
    const href = buildParentUrl('inbound_loc', loc);
    el.setAttribute('href', href);
    el.setAttribute('target', '_top');
    navigateTop(href);
  }});
}});
</script>
</body></html>
"""
    components.html(html, height=780, scrolling=False)


