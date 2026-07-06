from html import escape
from urllib.parse import quote

import streamlit as st


def render_inbound_quick_location_map():
    """입고 등록용 로케이션 도면.

    Streamlit 네이티브 버튼이 아니라 HTML 도면 링크를 사용한다.
    각 위치는 현재 부모 페이지의 query parameter(inbound_loc)를 갱신한다.
    """
    selected = st.session_state.get("_inbound_selected_loc", "") or "REC"

    def is_selected(loc):
        return selected == loc or (selected and selected.startswith(str(loc) + "-"))

    def href(loc):
        return f"?inbound_loc={quote(str(loc))}"

    def cls(loc, base):
        return f"{base} selected" if is_selected(loc) else base

    def cell(loc, text=None):
        text = text or loc
        return f'<a class="{cls(loc, "map-cell")}" href="{href(loc)}">{escape(str(text))}</a>'

    def rack(labels, left, top, color):
        return f'<div class="rack {color}" style="left:{left}px;top:{top}px;">' + ''.join(cell(x) for x in labels) + '</div>'

    def zone(loc, text, left, top, w, h, color="white"):
        return f'<a class="{cls(loc, "zone")} {color}" href="{href(loc)}" style="left:{left}px;top:{top}px;width:{w}px;height:{h}px;">{text}</a>'

    html = f"""
<style>
.inbound-map-card{{background:#fff;border:1px solid #dbe4f0;border-radius:18px;padding:14px 14px 18px;box-shadow:0 8px 24px rgba(15,23,42,.05);width:100%;overflow:hidden;}}
.inbound-map-card *{{box-sizing:border-box;}}
.inbound-map-title{{font-weight:900;font-size:18px;margin:0 0 10px;color:#111827;}}
.inbound-map-scroll{{overflow:visible;height:670px;padding:0;}}
.inbound-map-stage{{position:relative;width:1160px;height:704px;min-width:1160px;background:#fff;border-radius:14px;transform:scale(0.88);transform-origin:top left;}}
.rack{{position:absolute;width:126px;height:168px;display:grid;grid-template-columns:1fr 1fr;grid-template-rows:1fr 1fr 1fr;border:1px solid #334155;border-radius:9px;overflow:hidden;box-shadow:0 6px 14px rgba(15,23,42,.06);}}
.map-cell,.zone{{appearance:none;position:relative;display:flex;align-items:center;justify-content:center;text-decoration:none!important;color:#0f172a!important;font-weight:900;font-size:14px;border:0;border-right:1px solid rgba(51,65,85,.38);border-bottom:1px solid rgba(51,65,85,.38);cursor:pointer;font-family:inherit;}}
.map-cell:hover,.zone:hover{{outline:3px solid rgba(37,99,235,.22);z-index:2;text-decoration:none!important;}}
.map-cell:nth-child(2n){{border-right:none;}}
.map-cell:nth-child(n+5){{border-bottom:none;}}
.map-cell.selected,.zone.selected{{background:#22c55e!important;color:#ffffff!important;outline:3px solid rgba(34,197,94,.35)!important;box-shadow:0 0 0 3px rgba(255,255,255,.8),0 0 18px rgba(34,197,94,.75)!important;border-color:#16a34a!important;z-index:4;}}
.yellow{{background:#fff39b;}} .blue{{background:#68d2e7;}} .pink{{background:#f0a7e6;}} .gray{{background:#f7f8fa;}} .bidata{{background:#d1d5db;}} .white{{background:#fff;}}
.yellow .map-cell,.zone.yellow{{background:#fff39b;}} .blue .map-cell,.zone.blue{{background:#68d2e7;}} .pink .map-cell,.zone.pink{{background:#f0a7e6;}} .gray .map-cell,.zone.gray{{background:#f7f8fa;}} .bidata .map-cell,.zone.bidata{{background:#d1d5db;}} .white .map-cell,.zone.white{{background:#fff;}}
.zone{{position:absolute;border:1px solid #334155;border-radius:9px;box-shadow:0 6px 14px rgba(15,23,42,.04);}}
.big-left{{position:absolute;left:0;top:0;width:185px;height:282px;border:1px solid #334155;border-radius:10px;overflow:hidden;background:#fff;}}
.big-left a{{appearance:none;position:relative;display:flex;align-items:center;justify-content:center;width:100%;border:0;border-bottom:1px solid #cbd5e1;background:#f7f8fa;color:#0f172a!important;font-weight:900;cursor:pointer;font-family:inherit;text-decoration:none!important;}}
.big-left a:hover{{outline:3px solid rgba(37,99,235,.22);z-index:2;}}
.big-left a.selected{{background:#22c55e!important;color:#fff!important;outline:3px solid rgba(34,197,94,.35)!important;box-shadow:0 0 0 3px rgba(255,255,255,.8),0 0 18px rgba(34,197,94,.75)!important;z-index:4;}}
.g2{{height:225px;background:#f7f8fa;}} .g1row{{height:57px;display:grid;grid-template-columns:1fr 1fr 1fr;}}
.g1row a{{height:57px;border-right:1px solid #cbd5e1;border-bottom:none;}} .g1row a:last-child{{border-right:none;}}
.label{{position:absolute;text-align:center;font-weight:900;color:#111827;font-size:14px;}}
.memo{{position:absolute;color:#334155;font-size:15px;line-height:1.65;}}
.qp{{position:absolute;left:0;top:525px;width:165px;height:148px;border:1px solid #cbd5e1;border-radius:10px;overflow:hidden;background:#fff;}}
.qp a{{position:relative;display:grid;grid-template-columns:58px 1fr;align-items:center;width:100%;height:74px;border:0;border-bottom:1px solid #e2e8f0;background:#fff;color:#111827!important;font-weight:900;cursor:pointer;text-align:left;font-family:inherit;text-decoration:none!important;}}
.qp a:last-child{{border-bottom:none;}}
.qp a.selected{{background:#22c55e!important;color:#ffffff!important;outline:3px solid rgba(34,197,94,.35)!important;box-shadow:0 0 0 3px rgba(255,255,255,.8),0 0 18px rgba(34,197,94,.75)!important;border-color:#16a34a!important;z-index:4;}}
.qp-key{{height:100%;display:flex;align-items:center;justify-content:center;color:#ff221a;font-weight:900;font-size:18px;border-right:1px solid #e2e8f0;}}
.qp .qkey{{background:#f186ca;color:#ff0d0d;}}
.rec-red{{color:#ff1e12;font-weight:900;}}
.small-title{{position:absolute;font-size:14px;font-weight:900;color:#111827;text-align:center;}}
.special-menu{{position:absolute;z-index:30;background:#fff;border:1px solid #cbd5e1;border-radius:12px;box-shadow:0 12px 28px rgba(15,23,42,.10);padding:6px;display:grid;gap:5px;}}
.special-menu a{{appearance:none;border:1px solid #e2e8f0;background:#f8fafc;border-radius:9px;padding:8px 7px;font-size:12px;font-weight:900;color:#0f172a!important;cursor:pointer;font-family:inherit;text-align:center;text-decoration:none!important;}}
.special-menu a:hover,.special-menu a.selected{{background:#22c55e;color:#fff!important;border-color:#16a34a;}}
</style>
<div class="inbound-map-card">
  <div class="inbound-map-title">도면에서 입고 위치 선택</div>
  <div class="inbound-map-scroll"><div class="inbound-map-stage">
    <div class="big-left">
      <a class="g2 gray{' selected' if is_selected('G2') else ''}" href="{href('G2')}">G2</a>
      <div class="g1row">{cell('G1-01')}{cell('G1-02')}{cell('G1-03')}</div>
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
      <a class="{'selected' if is_selected('Q') or is_selected('Q1') or is_selected('Q2') else ''}" href="{href('Q')}"><span class="qp-key qkey">Q</span><span>유통기간임박</span></a>
      <a class="{'selected' if is_selected('P') else ''}" href="{href('P')}"><span class="qp-key">P</span><span>수출대기</span></a>
    </div>
    {zone('REC','<span><span class="rec-red">REC</span>eiving</span>',372,568,142,56,'white')}
    <div class="label" style="left:372px;top:635px;width:142px;">매입등록대기</div>
    {zone('R2','R2',790,460,64,56,'white')}
    {zone('R1','R1',854,460,64,56,'white')}
    <div class="label" style="left:770px;top:526px;width:190px;">R2 비자료 / R1 자료</div>
    <div class="special-menu" style="left:975px;top:492px;width:168px;">
      <a class="{'selected' if is_selected('홍보물랙') else ''}" href="{href('홍보물랙')}">홍보물랙</a>
      <a class="{'selected' if is_selected('회색 카트') else ''}" href="{href('회색 카트')}">회색 카트</a>
      <a class="{'selected' if is_selected('오른쪽 창고') else ''}" href="{href('오른쪽 창고')}">오른쪽 창고</a>
      <a class="{'selected' if is_selected('사무실(4층)') else ''}" href="{href('사무실(4층)')}">사무실(4층)</a>
    </div>
    {zone('N','기타 위치',975,628,168,60,'white')}
  </div></div>
</div>
"""
    st.markdown(html, unsafe_allow_html=True)
