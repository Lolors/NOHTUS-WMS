from __future__ import annotations

import base64
import json

import streamlit as st
import streamlit.components.v1 as components

from nohtus.auth import is_admin
from nohtus.services.location_map_layout import load_location_map_layout, save_location_map_layout
from nohtus.services.location_map_layout_seed import initial_layout


def _consume_save_payload() -> bool:
    raw = st.query_params.get("layout_save", "")
    if isinstance(raw, list):
        raw = raw[0] if raw else ""
    raw = str(raw or "").strip()
    if not raw:
        return False
    try:
        padded = raw + "=" * (-len(raw) % 4)
        data = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
        save_location_map_layout(json.loads(data))
        del st.query_params["layout_save"]
        st.success("로케이션맵 배치를 저장했습니다.")
        return True
    except Exception as exc:
        st.error(f"배치 저장에 실패했습니다: {exc}")
        return False


def page_location_map_editor():
    if not is_admin():
        st.warning("admin 계정만 로케이션맵 편집에 접근할 수 있습니다.")
        return
    st.title("🧭 로케이션맵 편집")
    st.caption("로케이션을 마우스로 끌어 이동한 뒤 배치 저장을 누르세요. 저장된 좌표는 실제 로케이션맵에 그대로 적용됩니다.")
    _consume_save_payload()
    layout = load_location_map_layout()
    if not layout.get("items"):
        layout = initial_layout()
    payload = json.dumps(layout, ensure_ascii=False)

    html = f'''<style>
    *{{box-sizing:border-box}} body{{margin:0;font-family:Inter,Segoe UI,Arial,'Noto Sans KR',sans-serif;background:#f8fafc;color:#0f172a}}
    button,input,select{{font:inherit}} .toolbar{{display:flex;align-items:center;gap:8px;margin-bottom:10px;flex-wrap:wrap}}
    button{{border:1px solid #cbd5e1;background:white;border-radius:9px;padding:8px 11px;font-weight:800;cursor:pointer}}
    button.primary{{background:#2563eb;color:white;border-color:#2563eb}} button.danger{{color:#b91c1c;border-color:#fecaca;background:#fff7f7}}
    .status{{font-size:13px;color:#64748b;margin-left:auto}} .editor-shell{{display:grid;grid-template-columns:minmax(0,1fr) 286px;gap:12px}}
    .viewport{{width:100%;height:720px;overflow:auto;border:1px solid #dbe4f0;border-radius:16px;background:white;padding:12px}}
    .stage{{position:relative;background-color:#fff;background-image:linear-gradient(#edf2f7 1px,transparent 1px),linear-gradient(90deg,#edf2f7 1px,transparent 1px);background-size:10px 10px;border:1px solid #cbd5e1}}
    .loc{{position:absolute;display:flex;align-items:center;justify-content:center;text-align:center;border:1.5px solid #334155;border-radius:12px;font-weight:900;font-size:15px;cursor:grab;user-select:none;box-shadow:0 3px 8px rgba(15,23,42,.08);transform-origin:center}}
    .loc.selected{{outline:4px solid rgba(34,197,94,.28);border-color:#16a34a;z-index:30}} .palette-farm{{background:#fff39b}} .palette-notus{{background:#87d9ee}} .palette-noh{{background:#efb0e5}} .palette-bidata{{background:#9bd8d8}} .palette-special{{background:#fff}} .palette-other{{background:#f1f5f9}}
    .coords{{position:absolute;left:6px;bottom:3px;font-size:9px;color:#64748b;font-weight:500}} .resize-handle{{display:none;position:absolute;width:11px;height:11px;background:#fff;border:2px solid #16a34a;border-radius:3px;z-index:3}}
    .selected .resize-handle{{display:block}} .resize-nw{{left:-7px;top:-7px;cursor:nwse-resize}} .resize-n{{left:calc(50% - 5px);top:-7px;cursor:ns-resize}} .resize-ne{{right:-7px;top:-7px;cursor:nesw-resize}} .resize-e{{right:-7px;top:calc(50% - 5px);cursor:ew-resize}} .resize-se{{right:-7px;bottom:-7px;cursor:nwse-resize}} .resize-s{{left:calc(50% - 5px);bottom:-7px;cursor:ns-resize}} .resize-sw{{left:-7px;bottom:-7px;cursor:nesw-resize}} .resize-w{{left:-7px;top:calc(50% - 5px);cursor:ew-resize}}
    .rotate-line{{display:none;position:absolute;left:calc(50% - 1px);top:-31px;width:2px;height:24px;background:#16a34a}} .rotate-handle{{display:none;position:absolute;left:calc(50% - 7px);top:-44px;width:15px;height:15px;border-radius:50%;background:#16a34a;border:2px solid white;box-shadow:0 0 0 1px #16a34a;cursor:grab}} .selected .rotate-line,.selected .rotate-handle{{display:block}}
    .panel{{height:720px;overflow:auto;border:1px solid #dbe4f0;border-radius:16px;background:white;padding:14px}} .panel h3{{font-size:15px;margin:0 0 10px}} .panel h3:not(:first-child){{margin-top:18px;padding-top:15px;border-top:1px solid #e2e8f0}}
    .field{{display:grid;gap:4px;margin-bottom:9px}} .field label{{font-size:11px;font-weight:800;color:#64748b}} .field input,.field select{{width:100%;border:1px solid #cbd5e1;border-radius:7px;padding:7px 8px;background:#fff}} .field-row{{display:grid;grid-template-columns:1fr 1fr;gap:8px}} .panel-actions{{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin-top:11px}} .hint{{font-size:11px;color:#64748b;line-height:1.45;margin:6px 0}} .empty-selection{{padding:12px;border-radius:9px;background:#f8fafc;color:#64748b;font-size:12px}}
    @media(max-width:900px){{.editor-shell{{grid-template-columns:1fr}} .panel{{height:auto}}}}
    </style>
    <div class="toolbar">
      <button type="button" id="zoomOut">−</button><button type="button" id="zoomIn">＋</button><button type="button" id="fit">전체보기</button>
      <button type="button" class="primary" id="save">배치 저장</button><span class="status" id="status">박스를 선택해 이동·변형하세요</span>
    </div>
    <div class="editor-shell">
      <div class="viewport" id="viewport"><div class="stage" id="stage"></div></div>
      <aside class="panel">
        <h3>선택한 로케이션</h3>
        <div id="emptySelection" class="empty-selection">지도에서 박스를 선택하세요.</div>
        <div id="selectedFields" hidden>
          <div class="field"><label for="propCode">로케이션 코드</label><input id="propCode"></div>
          <div class="field"><label for="propLabel">표시 이름</label><input id="propLabel"></div>
          <div class="field-row"><div class="field"><label for="propX">X</label><input id="propX" type="number"></div><div class="field"><label for="propY">Y</label><input id="propY" type="number"></div></div>
          <div class="field-row"><div class="field"><label for="propWidth">너비</label><input id="propWidth" type="number" min="36"></div><div class="field"><label for="propHeight">높이</label><input id="propHeight" type="number" min="30"></div></div>
          <div class="field"><label for="propRotation">회전각</label><input id="propRotation" type="number" step="5"></div>
          <div class="field"><label for="propCompany">색상/사업장</label><select id="propCompany"><option>노투스팜</option><option>노투스</option><option>NOH</option><option>비자료</option><option>특수</option><option>기타</option></select></div>
          <div class="field"><label for="propKind">종류</label><select id="propKind"><option value="location">일반 로케이션</option><option value="zone">구역</option></select></div>
          <div class="panel-actions"><button type="button" class="primary" id="applyProperties">속성 적용</button><button type="button" class="danger" id="deleteSelected">삭제</button></div>
          <p class="hint">코드를 변경하면 실제 재고가 연결되는 로케이션 코드도 바뀝니다.</p>
        </div>
        <h3>새 로케이션/구역</h3>
        <div class="field"><label for="newCode">새 코드</label><input id="newCode" placeholder="예: A3-01 또는 통로-A"></div>
        <div class="field"><label for="newLabel">표시 이름</label><input id="newLabel" placeholder="비우면 코드와 동일"></div>
        <div class="field-row"><div class="field"><label for="newWidth">너비</label><input id="newWidth" type="number" value="80" min="36"></div><div class="field"><label for="newHeight">높이</label><input id="newHeight" type="number" value="56" min="30"></div></div>
        <div class="field"><label for="newCompany">색상/사업장</label><select id="newCompany"><option>노투스팜</option><option>노투스</option><option>NOH</option><option>비자료</option><option>특수</option><option selected>기타</option></select></div>
        <div class="field"><label for="newKind">종류</label><select id="newKind"><option value="location">일반 로케이션</option><option value="zone">구역</option></select></div>
        <button type="button" class="primary" id="addItem" style="width:100%">새 항목 추가</button>
      </aside>
    </div>
    <script>
    const layout={payload}; const stage=document.getElementById('stage'); const viewport=document.getElementById('viewport'); const status=document.getElementById('status');
    const grid=Number(layout.canvas.grid||10); const minWidth=36,minHeight=30; let scale=.82,action=null,selectedIndex=null;
    const fieldIds=['propCode','propLabel','propX','propY','propWidth','propHeight','propRotation','propCompany','propKind'];
    const fields=Object.fromEntries(fieldIds.map(id=>[id,document.getElementById(id)])); const snap=v=>Math.round(v/grid)*grid; const clamp=(v,min,max)=>Math.max(min,Math.min(max,v));
    function palette(company){{return {{'노투스팜':'palette-farm','노투스':'palette-notus','NOH':'palette-noh','비자료':'palette-bidata','특수':'palette-special'}}[company]||'palette-other';}}
    function handles(){{return ['nw','n','ne','e','se','s','sw','w'].map(dir=>`<i class="resize-handle resize-${{dir}}" data-dir="${{dir}}"></i>`).join('')+'<i class="rotate-line"></i><i class="rotate-handle"></i>';}}
    function draw(){{stage.innerHTML='';stage.style.width=layout.canvas.width+'px';stage.style.height=layout.canvas.height+'px';stage.style.transform=`scale(${{scale}})`;stage.style.transformOrigin='top left';layout.items.forEach((it,idx)=>{{
      const el=document.createElement('div');el.className=`loc ${{palette(it.company)}}${{idx===selectedIndex?' selected':''}}`;el.dataset.idx=idx;el.style.left=it.x+'px';el.style.top=it.y+'px';el.style.width=it.width+'px';el.style.height=it.height+'px';el.style.transform=`rotate(${{Number(it.rotation||0)}}deg)`;
      const label=document.createElement('span');label.textContent=it.label||it.code;const coords=document.createElement('small');coords.className='coords';coords.textContent=`${{it.x}}, ${{it.y}}`;el.append(label,coords);el.insertAdjacentHTML('beforeend',handles());stage.appendChild(el);
    }});syncPanel();}}
    function syncPanel(){{const selected=selectedIndex!==null&&layout.items[selectedIndex];document.getElementById('emptySelection').hidden=!!selected;document.getElementById('selectedFields').hidden=!selected;if(!selected)return;fields.propCode.value=selected.code||'';fields.propLabel.value=selected.label||selected.code||'';fields.propX.value=selected.x;fields.propY.value=selected.y;fields.propWidth.value=selected.width;fields.propHeight.value=selected.height;fields.propRotation.value=Number(selected.rotation||0);fields.propCompany.value=selected.company||'기타';fields.propKind.value=selected.kind||'location';}}
    function selectItem(idx){{selectedIndex=idx;draw();status.textContent=`${{layout.items[idx].code}} 선택됨`;}}
    function isDuplicateCode(code,exceptIndex=null){{const key=code.trim().toLocaleUpperCase();return layout.items.some((it,idx)=>idx!==exceptIndex&&String(it.code||'').trim().toLocaleUpperCase()===key);}}
    function updateElement(el,it){{el.style.left=it.x+'px';el.style.top=it.y+'px';el.style.width=it.width+'px';el.style.height=it.height+'px';el.style.transform=`rotate(${{Number(it.rotation||0)}}deg)`;el.querySelector('.coords').textContent=`${{it.x}}, ${{it.y}}`;syncPanel();}}
    stage.addEventListener('pointerdown',e=>{{const el=e.target.closest('.loc');if(!el)return;e.preventDefault();const idx=Number(el.dataset.idx);if(selectedIndex!==idx){{selectedIndex=idx;stage.querySelectorAll('.loc.selected').forEach(node=>node.classList.remove('selected'));el.classList.add('selected');syncPanel();status.textContent=`${{layout.items[idx].code}} 선택됨`;}}const it=layout.items[idx];const handle=e.target.closest('.resize-handle');const rotate=e.target.closest('.rotate-handle');const rect=el.getBoundingClientRect();action={{mode:rotate?'rotate':handle?'resize':'move',dir:handle?.dataset.dir||'',el,idx,sx:e.clientX,sy:e.clientY,x:it.x,y:it.y,width:it.width,height:it.height,rotation:Number(it.rotation||0),cx:rect.left+rect.width/2,cy:rect.top+rect.height/2}};el.setPointerCapture(e.pointerId);}});
    stage.addEventListener('pointermove',e=>{{if(!action)return;const it=layout.items[action.idx];const dx=(e.clientX-action.sx)/scale,dy=(e.clientY-action.sy)/scale;if(action.mode==='move'){{it.x=clamp(snap(action.x+dx),0,layout.canvas.width-it.width);it.y=clamp(snap(action.y+dy),0,layout.canvas.height-it.height);}}
      else if(action.mode==='rotate'){{const start=Math.atan2(action.sy-action.cy,action.sx-action.cx);const now=Math.atan2(e.clientY-action.cy,e.clientX-action.cx);it.rotation=Math.round((action.rotation+(now-start)*180/Math.PI)/5)*5;}}
      else{{let x=action.x,y=action.y,w=action.width,h=action.height;const dir=action.dir;if(dir.includes('e'))w=snap(action.width+dx);if(dir.includes('s'))h=snap(action.height+dy);if(dir.includes('w')){{x=snap(action.x+dx);w=action.width-(x-action.x);}}if(dir.includes('n')){{y=snap(action.y+dy);h=action.height-(y-action.y);}}if(w<minWidth){{if(dir.includes('w'))x=action.x+action.width-minWidth;w=minWidth;}}if(h<minHeight){{if(dir.includes('n'))y=action.y+action.height-minHeight;h=minHeight;}}x=clamp(x,0,layout.canvas.width-minWidth);y=clamp(y,0,layout.canvas.height-minHeight);w=Math.min(w,layout.canvas.width-x);h=Math.min(h,layout.canvas.height-y);Object.assign(it,{{x,y,width:w,height:h}});}}
      updateElement(action.el,it);status.textContent=`${{it.code}} · ${{it.width}}×${{it.height}} · ${{it.rotation||0}}°`;}});
    function endAction(){{action=null}} stage.addEventListener('pointerup',endAction);stage.addEventListener('pointercancel',endAction);
    document.getElementById('applyProperties').addEventListener('click',()=>{{if(selectedIndex===null)return;const it=layout.items[selectedIndex];const code=fields.propCode.value.trim();if(!code){{status.textContent='로케이션 코드를 입력하세요.';return}}if(isDuplicateCode(code,selectedIndex)){{status.textContent='이미 존재하는 로케이션 코드입니다.';return}}Object.assign(it,{{code,label:fields.propLabel.value.trim()||code,x:clamp(snap(Number(fields.propX.value)||0),0,layout.canvas.width-minWidth),y:clamp(snap(Number(fields.propY.value)||0),0,layout.canvas.height-minHeight),width:Math.max(minWidth,snap(Number(fields.propWidth.value)||minWidth)),height:Math.max(minHeight,snap(Number(fields.propHeight.value)||minHeight)),rotation:Number(fields.propRotation.value)||0,company:fields.propCompany.value,kind:fields.propKind.value}});it.width=Math.min(it.width,layout.canvas.width-it.x);it.height=Math.min(it.height,layout.canvas.height-it.y);draw();status.textContent=`${{code}} 속성을 적용했습니다.`;}});
    document.getElementById('deleteSelected').addEventListener('click',()=>{{if(selectedIndex===null)return;const code=layout.items[selectedIndex].code;if(!confirm(`${{code}} 항목을 삭제할까요?`))return;layout.items.splice(selectedIndex,1);selectedIndex=null;draw();status.textContent=`${{code}} 삭제됨`;}});
    document.getElementById('addItem').addEventListener('click',()=>{{const code=document.getElementById('newCode').value.trim();if(!code){{status.textContent='새 로케이션 코드를 입력하세요.';return}}if(isDuplicateCode(code)){{status.textContent='이미 존재하는 로케이션 코드입니다.';return}}const width=Math.max(minWidth,snap(Number(document.getElementById('newWidth').value)||80));const height=Math.max(minHeight,snap(Number(document.getElementById('newHeight').value)||60));let x=grid,y=grid;for(let i=0;i<layout.items.length;i++){{const occupied=layout.items.some(it=>Math.abs(it.x-x)<grid&&Math.abs(it.y-y)<grid);if(!occupied)break;x+=grid;if(x+width>layout.canvas.width){{x=grid;y+=grid}}}}layout.items.push({{code,label:document.getElementById('newLabel').value.trim()||code,x,y,width:Math.min(width,layout.canvas.width-x),height:Math.min(height,layout.canvas.height-y),rotation:0,company:document.getElementById('newCompany').value,kind:document.getElementById('newKind').value,note:''}});selectedIndex=layout.items.length-1;document.getElementById('newCode').value='';document.getElementById('newLabel').value='';draw();status.textContent=`${{code}} 추가됨`;}});
    function setScale(v){{scale=Math.max(.35,Math.min(1.5,v));draw();status.textContent='확대 '+Math.round(scale*100)+'%';}}document.getElementById('zoomIn').addEventListener('click',()=>setScale(scale+.1));document.getElementById('zoomOut').addEventListener('click',()=>setScale(scale-.1));document.getElementById('fit').addEventListener('click',()=>{{const s=Math.min((viewport.clientWidth-30)/layout.canvas.width,(viewport.clientHeight-30)/layout.canvas.height);setScale(s);}});
    document.getElementById('save').addEventListener('click',()=>{{const txt=JSON.stringify(layout);const bytes=new TextEncoder().encode(txt);let binary='';bytes.forEach(b=>binary+=String.fromCharCode(b));const enc=btoa(binary).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');const u=new URL(window.parent.location.href);u.searchParams.set('layout_save',enc);window.parent.location.href=u.toString();}});
    draw();
    </script>'''
    components.html(html, height=790, scrolling=False)
