"""Location map service helpers."""

from __future__ import annotations

import json
from html import escape
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from nohtus.config import AREA_CONFIG, SPECIAL_LOCATIONS
from nohtus.db import q
from nohtus.dates import display_date_only

def get_product_image_path(product_name):
    df = q("SELECT image_path FROM products WHERE standard_name=?", (product_name,))
    if df.empty:
        return ""
    value = str(df.iloc[0].get("image_path") or "")
    full = Path(__file__).parent / value
    return str(full) if value and full.exists() else ""


def _loc_group_from_df(df):
    data = {}
    for r in df.itertuples():
        loc = str(r.location)
        data.setdefault(loc, []).append({
            "id": int(r.id),
            "company": str(r.company),
            "product_name": str(r.product_name),
            "warehouse_name": str(r.warehouse_name or "-"),
            "lot": str(r.lot or "-"),
            "exp_date": display_date_only(r.exp_date),
            "qty": int(r.qty),
        })
    return data


def render_location_map():
    """새로고침 없는 로케이션 맵.
    Streamlit 버튼/링크 대신 components.html 내부 JavaScript로 오른쪽 상세패널만 갱신한다.
    """
    df = q("SELECT id, company, product_name, warehouse_name, lot, exp_date, location, qty FROM inventory WHERE qty>0 ORDER BY location, company, product_name")
    loc_data = _loc_group_from_df(df)
    tx = q("""SELECT created_at, tx_type, product_name, lot, exp_date, from_location, to_location, qty
              FROM transactions ORDER BY id DESC LIMIT 300""")
    tx_data = tx.to_dict("records") if not tx.empty else []
    selected_loc = st.session_state.get("selected_location", "")
    payload = json.dumps({"inventory": loc_data, "tx": tx_data, "selected_location": selected_loc}, ensure_ascii=False)

    def dot(loc):
        if loc == "N":
            has = any(x in loc_data for x in SPECIAL_LOCATIONS)
        else:
            has = loc in loc_data or any(k.startswith(loc + "-") for k in loc_data)
        return '<span class="stock-dot"></span>' if has else ''

    def cell(loc, text=None):
        text = text or loc
        return f'<button type="button" class="map-cell" data-loc="{escape(loc)}">{escape(text)}{dot(loc)}</button>'

    def rack(area, labels, left, top, cls):
        cells = ''.join(cell(x) for x in labels)
        return f'<div class="rack {cls}" style="left:{left}px;top:{top}px;">{cells}</div>'

    def zone(loc, text, left, top, w, h, cls="white", extra=""):
        return f'<button type="button" class="zone {cls}" data-loc="{escape(loc)}" style="left:{left}px;top:{top}px;width:{w}px;height:{h}px;{extra}">{text}{dot(loc)}</button>'

    html = f"""
<!doctype html><html><head><meta charset="utf-8">
<style>
*{{box-sizing:border-box}} body{{margin:0;background:#f8fafc;font-family:Inter,Segoe UI,Arial,'Noto Sans KR',sans-serif;color:#0f172a;}}
.wms-wrap{{display:grid;grid-template-columns:minmax(0,3fr) minmax(300px,1fr);gap:22px;align-items:start;width:100%;}}
.map-card,.side-card{{background:#fff;border:1px solid #dbe4f0;border-radius:18px;padding:16px;box-shadow:0 8px 24px rgba(15,23,42,.06);}}
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
.side-card{{height:705px;overflow:auto;}}
.side-title{{font-size:22px;font-weight:900;margin:0 0 4px;}} .caption{{color:#64748b;font-size:13px;margin-bottom:10px;}}
.zone-pill{{display:inline-block;background:#e8f5ee;color:#15803d;font-weight:900;border-radius:10px;padding:6px 10px;margin:8px 0 12px;}}
.metric{{background:#f8fafc;border:1px solid #e2e8f0;border-radius:14px;padding:12px;margin-bottom:12px;}}
.metric .n{{font-size:24px;font-weight:900;}}
.level{{font-size:17px;font-weight:900;margin:14px 0 6px;}}
.level-tabs{{display:flex;align-items:flex-end;gap:0;margin:8px 0 12px;border-bottom:2px solid #111827;}}
.level-tab{{appearance:none;border:2px solid #111827;border-bottom:none;background:#f8fafc;color:#111827;font-weight:900;font-size:15px;padding:9px 18px;border-radius:11px 11px 0 0;margin-right:-1px;cursor:pointer;font-family:inherit;}}
.level-tab.active{{background:#fff;transform:translateY(2px);padding-top:14px;padding-bottom:12px;}}
.level-panel{{display:none;}}
.level-panel.active{{display:block;}}
.detail-card{{background:white;border:1px solid #dbe4f0;border-radius:14px;padding:12px;margin:8px 0;box-shadow:0 5px 16px rgba(15,23,42,.05);}}
.product-inline-detail{{margin:8px 0 14px 0;}}
.card-top{{display:flex;justify-content:space-between;align-items:center;gap:8px;}} .company-badge{{display:inline-block;background:#f1f5f9;color:#475569;font-weight:500;border:1px solid #e2e8f0;border-radius:999px;padding:3px 8px;font-size:12px;}}
.product-title{{font-weight:400;font-size:18px;line-height:1.25;margin-top:8px;margin-bottom:6px;color:#111827;}}
.lot-exp{{font-weight:400;font-size:14px;color:#334155;line-height:1.55;margin-top:6px;}}
.loc-line{{font-weight:400;font-size:14px;color:#334155;line-height:1.55;margin-top:6px;}}
.muted{{color:#64748b;font-size:12px;line-height:1.6;}}
.qty-text{{font-weight:900;color:#111827;white-space:nowrap;}}
.loc-link{{border:1px solid #e2e8f0;background:#ffffff;border-radius:10px;padding:7px 10px;margin:5px 0;width:100%;display:flex;justify-content:space-between;align-items:center;cursor:pointer;color:#0f172a;font-weight:700;}}
.loc-link:hover{{background:#f1f5f9;border-color:#94a3b8;}}
.prod-name-large{{font-size:12pt;font-weight:400;line-height:1.25;color:#111827;margin:8px auto 6px;}}
.prod-search-form{{margin:0;padding:0;}}
.prod-search-title{{appearance:none;border:0;background:transparent;display:block;text-align:center;cursor:pointer;padding:0;font-family:inherit;text-decoration:none;width:100%;}}
.prod-search-title:hover{{color:#1d4ed8;text-decoration:underline;}}
.prod-btn{{display:block;margin:10px auto 0;border:1px solid #bfdbfe;background:#eff6ff;color:#1d4ed8;border-radius:10px;padding:7px 16px;font-weight:800;cursor:pointer;min-width:150px;text-align:center;}}
.prod-box{{border-top:1px solid #e2e8f0;margin-top:14px;padding-top:14px;text-align:center;}} .photo-box{{width:150px;height:150px;margin:0 auto 10px;border:1px dashed #cbd5e1;border-radius:16px;background:#f8fafc;display:flex;align-items:center;justify-content:center;color:#94a3b8;font-weight:700;}}

.detail-total-text{{display:flex;gap:8px;align-items:baseline;justify-content:center;color:#334155;font-size:13px;margin:2px auto 10px;}}
.detail-total-text strong{{font-weight:600;color:#111827;}}
.loc-metric .caption{{text-align:left!important;}}
.recent-title{{text-align:center;margin:8px 0 4px!important;font-size:14px;}}
.recent-list{{text-align:left;}}
.tx-row{{font-size:12px;border-bottom:1px solid #f1f5f9;padding:6px 0;color:#334155;text-align:left;}}
@media(max-width:1100px){{.wms-wrap{{grid-template-columns:1fr}}.side-card{{height:auto}}}}
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
        <button type="button" class="g2 gray" data-loc="G2">G2{dot('G2')}</button>
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
  <div class="side-card" id="detail"><div class="side-title">위치 상세 정보</div><div class="caption">맵에서 로케이션을 선택하면 상세 재고가 여기에 표시됩니다.</div></div>
</div>
<script>
const DATA = {payload};
const inventory = DATA.inventory || {{}};
const txData = DATA.tx || [];
const specialLocations = ["홍보물랙", "회색 카트", "오른쪽 창고", "사무실(4층)"];
const initialSelectedLocation = DATA.selected_location || "";
function zoneName(loc){{
  if(specialLocations.includes(loc||'')) return '기타 위치';
  const area=(loc||'').split('-')[0];
  if(['A1','A2','B1','B2','C1'].includes(area)) return '노투스팜';
  if(['C2','D1'].includes(area)) return '노투스';
  if(area==='E1') return 'NOH';
  if(area==='Q') return '유통기간임박';
  if(area==='F1') return '비자료';
  if(area==='X1') return '폐기';
  if(area==='X2') return '기타 보관 구역';
  if(area==='R1') return '냉장고(자료)';
  if(area==='R2') return '냉장고(비자료)';
  if(area==='REC') return '매입등록대기';
  if(area==='P') return '수출대기';
  if(area==='G2') return '패키지 창고';
  if(area==='N') return '기타 위치';
  return '기타 보관 구역';
}}
function levelLabel(loc){{
  if(specialLocations.includes(loc||'')) return '단 구분 없음';
  const p=(loc||'').split('-');
  if(p[0]==='X1' && p.length===2) return '1단';
  if(p.length>=3 && /^\d+$/.test(p[2])) return parseInt(p[2],10)+'단';
  return '단 구분 없음';
}}
function rowsFor(loc){{
  let rows=[];
  Object.entries(inventory).forEach(([k,v])=>{{ if(k===loc || k.startsWith(loc+'-')) rows=rows.concat(v.map(x=>({{...x, location:k}}))); }});
  return rows;
}}
function formatRecentHistory(tx, currentTotal){{
  if(!tx.length) return '<div class="muted">최근 이력이 없습니다.</div>';
  let running = Number(currentTotal || 0);
  return tx.map(t=>{{
    const type = String(t.tx_type || '이력');
    const qty = Number(t.qty || 0);
    const fromLoc = t.from_location || '-';
    const toLoc = t.to_location || '-';
    let body = '';
    if(type.includes('이동')){{
      body = `${{esc(fromLoc)}} → ${{esc(toLoc)}} (${{qty}}EA)`;
    }} else if(type.includes('입고')){{
      const after = running;
      const before = Math.max(0, after - qty);
      body = `${{before}}EA → ${{after}}EA`;
      running = before;
    }} else if(type.includes('출고')){{
      const after = running;
      const before = after + qty;
      body = `${{before}}EA → ${{after}}EA`;
      running = before;
    }} else if(type.includes('조정')){{
      body = `${{qty}}EA 조정`;
    }} else {{
      body = `${{qty}}EA`;
    }}
    const shownDate = cleanDate(String(t.created_at || '').slice(0,10));
    return `<div class="tx-row">${{esc(shownDate)}} <b>[${{esc(type)}}]</b> ${{body}}</div>`;
  }}).join('');
}}
function productDetail(name){{
  const all=[]; Object.values(inventory).forEach(arr=>arr.forEach(x=>{{ if(x.product_name===name) all.push(x); }}));
  const total=all.reduce((a,b)=>a+(b.qty||0),0);
  const locMap={{}}; const locCompanies={{}};
  Object.entries(inventory).forEach(([loc,arr])=>arr.forEach(x=>{{
    if(x.product_name===name){{
      locMap[loc]=(locMap[loc]||0)+(x.qty||0);
      if(!locCompanies[loc]) locCompanies[loc]=new Set();
      locCompanies[loc].add(x.company||'-');
    }}
  }}));
  const locRows=Object.entries(locMap).sort((a,b)=>a[0].localeCompare(b[0])).map(([loc,qty])=>{{
    const comp=Array.from(locCompanies[loc]||[]).join(', ');
    return `<button class="loc-link" type="button" data-jump-loc="${{esc(loc)}}"><span>${{esc(loc)}} <em style="font-style:normal;color:#64748b;font-size:12px;">${{esc(comp)}}</em></span><span>${{qty}} EA</span></button>`;
  }}).join('');
  const tx=txData.filter(t=>t.product_name===name).slice(0,5);
  return `<div class="prod-box"><div class="photo-box">📷</div><form class="prod-search-form" method="get" target="_top" action="" data-search-form="1"><input type="hidden" name="map_search_product" value="${{esc(name)}}"><button type="submit" class="prod-name-large prod-search-title" data-search-product="${{esc(name)}}">${{esc(name)}}</button></form><div class="detail-total-text"><span>창고 총재고</span><strong>${{total}} EA</strong></div><div class="metric loc-metric"><div class="caption">분산 로케이션</div>${{locRows||'<div class="muted">재고 위치가 없습니다.</div>'}}</div><h4 class="recent-title">최근 이력 5건</h4><div class="recent-list">${{formatRecentHistory(tx,total)}}</div></div>`;
}}
function productCardsHtml(rows){{
  const products={{}};
  rows.forEach(r=>{{
    const key=r.product_name||'-';
    if(!products[key]) products[key]=[];
    products[key].push(r);
  }});
  return Object.entries(products).map(([name,items])=>{{
    const total=items.reduce((a,b)=>a+(Number(b.qty)||0),0);
    const companies=Array.from(new Set(items.map(x=>x.company||'-'))).sort().join(', ');
    const lines=items
      .slice()
      .sort((a,b)=>String(a.exp_date||'').localeCompare(String(b.exp_date||'')) || String(a.lot||'').localeCompare(String(b.lot||'')) || String(a.company||'').localeCompare(String(b.company||'')))
      .map(x=>{{
        const companyInfo = companies.includes(',') ? `<span class="company-badge">${{esc(x.company||'-')}}</span> ` : '';
        return `<div class="lot-exp">${{companyInfo}}${{Number(x.qty)||0}}EA&nbsp;&nbsp;${{esc(x.lot||'-')}} | ${{esc(cleanDate(x.exp_date||'-'))}}</div>`;
      }}).join('');
    return `<div class="detail-card"><div class="card-top"><span class="product-title">${{esc(name)}}</span><span class="qty-text">${{total}} EA</span></div><div class="muted">사업장: ${{esc(companies||'-')}}</div>${{lines}}<button class="prod-btn" type="button" data-product="${{esc(name)}}">제품 상세 보기</button></div>`;
  }}).join('');
}}
function cleanDate(v){{
  const s=String(v ?? '').trim();
  if(!s || s==='-' || s.toLowerCase()==='nan') return '-';
  const m=s.match(/^(\d{{4}})[-/.](\d{{1,2}})[-/.](\d{{1,2}})/);
  if(m) return `${{m[1]}}-${{String(m[2]).padStart(2,'0')}}-${{String(m[3]).padStart(2,'0')}}`;
  return s;
}}
function esc(v){{return String(v ?? '').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#39;')}}
function parentBaseHref(){{
  try {{ return window.top.location.href; }} catch(e) {{}}
  try {{ return window.parent.location.href; }} catch(e) {{}}
  return document.referrer || window.location.href;
}}
function buildParentUrl(key, value, removeKey){{
  const url = new URL(parentBaseHref());
  url.searchParams.set(key, value);
  if(removeKey) url.searchParams.delete(removeKey);
  return url.toString();
}}

function tryParentSearch(productName){{
  try {{
    const doc = window.parent.document;
    const inputs = Array.from(doc.querySelectorAll('input'));
    const input = inputs.find(x => (x.getAttribute('aria-label')||'').includes('제품명 검색'));
    if(input){{
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
      setter.call(input, productName);
      input.dispatchEvent(new InputEvent('input', {{bubbles:true, inputType:'insertText', data:productName}}));
      input.dispatchEvent(new Event('change', {{bubbles:true}}));
      const buttons = Array.from(doc.querySelectorAll('button'));
      const searchBtn = buttons.find(b => (b.innerText||'').trim()==='검색');
      if(searchBtn){{ searchBtn.click(); return true; }}
    }}
  }} catch(e) {{}}
  return false;
}}
function setFormsToParent(){{
  document.querySelectorAll('form[data-search-form]').forEach(f=>{{
    try {{ f.action = buildParentUrl('map_search_product', f.querySelector('[name="map_search_product"]').value || '', 'inbound_loc'); }} catch(e) {{}}
  }});
}}

function navigateTop(href){{
  try {{ window.top.location.assign(href); return; }} catch(e) {{}}
  try {{ window.parent.location.assign(href); return; }} catch(e) {{}}
  try {{ window.open(href, '_top'); return; }} catch(e) {{}}
  const a = document.createElement('a');
  a.href = href;
  a.target = '_top';
  a.rel = 'noopener';
  document.body.appendChild(a);
  a.click();
}}
function showDetail(loc){{
  document.querySelectorAll('[data-loc]').forEach(b=>{{
    const cellLoc = b.dataset.loc || '';
    b.classList.toggle('selected', cellLoc===loc || String(loc||'').startsWith(cellLoc+'-') || (cellLoc==='N' && specialLocations.includes(loc||'')));
  }});
  const rows=rowsFor(loc);
  const d=document.getElementById('detail');
  let title=loc;
  const p=loc.split('-'); if(p.length>=2) title=p[0]+'-'+p[1];
  if(!rows.length){{d.innerHTML=`<div class="side-title">${{esc(title)}}</div><div class="zone-pill">${{esc(zoneName(loc))}}</div><div class="caption">현재 이 로케이션에는 표시할 재고가 없습니다.</div>`; return;}}
  const total=rows.reduce((a,b)=>a+(b.qty||0),0);
  const order={{'1단':0,'2단':1,'3단':2,'단 구분 없음':9}};
  rows.sort((a,b)=>{{return (order[levelLabel(a.location)]??5)-(order[levelLabel(b.location)]??5) || a.company.localeCompare(b.company) || a.product_name.localeCompare(b.product_name);}});
  const grouped={{}};
  rows.forEach(r=>{{const lvl=levelLabel(r.location); if(!grouped[lvl]) grouped[lvl]=[]; grouped[lvl].push(r);}});
  const levels=['1단','2단','3단'].filter(l=>grouped[l]);
  Object.keys(grouped).forEach(l=>{{if(!levels.includes(l)) levels.push(l);}});
  let html=`<div class="side-title">${{esc(title)}}</div><div class="zone-pill">${{esc(zoneName(loc))}}</div><div class="metric"><div class="caption">현재 총재고</div><div class="n">${{total}} EA</div></div>`;
  if(levels.length>1){{
    html+=`<div class="level-tabs">${{levels.map((lvl,i)=>`<button class="level-tab ${{i===0?'active':''}}" type="button" data-level-tab="${{esc(lvl)}}">${{esc(lvl)}}</button>`).join('')}}</div>`;
  }}
  levels.forEach((lvl,i)=>{{
    html+=`<div class="level-panel ${{i===0?'active':''}}" data-level-panel="${{esc(lvl)}}">`;
    if(levels.length===1) html+=`<div class="level">${{esc(lvl)}}</div>`;
    html+=productCardsHtml(grouped[lvl]);
    html+=`</div>`;
  }});
  d.innerHTML=html;
  d.querySelectorAll('[data-level-tab]').forEach(tab=>tab.addEventListener('click',()=>{{
    const lvl=tab.dataset.levelTab;
    d.querySelectorAll('[data-level-tab]').forEach(x=>x.classList.toggle('active', x.dataset.levelTab===lvl));
    d.querySelectorAll('[data-level-panel]').forEach(x=>x.classList.toggle('active', x.dataset.levelPanel===lvl));
  }}));
  d.querySelectorAll('[data-product]').forEach(btn=>btn.addEventListener('click',()=>{{
    const card=btn.closest('.detail-card');
    const old=card.nextElementSibling;
    if(old && old.classList.contains('product-inline-detail')){{old.remove(); btn.disabled=false; return;}}
    d.querySelectorAll('.product-inline-detail').forEach(x=>x.remove());
    d.querySelectorAll('[data-product]').forEach(x=>x.disabled=false);
    card.insertAdjacentHTML('afterend', `<div class="product-inline-detail">${{productDetail(btn.dataset.product)}}</div>`);
    btn.disabled=true;
    const box=card.nextElementSibling;
    box.querySelectorAll('[data-jump-loc]').forEach(j=>j.addEventListener('click',()=>showDetail(j.dataset.jumpLoc)));
    box.querySelectorAll('[data-search-product]').forEach(t=>t.addEventListener('click',(ev)=>{{
      ev.preventDefault();
      ev.stopPropagation();
      const productName = t.dataset.searchProduct || '';
      if(!productName) return;
      if(tryParentSearch(productName)) return;
      const href = buildParentUrl('map_search_product', productName, 'inbound_loc');
      const form = t.closest('form');
      if(form) form.action = href;
      navigateTop(href);
    }}));
    setFormsToParent();
  }}));
}}
function toggleSpecialMenu(forceClose=false){{
  const menu=document.getElementById('specialMenu');
  if(!menu) return;
  if(forceClose){{menu.classList.remove('open'); return;}}
  menu.classList.toggle('open');
}}
document.querySelectorAll('[data-special-loc]').forEach(btn=>btn.addEventListener('click',(ev)=>{{
  ev.preventDefault(); ev.stopPropagation();
  const loc=btn.dataset.specialLoc || '';
  toggleSpecialMenu(true);
  document.querySelectorAll('[data-special-loc]').forEach(x=>x.classList.toggle('selected', x.dataset.specialLoc===loc));
  showDetail(loc);
}}));
document.querySelectorAll('[data-loc]').forEach(btn=>btn.addEventListener('click',(ev)=>{{
  const loc=btn.dataset.loc || '';
  if(loc==='N'){{
    ev.preventDefault(); ev.stopPropagation();
    toggleSpecialMenu(false);
    return;
  }}
  toggleSpecialMenu(true);
  showDetail(loc);
}}));
if(initialSelectedLocation){{setTimeout(()=>showDetail(initialSelectedLocation), 80);}}
</script></body></html>
"""
    components.html(html, height=790, scrolling=False)
