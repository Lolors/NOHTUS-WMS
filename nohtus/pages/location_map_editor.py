from __future__ import annotations

import base64
import json

import streamlit as st
import streamlit.components.v1 as components

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
    st.title("🧭 로케이션맵 편집")
    st.caption("로케이션을 마우스로 끌어 이동한 뒤 배치 저장을 누르세요. 저장된 좌표는 실제 로케이션맵에 그대로 적용됩니다.")
    _consume_save_payload()
    layout = load_location_map_layout()
    if not layout.get("items"):
        layout = initial_layout()
    payload = json.dumps(layout, ensure_ascii=False)

    html = f'''<style>
    *{{box-sizing:border-box}} body{{margin:0;font-family:Inter,Segoe UI,Arial,'Noto Sans KR',sans-serif;background:#f8fafc;color:#0f172a}}
    .toolbar{{display:flex;align-items:center;gap:8px;margin-bottom:10px;flex-wrap:wrap}}
    .toolbar button{{border:1px solid #cbd5e1;background:white;border-radius:10px;padding:8px 12px;font-weight:800;cursor:pointer}}
    .toolbar button.primary{{background:#2563eb;color:white;border-color:#2563eb}}
    .status{{font-size:13px;color:#64748b;margin-left:auto}}
    .viewport{{width:100%;height:720px;overflow:auto;border:1px solid #dbe4f0;border-radius:16px;background:white;padding:12px}}
    .stage{{position:relative;background-color:#fff;background-image:linear-gradient(#edf2f7 1px,transparent 1px),linear-gradient(90deg,#edf2f7 1px,transparent 1px);background-size:10px 10px;border:1px solid #cbd5e1}}
    .loc{{position:absolute;display:flex;align-items:center;justify-content:center;text-align:center;border:1.5px solid #334155;border-radius:12px;font-weight:900;font-size:15px;cursor:grab;user-select:none;box-shadow:0 3px 8px rgba(15,23,42,.08)}}
    .loc:active{{cursor:grabbing}} .loc.selected{{outline:4px solid rgba(34,197,94,.32);border-color:#16a34a}}
    .노투스팜{{background:#fff39b}} .노투스{{background:#87d9ee}} .NOH{{background:#efb0e5}} .비자료{{background:#9bd8d8}} .특수{{background:#fff}} .기타{{background:#f1f5f9}}
    .coords{{position:absolute;left:6px;bottom:3px;font-size:9px;color:#64748b;font-weight:500}}
    </style>
    <div class="toolbar">
      <button type="button" id="zoomOut">−</button><button type="button" id="zoomIn">＋</button><button type="button" id="fit">전체보기</button>
      <button type="button" class="primary" id="save">배치 저장</button><span class="status" id="status">드래그해서 위치 변경</span>
    </div>
    <div class="viewport" id="viewport"><div class="stage" id="stage"></div></div>
    <script>
    const layout={payload}; const stage=document.getElementById('stage'); const viewport=document.getElementById('viewport'); const status=document.getElementById('status');
    const grid=Number(layout.canvas.grid||10); let scale=0.82; let drag=null;
    function draw(){{stage.innerHTML=''; stage.style.width=layout.canvas.width+'px';stage.style.height=layout.canvas.height+'px';stage.style.transform=`scale(${{scale}})`;stage.style.transformOrigin='top left';
      layout.items.forEach((it,idx)=>{{const el=document.createElement('div');el.className='loc '+(it.company||'기타');el.dataset.idx=idx;el.style.left=it.x+'px';el.style.top=it.y+'px';el.style.width=it.width+'px';el.style.height=it.height+'px';el.innerHTML=`<span>${{it.label||it.code}}</span><small class="coords">${{it.x}}, ${{it.y}}</small>`;stage.appendChild(el);}});
    }}
    stage.addEventListener('pointerdown',e=>{{const el=e.target.closest('.loc');if(!el)return; const idx=Number(el.dataset.idx); const it=layout.items[idx];drag={{el,idx,sx:e.clientX,sy:e.clientY,x:it.x,y:it.y}};el.setPointerCapture(e.pointerId);document.querySelectorAll('.loc.selected').forEach(x=>x.classList.remove('selected'));el.classList.add('selected');}});
    stage.addEventListener('pointermove',e=>{{if(!drag)return; const it=layout.items[drag.idx];const dx=(e.clientX-drag.sx)/scale,dy=(e.clientY-drag.sy)/scale;it.x=Math.max(0,Math.round((drag.x+dx)/grid)*grid);it.y=Math.max(0,Math.round((drag.y+dy)/grid)*grid);drag.el.style.left=it.x+'px';drag.el.style.top=it.y+'px';drag.el.querySelector('.coords').textContent=it.x+', '+it.y;status.textContent=`${{it.code}} → ${{it.x}}, ${{it.y}}`;}});
    stage.addEventListener('pointerup',()=>{{drag=null}});stage.addEventListener('pointercancel',()=>{{drag=null}});
    function setScale(v){{scale=Math.max(.35,Math.min(1.5,v));draw();status.textContent='확대 '+Math.round(scale*100)+'%';}}
    document.getElementById('zoomIn').addEventListener('click',()=>setScale(scale+.1));document.getElementById('zoomOut').addEventListener('click',()=>setScale(scale-.1));
    document.getElementById('fit').addEventListener('click',()=>{{const s=Math.min((viewport.clientWidth-30)/layout.canvas.width,(viewport.clientHeight-30)/layout.canvas.height);setScale(s);}});
    document.getElementById('save').addEventListener('click',()=>{{const txt=JSON.stringify(layout);const bytes=new TextEncoder().encode(txt);let binary='';bytes.forEach(b=>binary+=String.fromCharCode(b));const enc=btoa(binary).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');const u=new URL(window.parent.location.href);u.searchParams.set('layout_save',enc);window.parent.location.href=u.toString();}});
    draw();
    </script>'''
    components.html(html, height=790, scrolling=False)
