from __future__ import annotations

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

import nohtus.pages.location_map as location_map_page
from nohtus.db import q
from nohtus.pages.location_map import page_map as _page_map
from nohtus.services.products import product_options


_ORIGINAL_MAP_SEARCH_RESULTS = location_map_page.page_map_search_results
_AVAILABLE_ONLY_KEY = "map_search_available_only"


def _search_has_export_waiting_stock(term):
    opts = product_options((term or "").strip())
    if opts is None or opts.empty or "standard_name" not in opts.columns:
        return False
    product_names = [
        str(x).strip()
        for x in opts["standard_name"].dropna().astype(str).drop_duplicates().tolist()
        if str(x).strip()
    ]
    if not product_names:
        return False
    placeholders = ",".join("?" for _ in product_names)
    found = q(
        f"""
        SELECT 1
        FROM inventory
        WHERE qty > 0
          AND location = 'P'
          AND product_name IN ({placeholders})
        LIMIT 1
        """,
        tuple(product_names),
    )
    return found is not None and not found.empty


def _page_map_search_results_with_available_filter(term, compact: bool = False):
    has_p_stock = _search_has_export_waiting_stock(term)
    available_only = False

    if has_p_stock:
        with st.container(border=True):
            available_only = st.checkbox(
                "가용재고만 보기",
                value=bool(st.session_state.get(_AVAILABLE_ONLY_KEY, False)),
                key=_AVAILABLE_ONLY_KEY,
                help="수출대기 로케이션 P의 재고를 총재고와 재고 분포에서 제외합니다.",
            )
            st.caption("끄면 P를 포함한 전체 재고, 켜면 출고 가능한 재고만 표시됩니다.")
    else:
        st.session_state[_AVAILABLE_ONLY_KEY] = False

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
    location_map_page.page_map_search_results = _page_map_search_results_with_available_filter
    try:
        _page_map()
    finally:
        location_map_page.page_map_search_results = original_search_results
    _inject_gm_medic_special_location()
