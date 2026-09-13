"""Location map service helpers."""

from __future__ import annotations

import json
from functools import lru_cache
from html import escape
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from nohtus.config import AREA_CONFIG, SPECIAL_LOCATIONS
from nohtus.db import q
from nohtus.dates import display_date_only
from nohtus.locations import REVERSED_LINE_RANGES, expand_row_range
from nohtus.services.location_map_layout import load_location_map_layout

_ASSETS_DIR = Path(__file__).parent / "location_map_assets"


@lru_cache(maxsize=None)
def _read_asset(name: str) -> str:
    """map.css/map.js는 완전히 정적이라(값 삽입 없음) 파일에서 읽어 캐싱한다."""
    return (_ASSETS_DIR / name).read_text(encoding="utf-8")


def _range_block_locations(loc, r):
    """이 재고 행이 "채워짐"으로 함께 표시해야 할 추가 칸 목록(자기 자신 포함)을 만든다.

    location_range_cells(신규, 임의 모양의 칸 목록 JSON)가 있으면 그대로 쓰고,
    없으면 구버전 location_range_end(직사각형 끝 칸)를 직사각형으로 펼쳐 호환한다.
    """
    return expand_row_range(
        loc,
        getattr(r, "location_range_cells", None),
        getattr(r, "location_range_end", None),
    )


def _loc_group_from_df(df):
    data = {}
    for r in df.itertuples():
        loc = str(r.location)
        occupied_cells = sorted(_range_block_locations(loc, r))
        entry = {
            "id": int(r.id),
            "company": str(r.company),
            "product_name": str(r.product_name),
            "warehouse_name": str(r.warehouse_name or "-"),
            "lot": str(r.lot or "-"),
            "exp_date": display_date_only(r.exp_date),
            "qty": int(r.qty),
            # 이 재고 행이 실제로 차지하는 칸 전체(자기 자신 포함). 미니 랙을
            # "로케이션 단위"가 아니라 "이 재고 행 단위"로 정확히 그리는 데 쓴다.
            "primary_location": loc,
            "occupied_cells": occupied_cells,
        }
        # 실제 재고는 location 하나만 기준으로 관리하지만, 범위 지정이 있으면 그
        # 칸들 전체를 로케이션맵에서 "채워짐"으로 함께 표시한다.
        for block_loc in occupied_cells:
            data.setdefault(block_loc, []).append(entry)
    return data


def render_location_map():
    """새로고침 없는 로케이션 맵.
    Streamlit 버튼/링크 대신 components.html 내부 JavaScript로 오른쪽 상세패널만 갱신한다.
    """
    df = q("SELECT id, company, product_name, warehouse_name, lot, exp_date, location, location_range_end, location_range_cells, qty FROM inventory WHERE qty>0 ORDER BY location, company, product_name")
    loc_data = _loc_group_from_df(df)
    tx = q("""SELECT created_at, tx_type, product_name, lot, exp_date, from_location, to_location, qty
              FROM transactions ORDER BY id DESC LIMIT 300""")
    tx_data = tx.to_dict("records") if not tx.empty else []
    selected_loc = st.session_state.get("selected_location", "")
    layout_items = load_location_map_layout().get("items", [])
    layout_company = {
        item.get("code"): item.get("company")
        for item in layout_items
        if item.get("kind") == "location" and item.get("code") and item.get("company")
    }
    # A name the admin explicitly set in the editor's "세부정보 표시 이름" field,
    # separate from "label" (the text drawn on the map cell itself). Used to
    # let the editor override the detail-panel name for zones whose name is
    # otherwise a hardcoded string in zoneName() below (Q/X1/X2/REC/P/... etc).
    layout_label = {
        item.get("code"): item.get("detail_label")
        for item in layout_items
        if item.get("code") and item.get("detail_label")
    }
    area_config = {
        area: {"lines": list(cfg.get("lines") or []), "levels": list(cfg.get("levels") or [])}
        for area, cfg in AREA_CONFIG.items()
    }
    payload = json.dumps(
        {
            "inventory": loc_data,
            "tx": tx_data,
            "selected_location": selected_loc,
            "layout_company": layout_company,
            "layout_label": layout_label,
            "area_config": area_config,
            "reversed_line_ranges": REVERSED_LINE_RANGES,
        },
        ensure_ascii=False,
    )

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
{_read_asset('map.css')}
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
      <div class="special-menu" id="specialMenu" style="left:930px;top:428px;width:155px;"><button type="button" data-special-loc="오른쪽 창고">오른쪽 창고</button><button type="button" data-special-loc="사무실(4층)">사무실(4층)</button></div>
    </div></div>
  </div>
  <div class="side-card" id="detail"><div class="side-title">위치 상세 정보</div><div class="caption">맵에서 로케이션을 선택하면 상세 재고가 여기에 표시됩니다.</div></div>
</div>
<script>
const DATA = {payload};
{_read_asset('map.js')}
</script></body></html>
"""
    components.html(html, height=790, scrolling=False)
