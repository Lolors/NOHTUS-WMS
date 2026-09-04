from __future__ import annotations

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

import nohtus.pages.location_map as location_map_page
from nohtus.pages.location_map import page_map as _page_map
from nohtus.db import q


_ORIGINAL_MAP_SEARCH_RESULTS = location_map_page.page_map_search_results
_AVAILABLE_ONLY_KEY = "map_search_available_only"
_EXCLUDE_MATERIALS_KEY = "map_search_exclude_materials"


def _normalized_location(value):
    return str(value or "").strip().upper().replace(" ", "")


def _material_product_names() -> set[str]:
    try:
        rows = q(
            "SELECT DISTINCT standard_name FROM products "
            "WHERE COALESCE(is_material, 0)=1 AND TRIM(COALESCE(standard_name,''))<>''"
        )
    except Exception:
        return set()
    if rows.empty or "standard_name" not in rows.columns:
        return set()
    return {str(value).strip() for value in rows["standard_name"].dropna().tolist() if str(value).strip()}


def _page_map_search_results_with_available_filter(term, compact: bool = False):
    available_only = bool(st.session_state.get(_AVAILABLE_ONLY_KEY, False))
    exclude_materials = bool(st.session_state.get(_EXCLUDE_MATERIALS_KEY, True))
    material_products = _material_product_names() if exclude_materials else set()
    original_q = location_map_page.q

    def filtered_q(sql, params=()):
        sql_text = str(sql or "")
        normalized_location_sql = (
            "REPLACE(REPLACE(REPLACE(UPPER(TRIM(COALESCE(location,''))), ' ', ''), '-', ''), '_', '')"
        )
        if "qty>0" in sql_text and "FROM inventory" in sql_text:
            sql_text = sql_text.replace(
                "qty>0",
                f"(qty>0 OR {normalized_location_sql} LIKE 'G1%' "
                f"OR {normalized_location_sql} LIKE 'G2%')",
            )

        result = original_q(sql_text, params)
        normalized = " ".join(sql_text.lower().split())
        if (
            isinstance(result, pd.DataFrame)
            and " from inventory " in f" {normalized} "
            and "location" in result.columns
        ):
            keep = pd.Series(True, index=result.index)
            locations = result["location"].fillna("").astype(str)
            if available_only:
                keep &= ~locations.apply(lambda value: _normalized_location(value).startswith("P"))
            if exclude_materials:
                if material_products and "product_name" in result.columns:
                    keep &= ~result["product_name"].fillna("").astype(str).str.strip().isin(material_products)
            result = result.loc[keep].copy()
        return result

    location_map_page.q = filtered_q
    try:
        return _ORIGINAL_MAP_SEARCH_RESULTS(term, compact=compact)
    finally:
        location_map_page.q = original_q


def _inject_special_location_button(name):
    """도면의 "기타 위치(N)" 특수 메뉴에 버튼을 하나 추가한다.

    이 메뉴는 로케이션맵 도면(저장된 레이아웃/기본 레이아웃 양쪽)에 하드코딩된
    HTML이라, SPECIAL_LOCATIONS에 새 항목을 추가해도 도면 자체에는 버튼이 안
    생긴다. 도면 HTML을 두 곳(기본/저장 레이아웃)에서 직접 고치는 대신, 이미
    떠 있는 도면에 버튼을 JS로 끼워 넣는 방식을 쓴다 — 레이아웃이 바뀌어도
    깨지지 않는다.
    """
    script = """
        <script>
        (function(){
          const SPECIAL = '__SPECIAL_NAME__';
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
        """.replace("__SPECIAL_NAME__", name)
    components.html(
        script,
        height=0,
        scrolling=False,
    )


def page_map():
    original_search_results = location_map_page.page_map_search_results
    original_product_groups = location_map_page._map_search_product_groups
    original_text_input = st.text_input
    original_button = st.button
    material_products = _material_product_names()

    st.markdown(
        """
        <style>
        /* Give the map more first-screen height than the global 3.2rem layout. */
        div[data-testid="stAppViewContainer"] .main .block-container,
        [data-testid="stMainBlockContainer"] {
            padding-top: 1rem !important;
        }
        /* Hide the stray page caret while preserving it in real form fields. */
        [data-testid="stMain"],
        [data-testid="stMainBlockContainer"],
        #wms-top-anchor {
            caret-color: transparent !important;
        }
        [data-testid="stMain"] input,
        [data-testid="stMain"] textarea,
        [data-testid="stMain"] [contenteditable="true"] {
            caret-color: auto !important;
        }
        .total-card-small { margin-bottom: 12px !important; }
        div[class*="st-key-map_fav_"] { display:none !important; }
        div[data-testid="stTextInput"]:has(input[aria-label="제품명 검색"]) {
            width: 100% !important;
            max-width: 100% !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    def patched_product_groups(product_name, inv_df):
        filtered_inv = inv_df
        if isinstance(inv_df, pd.DataFrame) and not inv_df.empty and "location" in inv_df.columns:
            filtered_inv = inv_df.copy()
            locations = filtered_inv["location"].fillna("").astype(str)
            if bool(st.session_state.get(_AVAILABLE_ONLY_KEY, False)):
                filtered_inv = filtered_inv.loc[
                    ~locations.apply(lambda value: _normalized_location(value).startswith("P"))
                ].copy()
                locations = filtered_inv["location"].fillna("").astype(str)
            if bool(st.session_state.get(_EXCLUDE_MATERIALS_KEY, True)):
                keep = pd.Series(True, index=filtered_inv.index)
                if material_products and "product_name" in filtered_inv.columns:
                    keep &= ~filtered_inv["product_name"].fillna("").astype(str).str.strip().isin(material_products)
                filtered_inv = filtered_inv.loc[keep].copy()

        groups = original_product_groups(product_name, filtered_inv)
        if bool(st.session_state.get(_EXCLUDE_MATERIALS_KEY, True)):
            groups = [
                group
                for group in groups
                if group.get("rows") is not None and not group.get("rows").empty
            ]

        return groups

    def patched_text_input(label, *args, **kwargs):
        if isinstance(label, str) and label == "제품명 검색":
            search_col, p_col, materials_col = st.columns([4.6, 2.55, 2.85], gap="small")
            with search_col:
                value = original_text_input(label, *args, **kwargs)
            with p_col:
                st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
                st.checkbox(
                    "수출대기(P) 제외",
                    value=bool(st.session_state.get(_AVAILABLE_ONLY_KEY, False)),
                    key=_AVAILABLE_ONLY_KEY,
                    help="수출대기(P) 재고를 총재고와 재고 분포에서 제외합니다.",
                )
            with materials_col:
                st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
                st.checkbox(
                    "부자재 제외",
                    value=bool(st.session_state.get(_EXCLUDE_MATERIALS_KEY, True)),
                    key=_EXCLUDE_MATERIALS_KEY,
                    help="부자재 관리 메뉴에 등록된 제품을 총재고와 재고 분포에서 제외합니다.",
                )
            return value
        return original_text_input(label, *args, **kwargs)

    def patched_button(label, *args, **kwargs):
        if isinstance(label, str) and label.startswith("⭐즐겨찾기"):
            return False
        if isinstance(label, str) and label == "제품 사진\n(아래에서 업로드)":
            label = "클릭해서 업로드"
        return original_button(label, *args, **kwargs)

    location_map_page.page_map_search_results = _page_map_search_results_with_available_filter
    location_map_page._map_search_product_groups = patched_product_groups
    st.text_input = patched_text_input
    st.button = patched_button
    try:
        _page_map()
    finally:
        location_map_page.page_map_search_results = original_search_results
        location_map_page._map_search_product_groups = original_product_groups
        st.text_input = original_text_input
        st.button = original_button
    _inject_special_location_button("지엠메딕")
    _inject_special_location_button("거래처 창고")
