from __future__ import annotations

import json

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

import nohtus.pages.location_map as location_map_page
import nohtus.services.location_map as location_map_service
from nohtus.db import q
from nohtus.pages.location_map import page_map as _page_map


_ORIGINAL_MAP_SEARCH_RESULTS = location_map_page.page_map_search_results
_AVAILABLE_ONLY_KEY = "map_search_available_only"


def _page_map_search_results_with_available_filter(term, compact: bool = False):
    available_only = bool(st.session_state.get(_AVAILABLE_ONLY_KEY, False))
    original_q = location_map_page.q

    def filtered_q(sql, params=()):
        result = original_q(sql, params)
        normalized = " ".join(str(sql or "").lower().split())
        if (
            available_only
            and isinstance(result, pd.DataFrame)
            and " from inventory " in f" {normalized} "
            and "location" in result.columns
        ):
            return result[result["location"].fillna("").astype(str).str.strip() != "P"].copy()
        return result

    location_map_page.q = filtered_q
    try:
        return _ORIGINAL_MAP_SEARCH_RESULTS(term, compact=compact)
    finally:
        location_map_page.q = original_q


def _export_waiting_rows():
    rows = q(
        """
        SELECT i.id,
               i.company,
               i.product_name,
               COALESCE(i.warehouse_name, '-') AS warehouse_name,
               COALESCE(i.lot, '-') AS lot,
               COALESCE(i.exp_date, '-') AS exp_date,
               i.qty,
               COALESCE(o.country, '') AS country
        FROM export_waiting_items i
        JOIN export_waiting_orders o ON o.id=i.order_id
        WHERE o.status='waiting'
        ORDER BY COALESCE(o.country, ''), i.product_name, i.lot, i.exp_date, i.id
        """
    )
    if rows is None or rows.empty:
        return []
    result = []
    for row in rows.to_dict("records"):
        result.append(
            {
                "id": int(row.get("id") or 0),
                "company": str(row.get("company") or "-"),
                "product_name": str(row.get("product_name") or "-"),
                "warehouse_name": str(row.get("warehouse_name") or "-"),
                "lot": str(row.get("lot") or "-"),
                "exp_date": str(row.get("exp_date") or "-"),
                "qty": int(row.get("qty") or 0),
                "country": str(row.get("country") or "미지정"),
                "location": "P",
            }
        )
    return result


def _patch_location_map_html(body):
    if not isinstance(body, str) or "const DATA =" not in body or "function showDetail(loc)" not in body:
        return body

    export_rows_json = json.dumps(_export_waiting_rows(), ensure_ascii=False)
    body = body.replace(
        "const txData = DATA.tx || [];",
        "const txData = (DATA.tx || []).filter(t => !String(t.tx_type || '').includes('재고조사불러오기'));\n"
        f"const exportWaitingRows = {export_rows_json};",
        1,
    )
    body = body.replace(
        "const rows=rowsFor(loc);",
        "const rows=(loc==='P' && exportWaitingRows.length) ? exportWaitingRows.slice() : rowsFor(loc);",
        1,
    )
    body = body.replace(
        "html+=productCardsHtml(grouped[lvl]);",
        "html+=(loc==='P' ? exportWaitingCardsHtml(grouped[lvl]) : productCardsHtml(grouped[lvl]));",
        1,
    )
    country_function = """
function exportWaitingCardsHtml(rows){
  const countries={};
  rows.forEach(r=>{
    const country=String(r.country||'미지정').trim()||'미지정';
    if(!countries[country]) countries[country]=[];
    countries[country].push(r);
  });
  return Object.keys(countries)
    .sort((a,b)=>a.localeCompare(b,'ko'))
    .map(country=>{
      const countryRows=countries[country].slice().sort((a,b)=>
        String(a.product_name||'').localeCompare(String(b.product_name||''),'ko') ||
        String(a.lot||'').localeCompare(String(b.lot||''),'ko') ||
        String(a.exp_date||'').localeCompare(String(b.exp_date||''),'ko')
      );
      const countryTotal=countryRows.reduce((sum,row)=>sum+(Number(row.qty)||0),0);
      return `<div class="export-country-group"><div class="export-country-head"><span>${esc(country)}</span><strong>${countryTotal} EA</strong></div>${productCardsHtml(countryRows)}</div>`;
    }).join('');
}
"""
    body = body.replace("function cleanDate(v){", country_function + "\nfunction cleanDate(v){", 1)
    body = body.replace(
        ".tx-row{font-size:12px;border-bottom:1px solid #f1f5f9;padding:6px 0;color:#334155;text-align:left;}",
        ".tx-row{font-size:12px;border-bottom:1px solid #f1f5f9;padding:6px 0;color:#334155;text-align:left;}"
        ".export-country-group{margin:12px 0 18px;padding-top:2px;}"
        ".export-country-head{display:flex;justify-content:space-between;align-items:center;background:#eef6ff;border:1px solid #bfdbfe;border-radius:12px;padding:9px 12px;margin:0 0 8px;color:#1e3a8a;font-size:15px;font-weight:900;}"
        ".export-country-head strong{font-size:14px;color:#2563eb;}",
        1,
    )
    return body


def _inject_gm_medic_special_location():
    components.html(
        """
        <script>
        (function(){
          const SPECIAL = '지엠메딕';
          function install(){
            try{
              const frames = Array.from(window.parent.document.querySelectorAll('iframe'));
              for(const frame of frames){
                let doc = null;
                let win = null;
                try{
                  doc = frame.contentDocument || frame.contentWindow.document;
                  win = frame.contentWindow;
                }catch(e){ continue; }
                if(!doc || !win) continue;
                const menu = doc.getElementById('specialMenu');
                if(!menu || doc.querySelector('[data-special-loc="' + SPECIAL + '"]')) continue;

                const btn = doc.createElement('button');
                btn.type = 'button';
                btn.setAttribute('data-special-loc', SPECIAL);
                btn.textContent = SPECIAL;
                btn.addEventListener('click', function(ev){
                  ev.preventDefault();
                  ev.stopPropagation();
                  try { win.toggleSpecialMenu(true); } catch(e) {}
                  try {
                    doc.querySelectorAll('[data-special-loc]').forEach(function(x){
                      x.classList.toggle('selected', x.getAttribute('data-special-loc') === SPECIAL);
                    });
                  } catch(e) {}
                  try { win.showDetail(SPECIAL); } catch(e) {}
                  setTimeout(function(){
                    try {
                      const pill = doc.querySelector('#detail .zone-pill');
                      if(pill) pill.textContent = '기타 위치';
                      const nCell = doc.querySelector('[data-loc="N"]');
                      if(nCell) nCell.classList.add('selected');
                    } catch(e) {}
                  }, 30);
                });
                menu.appendChild(btn);
              }
            }catch(e){}
          }
          install();
          setTimeout(install, 200);
          setTimeout(install, 700);
          setTimeout(install, 1500);
        })();
        </script>
        """,
        height=0,
        scrolling=False,
    )


def page_map():
    original_search_results = location_map_page.page_map_search_results
    original_text_input = st.text_input
    original_components_html = location_map_service.components.html

    def patched_text_input(label, *args, **kwargs):
        if isinstance(label, str) and label == "제품명 검색":
            search_col, filter_col = st.columns([7, 3], gap="small")
            with search_col:
                value = original_text_input(label, *args, **kwargs)
            with filter_col:
                st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
                st.checkbox(
                    "수출대기(P) 제외",
                    value=bool(st.session_state.get(_AVAILABLE_ONLY_KEY, False)),
                    key=_AVAILABLE_ONLY_KEY,
                    help="수출대기(P) 재고를 총재고와 재고 분포에서 제외합니다.",
                )
            return value
        return original_text_input(label, *args, **kwargs)

    def patched_components_html(body, *args, **kwargs):
        return original_components_html(_patch_location_map_html(body), *args, **kwargs)

    location_map_page.page_map_search_results = _page_map_search_results_with_available_filter
    location_map_service.components.html = patched_components_html
    st.text_input = patched_text_input
    try:
        _page_map()
    finally:
        location_map_page.page_map_search_results = original_search_results
        location_map_service.components.html = original_components_html
        st.text_input = original_text_input
    _inject_gm_medic_special_location()
