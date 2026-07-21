from __future__ import annotations

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

import nohtus.pages.location_map as location_map_page
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

    # 검색결과의 총재고 카드 아래 여백을 재고분포 제목 간격과 비슷하게 맞춘다.
    st.markdown(
        """
        <style>
        .total-card-small { margin-bottom: 12px !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )

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

    location_map_page.page_map_search_results = _page_map_search_results_with_available_filter
    st.text_input = patched_text_input
    try:
        _page_map()
    finally:
        location_map_page.page_map_search_results = original_search_results
        st.text_input = original_text_input
    _inject_gm_medic_special_location()
