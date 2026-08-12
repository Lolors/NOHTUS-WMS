"""Apply the real-world Yongin warehouse proportions to the legacy location map HTML."""
from __future__ import annotations


def apply_reality_layout(html: str) -> str:
    """Reposition the legacy interactive map to match the latest draw.io warehouse SVG."""
    css = r'''
<style id="reality-location-map-style">
.map-scroll{height:690px!important;overflow:hidden!important;position:relative;}
.map-stage{width:1279px!important;height:919px!important;min-width:1279px!important;transform:scale(.72)!important;transform-origin:top left!important;}
.big-left{left:0!important;top:0!important;width:220px!important;height:250px!important;border-radius:0!important;box-shadow:none!important;}
.big-left .g2{height:210px!important;}
.big-left .g1row{height:40px!important;grid-template-columns:repeat(3,1fr)!important;}
.big-left .g1row button,.big-left .g1row a{height:40px!important;}
.qp{left:0!important;top:560px!important;width:150px!important;height:175px!important;border:0!important;overflow:visible!important;background:transparent!important;}
.qp button,.qp a{position:absolute!important;left:0!important;width:150px!important;height:50px!important;display:flex!important;align-items:center!important;justify-content:center!important;border:1px solid #334155!important;border-radius:0!important;text-align:center!important;}
.qp button[data-loc="P"]{top:0!important;background:#ffe6cc!important;}
.qp button[data-loc="Q"]{top:125px!important;background:#e1d5e7!important;}
.qp-key{height:auto!important;border-right:0!important;margin-right:8px!important;}
.qp button.selected .qp-key{background:transparent!important;}
.reality-promo{position:absolute;border:1px solid #334155;background:#fff;width:50px;height:120px;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:900;cursor:pointer;font-family:inherit;padding:2px;text-align:center;}
.reality-promo.left{left:35px;top:825px;}
.reality-promo.right{left:155px;top:825px;}
.reality-promo.selected{background:#22c55e!important;color:#fff!important;outline:3px solid rgba(34,197,94,.35)!important;box-shadow:0 0 0 3px rgba(255,255,255,.8),0 0 18px rgba(34,197,94,.75)!important;z-index:4;}
@media(max-width:1100px){.map-scroll{height:610px!important}.map-stage{transform:scale(.62)!important}}
</style>
'''
    script = r'''
<script id="reality-location-map-script">
(function(){
  function pos(el,left,top,width,height){
    if(!el) return;
    el.style.left=left+'px'; el.style.top=top+'px';
    if(width!=null) el.style.width=width+'px';
    if(height!=null) el.style.height=height+'px';
  }
  function button(loc){ return document.querySelector('[data-loc="'+loc+'"]'); }
  function rackFor(loc){ const el=button(loc); return el ? el.closest('.rack') : null; }
  function zonePos(loc,left,top,width,height){ pos(button(loc),left,top,width,height); }
  function applyRealityLayout(){
    const stage=document.querySelector('.map-stage');
    if(!stage || stage.dataset.realityLayout==='1') return;
    stage.dataset.realityLayout='1';

    pos(rackFor('A2-01'),270,0,100,150);
    pos(rackFor('B2-01'),420,0,100,150);
    pos(rackFor('C2-01'),570,0,100,150);
    pos(rackFor('D1-01'),720,0,100,150);
    pos(rackFor('E1-01'),870,0,100,150);
    pos(rackFor('A1-01'),270,220,100,150);
    pos(rackFor('B1-01'),420,220,100,150);
    pos(rackFor('C1-01'),570,220,100,150);

    ['C1-04','C1-05','C1-06'].forEach(loc=>{ const el=button(loc); if(el) el.style.visibility='hidden'; });

    zonePos('F1-01',995,-35,50,120);
    zonePos('F1-02',1090,-35,50,120);
    zonePos('F1-03',1140,-35,50,120);
    zonePos('X2',1210,-10,50,70);
    zonePos('X1-01',1220,180,50,60);
    zonePos('X1-02',1220,240,50,60);
    zonePos('X1-03',1220,300,50,60);

    zonePos('T1',150,510,100,100);
    zonePos('T2',150,685,100,100);
    zonePos('REC',427,485,86,60);
    zonePos('R2',1150,430,60,50);
    zonePos('R1',1210,430,60,50);
    zonePos('N',870,575,120,60);

    document.querySelectorAll('.memo,.label,.small-title').forEach(el=>{ el.style.display='none'; });

    const menu=document.getElementById('specialMenu');
    if(menu){ pos(menu,870,640,160,null); }

    ['left','right'].forEach(side=>{
      const promo=document.createElement('button');
      promo.type='button'; promo.className='reality-promo '+side; promo.dataset.loc='홍보물랙'; promo.textContent='홍보물랙';
      promo.addEventListener('click',()=>{
        const n=button('N'); if(n) n.click();
        setTimeout(()=>{
          const special=document.querySelector('[data-special-loc="홍보물랙"]'); if(special) special.click();
        },0);
      });
      stage.appendChild(promo);
    });
  }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',applyRealityLayout);
  else applyRealityLayout();
})();
</script>
'''
    html = html.replace('</style></head>', '</style>' + css + '</head>', 1)
    html = html.replace('</body>', script + '</body>', 1)
    return html
