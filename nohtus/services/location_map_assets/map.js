const inventory = DATA.inventory || {};
const txData = DATA.tx || [];
const specialLocations = ["오른쪽 창고", "사무실(4층)"];
const initialSelectedLocation = DATA.selected_location || "";
const layoutCompany = DATA.layout_company || {};
const layoutLabel = DATA.layout_label || {};
const areaConfig = DATA.area_config || {};
const reversedLineRanges = DATA.reversed_line_ranges || {};
const RACK_GROUP_SIZE = 3;
// 같은 알파벳 구역 안에서 두 줄 선반이 마주보는 경우, 뒷줄은 번호가 클수록
// 왼쪽에 오도록(오름차순의 반대로) 그려야 실제 배치와 맞는다.
function lineGroupIsReversed(area, cols){
  const range = reversedLineRanges[area];
  if (!range || !cols || !cols.length) return false;
  const first = parseInt(cols[0], 10);
  return Number.isFinite(first) && first >= range[0] && first <= range[1];
}
function zoneName(loc, rows){
  const area=(loc||'').split('-')[0];
  const customLabel = layoutLabel[loc] || layoutLabel[area];
  if(customLabel) return customLabel;
  if((loc||'')==='홍보물랙') return '홍보물랙';
  if(specialLocations.includes(loc||'')) return '기타 위치';
  if(['A1','A2','B1','B2','C1','C2','D1','E1'].includes(area)){
    const companies=Array.from(new Set((rows||[]).map(r=>r.company).filter(Boolean)));
    if(companies.length) return companies.join(', ');
    const p=(loc||'').split('-');
    const cellCode=p.length>=2 ? p[0]+'-'+p[1] : loc;
    return layoutCompany[cellCode] || layoutCompany[loc] || '-';
  }
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
}
function rowsFor(loc){
  let rows=[];
  Object.entries(inventory).forEach(([k,v])=>{ if(k===loc || k.startsWith(loc+'-')) rows=rows.concat(v.map(x=>({...x, location:k}))); });
  return rows;
}
function formatRecentHistory(tx, currentTotal){
  if(!tx.length) return '<div class="muted">최근 이력이 없습니다.</div>';
  let running = Number(currentTotal || 0);
  return tx.map(t=>{
    const type = String(t.tx_type || '이력');
    const qty = Number(t.qty || 0);
    const fromLoc = t.from_location || '-';
    const toLoc = t.to_location || '-';
    let body = '';
    if(type.includes('이동')){
      body = `${esc(fromLoc)} → ${esc(toLoc)} (${qty}EA)`;
    } else if(type.includes('입고')){
      const after = running;
      const before = Math.max(0, after - qty);
      body = `${before}EA → ${after}EA`;
      running = before;
    } else if(type.includes('출고')){
      const after = running;
      const before = after + qty;
      body = `${before}EA → ${after}EA`;
      running = before;
    } else if(type.includes('조정')){
      body = `${qty}EA 조정`;
    } else {
      body = `${qty}EA`;
    }
    const shownDate = cleanDate(String(t.created_at || '').slice(0,10));
    return `<div class="tx-row">${esc(shownDate)} <b>[${esc(type)}]</b> ${body}</div>`;
  }).join('');
}
function rangeSummaryLabel(cells){
  const area=lineCode(cells[0]).split('-')[0];
  const lines=Array.from(new Set(cells.map(c=>c.split('-')[1]||''))).filter(Boolean).sort();
  const lineSpan = lines.length>1 ? `${lines[0]}~${lines[lines.length-1]}` : (lines[0]||'');
  return `${area}-${lineSpan} (여러 위치, ${cells.length}칸)`;
}
function productDetail(name){
  // 재고 행 하나가 여러 칸(location_range_cells)에 걸쳐 있으면 rowsFor류
  // 순회에서 칸 수만큼 중복 등장한다. id로 한 번만 세야 이 행의 실제 수량이
  // 칸마다 반복 표시되지 않는다.
  const rowsById={};
  Object.values(inventory).forEach(arr=>arr.forEach(x=>{ if(x.product_name===name) rowsById[x.id]=x; }));
  const rows=Object.values(rowsById);
  const total=rows.reduce((a,b)=>a+(b.qty||0),0);
  const locRows=rows
    .slice()
    .sort((a,b)=>(a.primary_location||'').localeCompare(b.primary_location||''))
    .map(x=>{
      const cells=(x.occupied_cells && x.occupied_cells.length) ? x.occupied_cells : [x.primary_location];
      const jumpLoc=x.primary_location || cells[0] || '';
      const label = cells.length>1 ? rangeSummaryLabel(cells) : (jumpLoc || '-');
      return `<button class="loc-link" type="button" data-jump-loc="${esc(jumpLoc)}"><span>${esc(label)} <em style="font-style:normal;color:#64748b;font-size:12px;">${esc(x.company||'-')}</em></span><span>${Number(x.qty)||0} EA</span></button>`;
    }).join('');
  const tx=txData.filter(t=>t.product_name===name).slice(0,5);
  return `<div class="prod-box"><div class="photo-box">📷</div><form class="prod-search-form" method="get" target="_top" action="" data-search-form="1"><input type="hidden" name="map_search_product" value="${esc(name)}"><button type="submit" class="prod-name-large prod-search-title" data-search-product="${esc(name)}">${esc(name)}</button></form><div class="detail-total-text"><span>창고 총재고</span><strong>${total} EA</strong></div><div class="metric loc-metric"><div class="caption">분산 로케이션</div>${locRows||'<div class="muted">재고 위치가 없습니다.</div>'}</div><h4 class="recent-title">최근 이력 5건</h4><div class="recent-list">${formatRecentHistory(tx,total)}</div></div>`;
}
function occupiedKey(cells){ return (cells||[]).slice().sort().join(','); }
function lineCode(loc){
  const p=(loc||'').split('-');
  return p.length>=2 ? p[0]+'-'+p[1] : loc;
}
// 메인 2D 맵은 라인(X축)까지만 표현하고 단(Y축)은 표현하지 않는다. 그래서
// "이 위치를 포함하는 재고"가 실제로 어느 단에 얼마나 있는지는 재고 행 단위로
// 작은 라인×단 그림(미니 랙)을 그려서 보여준다 — 로케이션 하나가 아니라
// 이 재고 행이 실제로 차지하는 정확한 모양 그대로.
function miniRackHtml(occupiedCells){
  if(!occupiedCells || !occupiedCells.length) return {html:'', lines:[]};
  const area=lineCode(occupiedCells[0]).split('-')[0];
  const cfg=areaConfig[area] || {};
  const areaLines=cfg.lines || [];
  const areaLevels=cfg.levels || [];
  if(!areaLines.length || !areaLevels.length) return {html:'', lines:[]};
  const touchedLines=Array.from(new Set(occupiedCells.map(c=>c.split('-')[1]||''))).filter(Boolean);
  const touchedIdx=touchedLines.map(l=>areaLines.indexOf(l)).filter(i=>i>=0);
  if(!touchedIdx.length) return {html:'', lines:[]};
  const anchorIdx=Math.min(...touchedIdx);
  const groupStart=Math.floor(anchorIdx / RACK_GROUP_SIZE) * RACK_GROUP_SIZE;
  let cols=areaLines.slice(groupStart, groupStart + RACK_GROUP_SIZE);
  // 이 랙 묶음이 "뒷줄"(마주보는 두 줄 중 번호가 큰 쪽)이면 왼쪽→오른쪽
  // 그리는 순서를 뒤집는다 — 실제 창고에서는 뒷줄이 번호 오름차순과 반대로
  // 배치돼 있기 때문이다(저장되는 라인 값 자체는 바뀌지 않는다).
  if(lineGroupIsReversed(area, cols)) cols=cols.slice().reverse();
  const occSet=new Set(occupiedCells);
  const rowsHtml=areaLevels.slice().reverse().map(level=>{
    const cellsHtml=cols.map(line=>{
      const filled=occSet.has(`${area}-${line}-${level}`);
      return `<span class="mini-rack-cell${filled ? ' filled' : ''}"></span>`;
    }).join('');
    return `<div class="mini-rack-row"><span class="mini-rack-level">${esc(level)}단</span><span class="mini-rack-cells">${cellsHtml}</span></div>`;
  }).join('');
  // 라벨은 그림칸(cols, 랙 3라인 전체)이 아니라 실제로 채워진 라인만 기준으로
  // 써야 한다 — cols로 쓰면 범위를 1칸으로 줄여도 랙 전체 구간("A1-13~15")이
  // 그대로 남아 있는 것처럼 보여서, 마치 이전의 더 큰 범위가 아직도 선택돼
  // 있는 것 같은 착시를 일으킨다.
  const touchedSorted=touchedIdx.slice().sort((a,b)=>a-b).map(i=>areaLines[i]);
  const rangeLabel = touchedSorted.length>1 ? `${area}-${touchedSorted[0]}~${touchedSorted[touchedSorted.length-1]}` : `${area}-${touchedSorted[0]}`;
  const html=`<div class="mini-rack">${rowsHtml}<div class="mini-rack-label">${esc(rangeLabel)}</div></div>`;
  // 메인 맵 하이라이트는 실제로 점유한 라인만 켠다(랙 전체 3라인 창이 아니라).
  // 미니 랙은 같은 랙 단위를 보여주려고 3라인을 다 그리지만, 안 채워진 라인까지
  // 메인 맵에서 켜면 실제로 안 쓰는 라인도 점유한 것처럼 보이게 된다.
  const lines=areaLines.filter(l=>touchedLines.includes(l)).map(line=>`${area}-${line}`);
  return {html, lines};
}
function productCardsHtml(rows){
  const groups={};
  rows.forEach(r=>{
    const key=(r.product_name||'-') + '::' + occupiedKey(r.occupied_cells);
    if(!groups[key]) groups[key]={name:r.product_name||'-', occupied_cells:r.occupied_cells||[], itemsById:{}};
    // 한 재고 행이 여러 칸에 걸쳐 있으면(location_range_cells) rowsFor()가 그 칸
    // 수만큼 같은 id를 중복해서 넘긴다. id로 한 번만 세야 수량이 곱절로 잡히지 않는다.
    groups[key].itemsById[r.id]=r;
  });
  return Object.values(groups).map(group=>{
    const {name, occupied_cells}=group;
    const items=Object.values(group.itemsById);
    const total=items.reduce((a,b)=>a+(Number(b.qty)||0),0);
    const companies=Array.from(new Set(items.map(x=>x.company||'-'))).sort().join(', ');
    const lines=items
      .slice()
      .sort((a,b)=>String(a.exp_date||'').localeCompare(String(b.exp_date||'')) || String(a.lot||'').localeCompare(String(b.lot||'')) || String(a.company||'').localeCompare(String(b.company||'')))
      .map(x=>{
        const companyInfo = companies.includes(',') ? `<span class="company-badge">${esc(x.company||'-')}</span> ` : '';
        return `<div class="lot-exp">${companyInfo}${Number(x.qty)||0}EA&nbsp;&nbsp;${esc(x.lot||'-')} | ${esc(cleanDate(x.exp_date||'-'))}<button class="lot-move-btn" type="button" data-move-id="${esc(x.id)}" style="margin-left:8px;padding:1px 8px;font-size:11px;border-radius:6px;border:1px solid #2563eb;color:#2563eb;background:#eff6ff;cursor:pointer;">이동</button></div>`;
      }).join('');
    const rack=miniRackHtml(occupied_cells);
    return `<div class="detail-card" data-occupied-lines="${esc(rack.lines.join(','))}"><div class="card-top"><span class="product-title">${esc(name)}</span><span class="qty-text">${total} EA</span></div><div class="muted">사업장: ${esc(companies||'-')}</div>${rack.html}${lines}<button class="prod-btn" type="button" data-product="${esc(name)}">제품 상세 보기</button></div>`;
  }).join('');
}
function cleanDate(v){
  const s=String(v ?? '').trim();
  if(!s || s==='-' || s.toLowerCase()==='nan') return '-';
  const m=s.match(/^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})/);
  if(m) return `${m[1]}-${String(m[2]).padStart(2,'0')}-${String(m[3]).padStart(2,'0')}`;
  return s;
}
function esc(v){return String(v ?? '').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#39;')}
function parentBaseHref(){
  try { return window.top.location.href; } catch(e) {}
  try { return window.parent.location.href; } catch(e) {}
  return document.referrer || window.location.href;
}
function buildParentUrl(key, value, removeKey){
  const url = new URL(parentBaseHref());
  url.searchParams.set(key, value);
  if(removeKey) url.searchParams.delete(removeKey);
  return url.toString();
}
function buildParentUrlMulti(setParams, removeKeys){
  const url = new URL(parentBaseHref());
  Object.entries(setParams||{}).forEach(([k,v])=>url.searchParams.set(k,v));
  (removeKeys||[]).forEach(k=>url.searchParams.delete(k));
  return url.toString();
}

function tryParentSearch(productName){
  try {
    const doc = window.parent.document;
    const inputs = Array.from(doc.querySelectorAll('input'));
    const input = inputs.find(x => (x.getAttribute('aria-label')||'').includes('제품명 검색'));
    if(input){
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
      setter.call(input, productName);
      input.dispatchEvent(new InputEvent('input', {bubbles:true, inputType:'insertText', data:productName}));
      input.dispatchEvent(new Event('change', {bubbles:true}));
      const buttons = Array.from(doc.querySelectorAll('button'));
      const searchBtn = buttons.find(b => (b.innerText||'').trim()==='검색');
      if(searchBtn){ searchBtn.click(); return true; }
    }
  } catch(e) {}
  return false;
}
function setFormsToParent(){
  document.querySelectorAll('form[data-search-form]').forEach(f=>{
    try { f.action = buildParentUrl('map_search_product', f.querySelector('[name="map_search_product"]').value || '', 'inbound_loc'); } catch(e) {}
  });
}

function navigateTop(href){
  try { window.top.location.assign(href); return; } catch(e) {}
  try { window.parent.location.assign(href); return; } catch(e) {}
  try { window.open(href, '_top'); return; } catch(e) {}
  const a = document.createElement('a');
  a.href = href;
  a.target = '_top';
  a.rel = 'noopener';
  document.body.appendChild(a);
  a.click();
}
function highlightLines(lineCodes, on){
  if(!lineCodes || !lineCodes.length) return;
  document.querySelectorAll('[data-loc]').forEach(el=>{
    if(lineCodes.includes(el.dataset.loc)) el.classList.toggle('line-soft', on);
  });
}
function showDetail(loc){
  document.querySelectorAll('.line-soft').forEach(el=>el.classList.remove('line-soft'));
  document.querySelectorAll('[data-loc]').forEach(b=>{
    const cellLoc = b.dataset.loc || '';
    b.classList.toggle('selected', cellLoc===loc || String(loc||'').startsWith(cellLoc+'-') || (cellLoc==='N' && specialLocations.includes(loc||'')));
  });
  const rows=rowsFor(loc);
  const d=document.getElementById('detail');
  let title=loc;
  const p=loc.split('-'); if(p.length>=2) title=p[0]+'-'+p[1];
  if(!rows.length){d.innerHTML=`<div class="side-title">${esc(title)}</div><div class="zone-pill">${esc(zoneName(loc, rows))}</div><div class="caption">현재 이 로케이션에는 표시할 재고가 없습니다.</div>`; return;}
  // 단(段)별 탭으로 나누면 여러 단에 걸친 재고 행(location_range_cells)이
  // 탭마다 중복 표시된다. 미니 랙이 이미 재고 행 하나당 정확한 단 점유
  // 모양을 보여주므로, 탭 없이 이 위치를 포함하는 재고를 그대로 나열한다.
  const groupCount=new Set(rows.map(r=>(r.product_name||'-') + '::' + occupiedKey(r.occupied_cells))).size;
  let html=`<div class="side-title">${esc(title)}</div><div class="zone-pill">${esc(zoneName(loc, rows))}</div><div class="metric"><div class="caption">이 위치를 포함하는 재고</div><div class="n">${groupCount}건</div><div class="muted" style="margin-top:6px;">제품을 선택하면 점유 영역이 지도에 표시됩니다.</div></div>`;
  html+=productCardsHtml(rows);
  d.innerHTML=html;
  // 제품 카드에 마우스를 올리거나 탭하면, 그 제품이 실제로 차지하는 라인들만
  // 메인 2D 맵에서 은은하게 강조한다. 메인 맵은 라인(X축)까지만 책임지고,
  // 정확한 단(Y축) 점유 모양은 카드 안의 미니 랙이 보여준다.
  d.querySelectorAll('[data-occupied-lines]').forEach(card=>{
    const lineCodes=(card.dataset.occupiedLines||'').split(',').filter(Boolean);
    if(!lineCodes.length) return;
    card.addEventListener('mouseenter', ()=>highlightLines(lineCodes, true));
    card.addEventListener('mouseleave', ()=>{ if(!card.classList.contains('card-pinned')) highlightLines(lineCodes, false); });
    card.addEventListener('click', (ev)=>{
      if(ev.target.closest('button')) return;
      const wasPinned=card.classList.contains('card-pinned');
      d.querySelectorAll('.card-pinned').forEach(other=>{
        if(other!==card){ other.classList.remove('card-pinned'); highlightLines((other.dataset.occupiedLines||'').split(',').filter(Boolean), false); }
      });
      card.classList.toggle('card-pinned', !wasPinned);
      highlightLines(lineCodes, !wasPinned);
    });
  });
  d.querySelectorAll('[data-product]').forEach(btn=>btn.addEventListener('click',(ev)=>{
    ev.stopPropagation();
    const card=btn.closest('.detail-card');
    const old=card.nextElementSibling;
    if(old && old.classList.contains('product-inline-detail')){
      // 같은 버튼을 다시 누르면 접는다(예전엔 여기서 버튼을 disabled로 만들어
      // 다시 눌러도 이 분기에 아예 도달하지 못했다).
      old.remove();
      btn.textContent='제품 상세 보기';
      return;
    }
    d.querySelectorAll('.product-inline-detail').forEach(x=>x.remove());
    d.querySelectorAll('[data-product]').forEach(x=>x.textContent='제품 상세 보기');
    card.insertAdjacentHTML('afterend', `<div class="product-inline-detail">${productDetail(btn.dataset.product)}</div>`);
    btn.textContent='접기';
    const box=card.nextElementSibling;
    box.querySelectorAll('[data-jump-loc]').forEach(j=>j.addEventListener('click',()=>showDetail(j.dataset.jumpLoc)));
    box.querySelectorAll('[data-search-product]').forEach(t=>t.addEventListener('click',(ev)=>{
      ev.preventDefault();
      ev.stopPropagation();
      const productName = t.dataset.searchProduct || '';
      if(!productName) return;
      if(tryParentSearch(productName)) return;
      const href = buildParentUrl('map_search_product', productName, 'inbound_loc');
      const form = t.closest('form');
      if(form) form.action = href;
      navigateTop(href);
    }));
    setFormsToParent();
  }));
  d.querySelectorAll('[data-move-id]').forEach(btn=>btn.addEventListener('click',(ev)=>{
    ev.preventDefault();
    ev.stopPropagation();
    const invId = btn.dataset.moveId || '';
    if(!invId) return;
    // 이 iframe은 sandbox에 allow-top-navigation이 없어 window.top.location.assign은
    // 브라우저가 조용히 막는다(버튼을 눌러도 아무 반응이 없는 것처럼 보임). 그래서
    // 최상위 페이지 이동 대신, 부모 문서(같은 출처라 DOM 접근은 허용됨)에 숨겨 그려둔
    // 입력칸에 재고 id만 적어 넣어 그 on_change가 실제 화면 전환을 하게 한다.
    try {
      const doc = window.parent.document;
      const input = Array.from(doc.querySelectorAll('input')).find(x => (x.getAttribute('aria-label')||'')==='__map_move_inv_id_bridge');
      if(input){
        input.focus();
        const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        setter.call(input, invId);
        input.dispatchEvent(new InputEvent('input', {bubbles:true, inputType:'insertText', data:invId}));
        input.dispatchEvent(new Event('change', {bubbles:true}));
        input.blur();
        return;
      }
    } catch(e) {}
    navigateTop(buildParentUrlMulti({move_inv_id: invId}, ['map_search_product', 'inbound_loc']));
  }));
}
function toggleSpecialMenu(forceClose=false){
  const menu=document.getElementById('specialMenu');
  if(!menu) return;
  if(forceClose){menu.classList.remove('open'); return;}
  menu.classList.toggle('open');
}
document.querySelectorAll('[data-special-loc]').forEach(btn=>btn.addEventListener('click',(ev)=>{
  ev.preventDefault(); ev.stopPropagation();
  const loc=btn.dataset.specialLoc || '';
  toggleSpecialMenu(true);
  document.querySelectorAll('[data-special-loc]').forEach(x=>x.classList.toggle('selected', x.dataset.specialLoc===loc));
  showDetail(loc);
}));
document.querySelectorAll('[data-loc]').forEach(btn=>btn.addEventListener('click',(ev)=>{
  const loc=btn.dataset.loc || '';
  if(loc==='N'){
    ev.preventDefault(); ev.stopPropagation();
    toggleSpecialMenu(false);
    return;
  }
  toggleSpecialMenu(true);
  showDetail(loc);
}));
if(initialSelectedLocation){setTimeout(()=>showDetail(initialSelectedLocation), 80);}