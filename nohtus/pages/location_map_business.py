from __future__ import annotations

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

import nohtus.pages.location_map as location_map_page
from nohtus.pages.location_map import page_map as _page_map


_ORIGINAL_MAP_SEARCH_RESULTS = location_map_page.page_map_search_results
_AVAILABLE_ONLY_KEY = "map_search_available_only"
_EXCLUDE_MATERIALS_KEY = "map_search_exclude_materials"
_SPECIAL_SORT_PREFIX = "\uffff"
_NON_COUNTED_LOCATION = "N-홍보물랙"


def _normalized_location(value):
    return str(value or "").strip().upper().replace(" ", "").lstrip(_SPECIAL_SORT_PREFIX)


def _is_non_counted_location(value):
    return _normalized_location(value) == _NON_COUNTED_LOCATION


def _is_material_or_promo_location(value):
    location = _normalized_location(value)
    return location.startswith("G1") or location.startswith("G2") or "홍보물랙" in location


def _page_map_search_results_with_available_filter(term, compact: bool = False):
    available_only = bool(st.session_state.get(_AVAILABLE_ONLY_KEY, False))
    exclude_materials = bool(st.session_state.get(_EXCLUDE_MATERIALS_KEY, True))
    original_q = location_map_page.q

    def filtered_q(sql, params=()):
        result = original_q(sql, params)
        normalized = " ".join(str(sql or "").lower().split())
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
                keep &= ~locations.apply(_is_material_or_promo_location)
            result = result.loc[keep].copy()
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
    original_product_groups = location_map_page._map_search_product_groups
    original_text_input = st.text_input
    original_button = st.button
    original_markdown = st.markdown

    st.markdown(
        """
        <style>
        .total-card-small { margin-bottom: 12px !important; }
        div[class*="st-key-map_fav_"] { display:none !important; }
        div[data-testid="stTextInput"]:has(input[aria-label="제품명 검색"]) {
            width: calc(100% + 2px) !important;
            max-width: calc(100% + 2px) !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # 검색 폼 내부 체크박스는 검색 버튼을 누르기 전까지 값이 반영되지 않는다.
    # 필터를 폼 밖에서 렌더링해 체크 즉시 rerun되고 검색 결과 집계에도 바로 적용되게 한다.
    filter_spacer, p_col, materials_col = st.columns([5.1, 2.15, 2.75], gap="small")
    with p_col:
        st.checkbox(
            "수출대기(P) 제외",
            value=bool(st.session_state.get(_AVAILABLE_ONLY_KEY, False)),
            key=_AVAILABLE_ONLY_KEY,
            help="수출대기(P) 재고를 총재고와 재고 분포에서 제외합니다.",
        )
    with materials_col:
        st.checkbox(
            "부자재 및 홍보물 제외",
            value=bool(st.session_state.get(_EXCLUDE_MATERIALS_KEY, True)),
            key=_EXCLUDE_MATERIALS_KEY,
            help="G1 계열, G2 계열 및 홍보물랙 재고를 총재고와 재고 분포에서 제외합니다.",
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
                filtered_inv = filtered_inv.loc[
                    ~locations.apply(_is_material_or_promo_location)
                ].copy()

        groups = original_product_groups(product_name, filtered_inv)
        for group in groups:
            rows = group.get("rows")
            if rows is None or rows.empty or "location" not in rows.columns:
                continue
            rows = rows.copy()
            non_counted = rows["location"].apply(_is_non_counted_location)
            if non_counted.any():
                counted_qty = pd.to_numeric(rows.loc[~non_counted, "qty"], errors="coerce").fillna(0).sum()
                group["total_qty"] = int(counted_qty)
                rows.loc[non_counted, "qty"] = 0
                rows.loc[non_counted, "location"] = (
                    _SPECIAL_SORT_PREFIX + rows.loc[non_counted, "location"].astype(str)
                )
                rows.loc[non_counted, "company"] = (
                    _SPECIAL_SORT_PREFIX + rows.loc[non_counted, "company"].astype(str)
                )
                group["rows"] = rows
        return groups

    def patched_text_input(label, *args, **kwargs):
        return original_text_input(label, *args, **kwargs)

    def patched_button(label, *args, **kwargs):
        if isinstance(label, str) and label.startswith("⭐즐겨찾기"):
            return False
        if isinstance(label, str) and label == "제품 사진\n(아래에서 업로드)":
            label = "클릭해서 업로드"
        if isinstance(label, str) and label.startswith(_SPECIAL_SORT_PREFIX):
            clean_label = label.lstrip(_SPECIAL_SORT_PREFIX)
            clicked = original_button(clean_label, *args, **kwargs)
            if clicked and clean_label == "N - 홍보물랙":
                st.session_state["selected_location"] = clean_label
            return clicked
        return original_button(label, *args, **kwargs)

    def patched_markdown(body, *args, **kwargs):
        if isinstance(body, str):
            body = body.replace(_SPECIAL_SORT_PREFIX, "")
            body = body.replace(
                "<div class='dist-cell-qty'>0 EA</div>",
                "<div class='dist-cell-qty'>측정 대상 아님</div>",
            )
            body = body.replace(
                "<span class='company-total-blue'>0 EA</span>",
                "<span class='company-total-blue'>측정 대상 아님</span>",
            )
        return original_markdown(body, *args, **kwargs)

    location_map_page.page_map_search_results = _page_map_search_results_with_available_filter
    location_map_page._map_search_product_groups = patched_product_groups
    st.text_input = patched_text_input
    st.button = patched_button
    st.markdown = patched_markdown
    try:
        _page_map()
    finally:
        location_map_page.page_map_search_results = original_search_results
        location_map_page._map_search_product_groups = original_product_groups
        st.text_input = original_text_input
        st.button = original_button
        st.markdown = original_markdown
    _inject_gm_medic_special_location()
