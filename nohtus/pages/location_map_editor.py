from __future__ import annotations

import base64
import json

import streamlit as st
import streamlit.components.v1 as components

from nohtus.auth import is_admin
from nohtus.services.location_map_layout import (
    delete_location_map_draft,
    load_location_map_draft,
    load_location_map_layout,
    save_location_map_draft,
    save_location_map_layout,
)
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



def _consume_draft_payload() -> bool:
    raw = st.query_params.get("layout_draft_save", "")
    if isinstance(raw, list):
        raw = raw[0] if raw else ""
    raw = str(raw or "").strip()
    if raw:
        try:
            padded = raw + "=" * (-len(raw) % 4)
            data = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
            save_location_map_draft(json.loads(data))
            del st.query_params["layout_draft_save"]
            st.success("편집 내용을 임시저장했습니다. 실제 로케이션맵에는 아직 반영되지 않았습니다.")
            return True
        except Exception as exc:
            st.error(f"임시저장에 실패했습니다: {exc}")
            return False

    delete_requested = st.query_params.get("layout_draft_delete", "")
    if isinstance(delete_requested, list):
        delete_requested = delete_requested[0] if delete_requested else ""
    if str(delete_requested or "").strip():
        delete_location_map_draft()
        del st.query_params["layout_draft_delete"]
        st.success("임시저장 내용을 삭제했습니다.")
        return True
    return False


def page_location_map_editor():
    if not is_admin():
        st.warning("admin 계정만 로케이션맵 편집에 접근할 수 있습니다.")
        return
    st.title("🧭 로케이션맵 편집")
    st.caption("로케이션을 마우스로 끌어 이동한 뒤 배치 저장을 누르세요. 저장된 좌표는 실제 로케이션맵에 그대로 적용됩니다.")
    _consume_save_payload()
    _consume_draft_payload()
    layout = load_location_map_layout()
    if not layout.get("items"):
        layout = initial_layout()
    layout.setdefault("canvas", {})["width"] = max(2000, int(layout.get("canvas", {}).get("width") or 0))
    payload = json.dumps(layout, ensure_ascii=False)
    draft_payload = json.dumps(load_location_map_draft(), ensure_ascii=False)

    html = f'''<style>
    *{{box-sizing:border-box}} body{{margin:0;font-family:Inter,Segoe UI,Arial,'Noto Sans KR',sans-serif;background:#f8fafc;color:#0f172a}}
    button,input,select{{font:inherit}} .toolbar{{display:flex;align-items:center;gap:8px;margin-bottom:10px;flex-wrap:wrap}}
    button{{border:1px solid #cbd5e1;background:white;border-radius:9px;padding:8px 11px;font-weight:800;cursor:pointer}}
    button.primary{{background:#2563eb;color:white;border-color:#2563eb}} button.danger{{color:#b91c1c;border-color:#fecaca;background:#fff7f7}}
    .status{{font-size:13px;color:#64748b;margin-left:auto}} .guide{{position:absolute;z-index:80;pointer-events:none;background:#e11d48}} .guide-x{{width:1px;top:0;bottom:0}} .guide-y{{height:1px;left:0;right:0}} .gap-guide{{position:absolute;z-index:81;pointer-events:none;color:#e11d48;font-size:10px;font-weight:900;border-color:#e11d48;border-style:dashed}} .gap-guide.x{{height:12px;border-top-width:1px}} .gap-guide.y{{width:12px;border-left-width:1px}} .editor-shell{{display:grid;grid-template-columns:minmax(0,1fr) 286px;gap:12px}}
    .viewport{{width:100%;height:720px;overflow:auto;border:1px solid #dbe4f0;border-radius:16px;background:white;padding:12px}}
    .stage{{position:relative;background-color:#fff;background-image:linear-gradient(#edf2f7 1px,transparent 1px),linear-gradient(90deg,#edf2f7 1px,transparent 1px);background-size:10px 10px;border:1px solid #cbd5e1}}
    .loc{{position:absolute;display:flex;align-items:center;justify-content:center;text-align:center;border:1.5px solid #334155;border-radius:12px;font-weight:900;font-size:15px;cursor:grab;user-select:none;box-shadow:0 3px 8px rgba(15,23,42,.08);transform-origin:center}}
    .loc.selected{{outline:4px solid rgba(34,197,94,.28);border-color:#16a34a;z-index:30}} .loc.map-shape{{background:transparent!important;color:transparent;border:4px solid #475569;box-shadow:none}} .loc.shape-rounded_rect{{border-radius:18px}} .loc.shape-circle{{border-radius:50%}} .loc.shape-line{{border-color:transparent;background:linear-gradient(to bottom,transparent calc(50% - 2px),var(--shape-stroke,#334155) calc(50% - 2px),var(--shape-stroke,#334155) calc(50% + 2px),transparent calc(50% + 2px))!important}} .selection-box{{position:absolute;z-index:90;border:1.5px solid #2563eb;background:rgba(37,99,235,.12);pointer-events:none}} .palette-farm{{background:#fff39b}} .palette-notus{{background:#87d9ee}} .palette-noh{{background:#efb0e5}} .palette-bidata{{background:#9bd8d8}} .palette-special{{background:#fff}} .palette-other{{background:#f1f5f9}}
    .coords{{position:absolute;left:6px;bottom:3px;font-size:9px;color:#64748b;font-weight:500}} .resize-handle{{display:none;position:absolute;width:11px;height:11px;background:#fff;border:2px solid #16a34a;border-radius:3px;z-index:3}}
    .selected .resize-handle{{display:block}} .resize-nw{{left:-7px;top:-7px;cursor:nwse-resize}} .resize-n{{left:calc(50% - 5px);top:-7px;cursor:ns-resize}} .resize-ne{{right:-7px;top:-7px;cursor:nesw-resize}} .resize-e{{right:-7px;top:calc(50% - 5px);cursor:ew-resize}} .resize-se{{right:-7px;bottom:-7px;cursor:nwse-resize}} .resize-s{{left:calc(50% - 5px);bottom:-7px;cursor:ns-resize}} .resize-sw{{left:-7px;bottom:-7px;cursor:nesw-resize}} .resize-w{{left:-7px;top:calc(50% - 5px);cursor:ew-resize}}
    .rotate-line{{display:none;position:absolute;left:calc(50% - 1px);top:-31px;width:2px;height:24px;background:#16a34a}} .rotate-handle{{display:none;position:absolute;left:calc(50% - 7px);top:-44px;width:15px;height:15px;border-radius:50%;background:#16a34a;border:2px solid white;box-shadow:0 0 0 1px #16a34a;cursor:grab}} .selected .rotate-line,.selected .rotate-handle{{display:block}}
    .panel{{height:720px;overflow:auto;border:1px solid #dbe4f0;border-radius:16px;background:white;padding:14px}} .panel h3{{font-size:15px;margin:0 0 10px}} .panel h3:not(:first-child){{margin-top:18px;padding-top:15px;border-top:1px solid #e2e8f0}}
    .tabs{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:5px;margin-bottom:14px;padding:4px;background:#f1f5f9;border-radius:10px}} .tab-button{{border:0;background:transparent;color:#64748b;padding:8px 5px}} .tab-button.active{{background:white;color:#0f172a;box-shadow:0 1px 4px rgba(15,23,42,.12)}} .tab-panel[hidden]{{display:none}} .field{{display:grid;gap:4px;margin-bottom:9px}} .field label{{font-size:11px;font-weight:800;color:#64748b}} .field input,.field select{{width:100%;border:1px solid #cbd5e1;border-radius:7px;padding:7px 8px;background:#fff}} .field-row{{display:grid;grid-template-columns:1fr 1fr;gap:8px}} .panel-actions{{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin-top:11px}} .hint{{font-size:11px;color:#64748b;line-height:1.45;margin:6px 0}} .empty-selection{{padding:12px;border-radius:9px;background:#f8fafc;color:#64748b;font-size:12px}}
    @media(max-width:900px){{.editor-shell{{grid-template-columns:1fr}} .panel{{height:auto}}}}
    </style>
    <div class="toolbar">
      <button type="button" id="zoomOut">−</button><button type="button" id="zoomIn">＋</button><button type="button" id="fit">전체보기</button><button type="button" id="undo">↶ 되돌리기</button><button type="button" id="redo">↷ 다시 실행</button><button type="button" id="selectAll">도형 전체 선택</button><button type="button" id="clearSelection">선택 해제</button>
      <button type="button" id="saveDraft">임시저장</button><button type="button" id="loadDraft">임시저장 불러오기</button><button type="button" class="danger" id="deleteDraft">임시저장 삭제</button><button type="button" class="primary" id="save">배치 저장</button><span class="status" id="status">박스를 선택해 이동·변형하세요</span>
    </div>
    <div class="editor-shell">
      <div class="viewport" id="viewport"><div class="stage" id="stage"></div></div>
      <aside class="panel">
        <div class="tabs"><button type="button" class="tab-button active" data-tab="changeTab">선택 변경</button><button type="button" class="tab-button" data-tab="newTab">로케이션 추가</button><button type="button" class="tab-button" data-tab="shapeTab">도형 추가</button></div>
        <section id="changeTab" class="tab-panel">
          <h3>선택한 로케이션</h3>
          <div id="emptySelection" class="empty-selection">지도에서 박스를 선택하세요. Ctrl/Shift 클릭으로 여러 개를 선택할 수 있습니다.</div>
          <div id="selectedFields" hidden>
            <div class="field location-only"><label for="propCode">로케이션 코드</label><input id="propCode"></div>
            <div class="field location-only"><label for="propLabel">표시 이름</label><input id="propLabel"></div>
            <div class="field location-only"><label for="propCompany">색상/사업장</label><select id="propCompany"><option>노투스팜</option><option>노투스</option><option>NOH</option><option>비자료</option><option>특수</option><option>기타</option></select></div>
            <div class="field location-only"><label for="propKind">종류</label><select id="propKind"><option value="location">일반 로케이션</option><option value="zone">구역</option></select></div>
            <p class="hint location-only">일반 로케이션은 개별 보관 위치, 구역은 여러 위치를 대표하는 큰 영역용 분류입니다. 현재 저장·지도 클릭 동작은 동일합니다.</p><p class="hint shape-only" hidden>지도 장식 도형입니다. 마우스로 이동·크기 조절·회전할 수 있으며 재고 위치로는 사용되지 않습니다.</p>
            <div class="panel-actions"><button type="button" class="primary location-only" id="applyProperties">속성 적용</button><button type="button" id="duplicateSelected">묶음 복제</button></div>
            <div class="panel-actions"><button type="button" class="danger" id="deleteSelected">삭제</button></div>
            <h3 class="location-only">균등 분할</h3>
            <div class="field-row location-only"><div class="field"><label for="splitCount">분할 개수</label><input id="splitCount" type="number" value="2" min="2" max="100"></div><div class="field"><label for="splitAxis">분할 방향</label><select id="splitAxis"><option value="x">가로</option><option value="y">세로</option></select></div></div>
            <div class="field-row location-only"><div class="field"><label for="splitGap">칸 간격</label><input id="splitGap" type="number" value="0" min="0"></div><div class="field"><label for="splitPrefix">코드 접두어</label><input id="splitPrefix" placeholder="예: A3"></div></div>
            <button type="button" class="primary location-only" id="splitSelected" style="width:100%">선택 도형 균등 분할</button>
            <p class="hint">분할된 칸은 하나의 묶음으로 저장됩니다. 묶음 복제를 누르면 분할 모습과 간격이 그대로 복제됩니다.</p>
          </div>
        </section>
        <section id="newTab" class="tab-panel" hidden>
          <h3>새 로케이션/구역</h3>
          <div class="field"><label for="newCode">새 코드</label><input id="newCode" placeholder="예: A3-01 또는 통로-A"></div>
          <div class="field"><label for="newLabel">표시 이름</label><input id="newLabel" placeholder="비우면 코드와 동일"></div>
          <div class="field-row"><div class="field"><label for="newWidth">너비</label><input id="newWidth" type="number" value="80" min="36"></div><div class="field"><label for="newHeight">높이</label><input id="newHeight" type="number" value="56" min="30"></div></div>
          <div class="field"><label for="newCompany">색상/사업장</label><select id="newCompany"><option>노투스팜</option><option>노투스</option><option>NOH</option><option>비자료</option><option>특수</option><option selected>기타</option></select></div>
          <div class="field"><label for="newKind">종류</label><select id="newKind"><option value="location">일반 로케이션</option><option value="zone">구역</option></select></div>
          <p class="hint">일반 로케이션은 개별 위치, 구역은 큰 영역을 구분할 때 사용합니다.</p>
          <button type="button" class="primary" id="addItem" style="width:100%">새 항목 추가</button>
        </section>
        <section id="shapeTab" class="tab-panel" hidden>
          <h3>지도 도형 추가</h3>
          <p class="hint">재고와 연결되지 않는 안내 도형입니다. 추가한 뒤 마우스로 길이·크기·회전각을 자유롭게 조절할 수 있습니다.</p>
          <div class="field"><label for="shapeStroke">선 색상</label><input id="shapeStroke" type="color" value="#475569"></div>
          <div class="panel-actions"><button type="button" data-add-shape="rounded_rect">둥근 사각형</button><button type="button" data-add-shape="circle">원</button></div>
          <button type="button" class="primary" data-add-shape="line" style="width:100%;margin-top:8px">직선 / 벽 추가</button>
        </section>
      </aside>
    </div>
    <script>
    const layout={payload}; const serverDraft={draft_payload},draftKey='nohtus-location-map-editor-draft-v2';let draftLayout=null;try{{draftLayout=JSON.parse(localStorage.getItem(draftKey)||'null')||serverDraft}}catch(e){{draftLayout=serverDraft}} const stage=document.getElementById('stage'); const viewport=document.getElementById('viewport'); const status=document.getElementById('status');
    const grid=Number(layout.canvas.grid||10); const minWidth=36,minHeight=30; let scale=.82,action=null,selectedIndex=null; const selectedIndices=new Set(),undoStack=[],redoStack=[]; const guideTolerance=Math.max(4,grid/2);
    const fieldIds=['propCode','propLabel','propCompany','propKind'];
    const fields=Object.fromEntries(fieldIds.map(id=>[id,document.getElementById(id)])); const snap=v=>Math.round(v/grid)*grid; const clamp=(v,min,max)=>Math.max(min,Math.min(max,v));
    const snapshot=()=>JSON.stringify(layout);function updateHistoryButtons(){{document.getElementById('undo').disabled=!undoStack.length;document.getElementById('redo').disabled=!redoStack.length;}}function checkpoint(){{undoStack.push(snapshot());if(undoStack.length>100)undoStack.shift();redoStack.length=0;updateHistoryButtons();}}function restore(raw){{const saved=JSON.parse(raw);layout.version=saved.version;layout.canvas=saved.canvas;layout.canvas.width=Math.max(2000,Number(layout.canvas.width||0));layout.items=saved.items;selectedIndices.clear();selectedIndex=null;clearGuides();draw();}}function undo(){{if(!undoStack.length)return;redoStack.push(snapshot());restore(undoStack.pop());updateHistoryButtons();status.textContent='이전 작업으로 되돌렸습니다.';}}function redo(){{if(!redoStack.length)return;undoStack.push(snapshot());restore(redoStack.pop());updateHistoryButtons();status.textContent='작업을 다시 실행했습니다.';}}
    function palette(company){{return {{'노투스팜':'palette-farm','노투스':'palette-notus','NOH':'palette-noh','비자료':'palette-bidata','특수':'palette-special'}}[company]||'palette-other';}}
    function handles(){{return ['nw','n','ne','e','se','s','sw','w'].map(dir=>`<i class="resize-handle resize-${{dir}}" data-dir="${{dir}}"></i>`).join('')+'<i class="rotate-line"></i><i class="rotate-handle"></i>';}}
    function clearGuides(){{stage.querySelectorAll('.guide,.gap-guide').forEach(el=>el.remove());}}
    function addGuide(axis,pos){{const el=document.createElement('i');el.className=`guide guide-${{axis}}`;if(axis==='x')el.style.left=pos+'px';else el.style.top=pos+'px';stage.appendChild(el);}}
    function addGapGuide(axis,start,end,cross,gap){{const el=document.createElement('i');el.className=`gap-guide ${{axis}}`;if(axis==='x'){{el.style.left=start+'px';el.style.top=cross+'px';el.style.width=Math.max(0,end-start)+'px';}}else{{el.style.top=start+'px';el.style.left=cross+'px';el.style.height=Math.max(0,end-start)+'px';}}el.textContent=Math.round(gap);stage.appendChild(el);}}
    function showSmartGuides(it,idx){{clearGuides();const others=layout.items.filter((_,i)=>i!==idx&&!selectedIndices.has(i));const xs=[it.x,it.x+it.width/2,it.x+it.width],ys=[it.y,it.y+it.height/2,it.y+it.height];const gx=new Set(),gy=new Set();others.forEach(o=>{{[o.x,o.x+o.width/2,o.x+o.width].forEach(v=>xs.forEach(a=>{{if(Math.abs(v-a)<=guideTolerance)gx.add(v)}}));[o.y,o.y+o.height/2,o.y+o.height].forEach(v=>ys.forEach(a=>{{if(Math.abs(v-a)<=guideTolerance)gy.add(v)}}));}});gx.forEach(v=>addGuide('x',v));gy.forEach(v=>addGuide('y',v));
      const row=others.filter(o=>Math.abs((o.y+o.height/2)-(it.y+it.height/2))<=guideTolerance).sort((a,b)=>a.x-b.x);const left=row.filter(o=>o.x+o.width<=it.x).at(-1),right=row.find(o=>o.x>=it.x+it.width);if(left&&right){{const a=it.x-(left.x+left.width),b=right.x-(it.x+it.width);if(Math.abs(a-b)<=guideTolerance){{addGapGuide('x',left.x+left.width,it.x,it.y+it.height/2,a);addGapGuide('x',it.x+it.width,right.x,it.y+it.height/2,b);}}}}
      const col=others.filter(o=>Math.abs((o.x+o.width/2)-(it.x+it.width/2))<=guideTolerance).sort((a,b)=>a.y-b.y);const up=col.filter(o=>o.y+o.height<=it.y).at(-1),down=col.find(o=>o.y>=it.y+it.height);if(up&&down){{const a=it.y-(up.y+up.height),b=down.y-(it.y+it.height);if(Math.abs(a-b)<=guideTolerance){{addGapGuide('y',up.y+up.height,it.y,it.x+it.width/2,a);addGapGuide('y',it.y+it.height,down.y,it.x+it.width/2,b);}}}}}}
    function draw(){{stage.innerHTML='';stage.style.width=layout.canvas.width+'px';stage.style.height=layout.canvas.height+'px';stage.style.zoom=String(scale);stage.style.transform='none';stage.style.transformOrigin='top left';layout.items.forEach((it,idx)=>{{
      const el=document.createElement('div');const shapeType=it.kind==='shape'?(it.shape_type||'rounded_rect'):'';el.className=`loc ${{shapeType?'map-shape shape-'+shapeType:palette(it.company)}}${{selectedIndices.has(idx)?' selected':''}}`;el.dataset.idx=idx;el.style.left=it.x+'px';el.style.top=it.y+'px';el.style.width=it.width+'px';el.style.height=it.height+'px';el.style.transform=`rotate(${{Number(it.rotation||0)}}deg)`;
      const label=document.createElement('span');label.textContent=shapeType?'':(it.label||it.code);el.style.borderColor=shapeType&&shapeType!=='line'?(it.stroke||'#475569'):'';if(shapeType==='line')el.style.setProperty('--shape-stroke',it.stroke||'#475569');label.style.transform=`rotate(${{-Number(it.rotation||0)}}deg)`;label.style.transformOrigin='center';el.append(label);el.insertAdjacentHTML('beforeend',handles());stage.appendChild(el);
    }});syncPanel();}}
    function syncPanel(){{const selected=selectedIndex!==null&&layout.items[selectedIndex];document.getElementById('emptySelection').hidden=!!selected;document.getElementById('selectedFields').hidden=!selected;if(!selected)return;const isShape=selected.kind==='shape';document.querySelectorAll('.location-only').forEach(el=>el.hidden=isShape);document.querySelectorAll('.shape-only').forEach(el=>el.hidden=!isShape);fields.propCode.value=selected.code||'';fields.propLabel.value=selected.label||selected.code||'';fields.propCompany.value=selected.company||'기타';fields.propKind.value=selected.kind||'location';}}
    function selectItem(idx){{selectedIndex=idx;draw();status.textContent=`${{layout.items[idx].code}} 선택됨`;}}
    function isDuplicateCode(code,exceptIndex=null){{const key=code.trim().toLocaleUpperCase();return layout.items.some((it,idx)=>idx!==exceptIndex&&String(it.code||'').trim().toLocaleUpperCase()===key);}}
    function updateElement(el,it){{el.style.left=it.x+'px';el.style.top=it.y+'px';el.style.width=it.width+'px';el.style.height=it.height+'px';el.style.transform=`rotate(${{Number(it.rotation||0)}}deg)`;const label=el.querySelector('span');if(label)label.style.transform=`rotate(${{-Number(it.rotation||0)}}deg)`;syncPanel();}}
    function stagePoint(e){{const rect=stage.getBoundingClientRect();return {{x:(e.clientX-rect.left)/scale,y:(e.clientY-rect.top)/scale}};}}
    stage.addEventListener('pointerdown',e=>{{const el=e.target.closest('.loc');if(!el){{e.preventDefault();const p=stagePoint(e),box=document.createElement('i');box.className='selection-box';box.style.left=p.x+'px';box.style.top=p.y+'px';stage.appendChild(box);action={{mode:'marquee',sx:p.x,sy:p.y,x:p.x,y:p.y,box,additive:e.ctrlKey||e.shiftKey}};stage.setPointerCapture(e.pointerId);return}}e.preventDefault();const idx=Number(el.dataset.idx),multi=e.ctrlKey||e.shiftKey;if(multi){{if(selectedIndices.has(idx)&&selectedIndices.size>1)selectedIndices.delete(idx);else selectedIndices.add(idx);selectedIndex=selectedIndices.has(idx)?idx:(selectedIndices.values().next().value??null);draw();return}}if(!selectedIndices.has(idx)){{selectedIndices.clear();selectedIndices.add(idx);selectedIndex=idx;draw();}}else selectedIndex=idx;const activeEl=stage.querySelector(`.loc[data-idx="${{idx}}"]`);const it=layout.items[idx];const handle=e.target.closest('.resize-handle');const rotate=e.target.closest('.rotate-handle');const members=Array.from(selectedIndices).map(i=>{{const item=layout.items[i];return {{idx:i,x:item.x,y:item.y,width:item.width,height:item.height,cx:item.x+item.width/2,cy:item.y+item.height/2,rotation:Number(item.rotation||0)}};}});const groupBounds=members.reduce((b,m)=>({{left:Math.min(b.left,m.x),top:Math.min(b.top,m.y),right:Math.max(b.right,m.x+m.width),bottom:Math.max(b.bottom,m.y+m.height)}}),{{left:Infinity,top:Infinity,right:-Infinity,bottom:-Infinity}}),groupCx=(groupBounds.left+groupBounds.right)/2,groupCy=(groupBounds.top+groupBounds.bottom)/2,stageRect=stage.getBoundingClientRect();checkpoint();action={{mode:rotate?'rotate':handle?'resize':'move',dir:handle?.dataset.dir||'',el:activeEl||el,idx,members,sx:e.clientX,sy:e.clientY,x:it.x,y:it.y,width:it.width,height:it.height,rotation:Number(it.rotation||0),groupCx,groupCy,cx:stageRect.left+groupCx*scale,cy:stageRect.top+groupCy*scale}};(activeEl||el).setPointerCapture(e.pointerId);status.textContent=`${{selectedIndices.size}}개 도형 선택됨`;}});

    stage.addEventListener('pointermove',e=>{{if(!action)return;if(action.mode==='marquee'){{const p=stagePoint(e);action.x=p.x;action.y=p.y;const left=Math.min(action.sx,p.x),top=Math.min(action.sy,p.y);action.box.style.left=left+'px';action.box.style.top=top+'px';action.box.style.width=Math.abs(p.x-action.sx)+'px';action.box.style.height=Math.abs(p.y-action.sy)+'px';return}}const it=layout.items[action.idx];const dx=(e.clientX-action.sx)/scale,dy=(e.clientY-action.sy)/scale;if(action.mode==='move'){{action.members.forEach(m=>{{const target=layout.items[m.idx];target.x=clamp(snap(m.x+dx),0,layout.canvas.width-target.width);target.y=clamp(snap(m.y+dy),0,layout.canvas.height-target.height);const node=stage.querySelector(`.loc[data-idx="${{m.idx}}"]`);if(node)updateElement(node,target);}});showSmartGuides(it,action.idx);}}
      else if(action.mode==='rotate'){{const startAngle=Math.atan2(action.sy-action.cy,action.sx-action.cx),now=Math.atan2(e.clientY-action.cy,e.clientX-action.cx),deltaRotation=Math.round(((now-startAngle)*180/Math.PI)/5)*5,rad=deltaRotation*Math.PI/180,cos=Math.cos(rad),sin=Math.sin(rad);action.members.forEach(m=>{{const target=layout.items[m.idx],dx=m.cx-action.groupCx,dy=m.cy-action.groupCy,newCx=action.groupCx+dx*cos-dy*sin,newCy=action.groupCy+dx*sin+dy*cos;target.x=Math.round(newCx-m.width/2);target.y=Math.round(newCy-m.height/2);target.rotation=m.rotation+deltaRotation;const node=stage.querySelector(`.loc[data-idx="${{m.idx}}"]`);if(node)updateElement(node,target);}});}}
      else{{let x=action.x,y=action.y,w=action.width,h=action.height;const dir=action.dir;if(dir.includes('e'))w=snap(action.width+dx);if(dir.includes('s'))h=snap(action.height+dy);if(dir.includes('w')){{x=snap(action.x+dx);w=action.width-(x-action.x);}}if(dir.includes('n')){{y=snap(action.y+dy);h=action.height-(y-action.y);}}if(w<minWidth){{if(dir.includes('w'))x=action.x+action.width-minWidth;w=minWidth;}}if(h<minHeight){{if(dir.includes('n'))y=action.y+action.height-minHeight;h=minHeight;}}x=clamp(x,0,layout.canvas.width-minWidth);y=clamp(y,0,layout.canvas.height-minHeight);w=Math.min(w,layout.canvas.width-x);h=Math.min(h,layout.canvas.height-y);Object.assign(it,{{x,y,width:w,height:h}});showSmartGuides(it,action.idx);}}
      updateElement(action.el,it);status.textContent=`${{it.code}} · ${{it.width}}×${{it.height}} · ${{it.rotation||0}}°`;}});

    function endAction(){{if(action?.mode==='marquee'){{const left=Math.min(action.sx,action.x),right=Math.max(action.sx,action.x),top=Math.min(action.sy,action.y),bottom=Math.max(action.sy,action.y);if(!action.additive)selectedIndices.clear();layout.items.forEach((it,idx)=>{{if(it.x<right&&it.x+it.width>left&&it.y<bottom&&it.y+it.height>top)selectedIndices.add(idx);}});selectedIndex=selectedIndices.size?selectedIndices.values().next().value:null;action.box.remove();status.textContent=`${{selectedIndices.size}}개 도형 영역 선택됨`;action=null;draw();return}}action=null;clearGuides()}} stage.addEventListener('pointerup',endAction);stage.addEventListener('pointercancel',endAction);
    document.getElementById('applyProperties').addEventListener('click',()=>{{if(selectedIndex===null)return;const it=layout.items[selectedIndex];if(it.kind==='shape')return;const code=fields.propCode.value.trim();if(!code){{status.textContent='로케이션 코드를 입력하세요.';return}}if(isDuplicateCode(code,selectedIndex)){{status.textContent='이미 존재하는 로케이션 코드입니다.';return}}checkpoint();Object.assign(it,{{code,label:fields.propLabel.value.trim()||code,company:fields.propCompany.value,kind:fields.propKind.value}});draw();status.textContent=`${{code}} 속성을 적용했습니다.`;}});
    function nextCode(base,n=1){{let i=n,code='';do{{code=`${{base}}-${{String(i).padStart(2,'0')}}`;i++;}}while(isDuplicateCode(code));return code;}}
    document.getElementById('splitSelected').addEventListener('click',()=>{{if(selectedIndex===null)return;const source={{...layout.items[selectedIndex]}};const count=clamp(Math.floor(Number(document.getElementById('splitCount').value)||2),2,100);const axis=document.getElementById('splitAxis').value;const gap=Math.max(0,snap(Number(document.getElementById('splitGap').value)||0));const total=axis==='x'?source.width:source.height;const cell=snap((total-gap*(count-1))/count);if((axis==='x'&&cell<minWidth)||(axis==='y'&&cell<minHeight)){{status.textContent='도형 크기에 비해 분할 개수 또는 간격이 너무 큽니다.';return}}const prefix=document.getElementById('splitPrefix').value.trim()||String(source.code||'LOC').replace(/[-_ ]?\d+$/,'');checkpoint();const group='group-'+Date.now();const made=[],reserved=new Set(layout.items.filter((_,i)=>i!==selectedIndex).map(it=>String(it.code||'').trim().toLocaleUpperCase()));function claimCode(n){{let i=n,code='';do{{code=`${{prefix}}-${{String(i).padStart(2,'0')}}`;i++;}}while(reserved.has(code.toLocaleUpperCase()));reserved.add(code.toLocaleUpperCase());return code;}}for(let i=0;i<count;i++){{const it={{...source,group_id:group,code:claimCode(i+1)}};it.label=it.code;if(axis==='x'){{it.x=source.x+i*(cell+gap);it.width=i===count-1?source.x+source.width-it.x:cell;}}else{{it.y=source.y+i*(cell+gap);it.height=i===count-1?source.y+source.height-it.y:cell;}}made.push(it);}}layout.items.splice(selectedIndex,1,...made);selectedIndices.clear();made.forEach((_,i)=>selectedIndices.add(selectedIndex+i));draw();status.textContent=`${{source.code}}을(를) ${{count}}개로 균등 분할했습니다.`;}});
    document.getElementById('duplicateSelected').addEventListener('click',()=>{{if(selectedIndex===null)return;const source=layout.items[selectedIndex];const members=source.group_id?layout.items.filter(it=>it.group_id===source.group_id):[source];checkpoint();const newGroup='group-'+Date.now();const copies=members.map((it,i)=>{{const copy={{...it,x:clamp(it.x+grid*2,0,layout.canvas.width-it.width),y:clamp(it.y+grid*2,0,layout.canvas.height-it.height),code:nextCode(String(it.code||'LOC')+'-COPY',1)}};if(source.group_id)copy.group_id=newGroup;return copy;}});layout.items.push(...copies);selectedIndex=layout.items.length-copies.length;selectedIndices.clear();copies.forEach((_,i)=>selectedIndices.add(selectedIndex+i));draw();status.textContent=`${{copies.length}}개 도형을 묶음 복제했습니다.`;}});
    function deleteSelection(confirmFirst=true){{if(selectedIndex===null||!selectedIndices.size)return;const code=layout.items[selectedIndex].code,deleteCount=selectedIndices.size;if(confirmFirst&&!confirm(deleteCount>1?`선택한 ${{deleteCount}}개 항목을 삭제할까요?`:`${{code}} 항목을 삭제할까요?`))return;checkpoint();const targets=Array.from(selectedIndices).sort((a,b)=>b-a);targets.forEach(i=>layout.items.splice(i,1));selectedIndices.clear();selectedIndex=null;draw();status.textContent=`${{deleteCount}}개 항목 삭제됨`;}}
    document.getElementById('deleteSelected').addEventListener('click',()=>deleteSelection(true));
    document.getElementById('addItem').addEventListener('click',()=>{{const code=document.getElementById('newCode').value.trim();if(!code){{status.textContent='새 로케이션 코드를 입력하세요.';return}}if(isDuplicateCode(code)){{status.textContent='이미 존재하는 로케이션 코드입니다.';return}}const width=Math.max(minWidth,snap(Number(document.getElementById('newWidth').value)||80));const height=Math.max(minHeight,snap(Number(document.getElementById('newHeight').value)||60));let x=grid,y=grid;for(let i=0;i<layout.items.length;i++){{const occupied=layout.items.some(it=>Math.abs(it.x-x)<grid&&Math.abs(it.y-y)<grid);if(!occupied)break;x+=grid;if(x+width>layout.canvas.width){{x=grid;y+=grid}}}}checkpoint();layout.items.push({{code,label:document.getElementById('newLabel').value.trim()||code,x,y,width:Math.min(width,layout.canvas.width-x),height:Math.min(height,layout.canvas.height-y),rotation:0,company:document.getElementById('newCompany').value,kind:document.getElementById('newKind').value,note:''}});selectedIndex=layout.items.length-1;selectedIndices.clear();selectedIndices.add(selectedIndex);document.getElementById('newCode').value='';document.getElementById('newLabel').value='';draw();status.textContent=`${{code}} 추가됨`;}});
    document.getElementById('undo').addEventListener('click',undo);document.getElementById('redo').addEventListener('click',redo);let itemClipboard=[],pasteCount=0;function copySelection(){{if(!selectedIndices.size)return false;itemClipboard=Array.from(selectedIndices).map(i=>JSON.parse(JSON.stringify(layout.items[i])));pasteCount=0;status.textContent=`${{itemClipboard.length}}개 항목을 복사했습니다.`;return true}}function pasteSelection(){{if(!itemClipboard.length){{status.textContent='복사된 항목이 없습니다.';return}}checkpoint();pasteCount++;const offset=grid*2*pasteCount,groupMap=new Map(),start=layout.items.length,copies=itemClipboard.map(source=>{{const copy={{...source}};copy.x=clamp(source.x+offset,0,layout.canvas.width-source.width);copy.y=clamp(source.y+offset,0,layout.canvas.height-source.height);if(source.kind==='shape')copy.code='__shape-'+Date.now()+'-'+Math.random().toString(36).slice(2,7);else copy.code=nextCode(String(source.code||'LOC')+'-COPY',1);if(source.group_id){{if(!groupMap.has(source.group_id))groupMap.set(source.group_id,'group-'+Date.now()+'-'+groupMap.size);copy.group_id=groupMap.get(source.group_id);}}return copy;}});layout.items.push(...copies);selectedIndices.clear();copies.forEach((_,i)=>selectedIndices.add(start+i));selectedIndex=start;draw();status.textContent=`${{copies.length}}개 항목을 붙여넣었습니다.`;}}document.addEventListener('keydown',e=>{{const tag=String(e.target?.tagName||'').toLowerCase(),editing=['input','textarea','select'].includes(tag)||e.target?.isContentEditable,key=e.key.toLowerCase(),command=e.ctrlKey||e.metaKey;if(command&&!editing&&key==='c'&&copySelection()){{e.preventDefault();return}}if(command&&!editing&&key==='v'){{e.preventDefault();pasteSelection();return}}if(!editing&&(e.key==='Delete'||e.key==='Backspace')){{e.preventDefault();deleteSelection(false);return}}if(command&&!editing&&key==='z'){{e.preventDefault();e.shiftKey?redo():undo();return}}if(command&&!editing&&key==='y'){{e.preventDefault();redo();}}}});updateHistoryButtons();
    function addMapShape(shapeType){{checkpoint();const defaults={{rounded_rect:[180,100,'둥근 사각형'],line:[220,30,'직선'],circle:[100,100,'원']}},spec=defaults[shapeType]||defaults.rounded_rect;let x=grid,y=grid;while(layout.items.some(it=>Math.abs(it.x-x)<grid&&Math.abs(it.y-y)<grid)){{x+=grid;if(x+spec[0]>layout.canvas.width){{x=grid;y+=grid}}}}layout.items.push({{code:'__shape-'+Date.now()+'-'+Math.random().toString(36).slice(2,7),label:spec[2],x,y,width:spec[0],height:spec[1],rotation:0,company:'기타',kind:'shape',shape_type:shapeType,stroke:document.getElementById('shapeStroke').value||'#475569',note:''}});selectedIndex=layout.items.length-1;selectedIndices.clear();selectedIndices.add(selectedIndex);draw();status.textContent=`${{spec[2]}} 도형을 추가했습니다.`;}}document.querySelectorAll('[data-add-shape]').forEach(button=>button.addEventListener('click',()=>addMapShape(button.dataset.addShape)));
        document.getElementById('selectAll').addEventListener('click',()=>{{selectedIndices.clear();layout.items.forEach((_,i)=>selectedIndices.add(i));selectedIndex=layout.items.length?0:null;draw();status.textContent=`도형 ${{selectedIndices.size}}개 전체 선택됨`;}});document.getElementById('clearSelection').addEventListener('click',()=>{{selectedIndices.clear();selectedIndex=null;draw();status.textContent='선택 해제됨';}});
    document.querySelectorAll('.tab-button').forEach(button=>button.addEventListener('click',()=>{{document.querySelectorAll('.tab-button').forEach(x=>x.classList.toggle('active',x===button));document.querySelectorAll('.tab-panel').forEach(panel=>panel.hidden=panel.id!==button.dataset.tab);}}));
    function setScale(v){{scale=Math.max(.1,Math.min(1.5,v));draw();status.textContent='확대 '+Math.round(scale*100)+'%';}}document.getElementById('zoomIn').addEventListener('click',()=>setScale(scale+.1));document.getElementById('zoomOut').addEventListener('click',()=>setScale(scale-.1));document.getElementById('fit').addEventListener('click',()=>{{const s=Math.min((viewport.clientWidth-30)/(layout.canvas.width+2),(viewport.clientHeight-30)/(layout.canvas.height+2));setScale(s);viewport.scrollLeft=0;viewport.scrollTop=0;}});
    function encodedLayout(){{const bytes=new TextEncoder().encode(JSON.stringify(layout));let binary='';bytes.forEach(b=>binary+=String.fromCharCode(b));return btoa(binary).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');}}function navigateWithParam(name,value){{const u=new URL(window.parent.location.href);u.searchParams.set(name,value);window.parent.location.href=u.toString();}}document.getElementById('saveDraft').addEventListener('click',()=>{{try{{localStorage.setItem(draftKey,snapshot());draftLayout=JSON.parse(snapshot());status.textContent='현재 편집 내용을 임시저장했습니다. 실제 지도에는 반영되지 않았습니다.';}}catch(e){{status.textContent='임시저장에 실패했습니다: '+e.message;}}}});document.getElementById('loadDraft').addEventListener('click',()=>{{if(!draftLayout){{status.textContent='불러올 임시저장 내용이 없습니다.';return}}if(!confirm('현재 편집 화면을 임시저장 내용으로 바꿀까요?'))return;checkpoint();restore(JSON.stringify(draftLayout));status.textContent='임시저장 내용을 불러왔습니다. 배치 저장 전까지 실제 지도에는 반영되지 않습니다.';}});document.getElementById('deleteDraft').addEventListener('click',()=>{{if(!draftLayout){{status.textContent='삭제할 임시저장 내용이 없습니다.';return}}if(!confirm('임시저장 내용을 삭제할까요?'))return;try{{localStorage.removeItem(draftKey)}}catch(e){{}}draftLayout=null;status.textContent='임시저장 내용을 삭제했습니다.';}});document.getElementById('save').addEventListener('click',()=>navigateWithParam('layout_save',encodedLayout()));
    draw();if(draftLayout)status.textContent='임시저장된 편집 내용이 있습니다.';
    </script>'''
    components.html(html, height=790, scrolling=False)
