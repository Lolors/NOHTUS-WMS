"""Location map page for NOHTUS WMS.

Migrated from app.py. This module intentionally imports Streamlit because it
contains page rendering code.
"""

from __future__ import annotations

from html import escape

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from nohtus.auth import current_username
from nohtus.config import AREA_COLOR, AREA_CONFIG, COMPANIES
from nohtus.db import q
from nohtus.dates import display_date_only
from nohtus.locations import location_picking_key, parse_location
from nohtus.services.favorites import is_favorite, record_recent_view, toggle_favorite
from nohtus.services.products import product_options


# Some UI/map helper functions may still live in app.py until later steps.
# The migration script injects runtime imports inside the moved page as needed.


def _map_search_warehouse_name(value):
    text = str(value or "").strip()
    return text if text and text.lower() != "nan" else "-"


def _map_search_product_groups(product_name, inv_df):
    """표준제품명 검색 결과를 전산상명칭(ERP명)별로 나눈다.

    같은 표준제품명이라도 inventory.warehouse_name이 2개 이상이면
    로케이션맵 검색 결과에서 전산명별로 별도 카드가 나오도록 한다.
    """
    product_name = str(product_name or "").strip()
    rows = inv_df[inv_df["product_name"] == product_name].copy() if inv_df is not None and not inv_df.empty else pd.DataFrame()
    if rows.empty:
        return [{"product_name": product_name, "warehouse_name": "-", "rows": rows, "total_qty": 0, "split_by_erp": False}]

    rows["warehouse_name"] = rows["warehouse_name"].apply(_map_search_warehouse_name)
    erp_names = [x for x in rows["warehouse_name"].dropna().astype(str).str.strip().drop_duplicates().tolist() if x]
    split_by_erp = len(erp_names) >= 2
    groups = []
    if split_by_erp:
        for wh, g in rows.groupby("warehouse_name", sort=True):
            groups.append({
                "product_name": product_name,
                "warehouse_name": _map_search_warehouse_name(wh),
                "rows": g.copy(),
                "total_qty": int(g["qty"].sum()),
                "split_by_erp": True,
            })
    else:
        groups.append({
            "product_name": product_name,
            "warehouse_name": erp_names[0] if erp_names else "-",
            "rows": rows,
            "total_qty": int(rows["qty"].sum()),
            "split_by_erp": False,
        })
    return groups


def _company_erp_name(cg):
    if cg is None or cg.empty or "warehouse_name" not in cg.columns:
        return ""
    names = [
        _map_search_warehouse_name(x)
        for x in cg["warehouse_name"].dropna().astype(str).str.strip().drop_duplicates().tolist()
        if _map_search_warehouse_name(x) not in ["", "-"]
    ]
    return " / ".join(names)


def _render_favorite_button(product_name, button_key):
    username = current_username()
    if not username or not product_name:
        return
    added = is_favorite(username, product_name)
    label = "⭐즐겨찾기 추가됨" if added else "⭐즐겨찾기"
    if st.button(label, key=button_key, use_container_width=True):
        toggle_favorite(username, product_name)
        st.rerun()


def page_map_search_results(term):
    """로케이션맵 > 제품명 검색 결과.

    같은 표준제품명에 전산상명칭(ERP명)이 여러 개 있으면 전산명별로 별도 표시한다.
    """
    try:
        from nohtus.services.location_map import get_product_image_path
    except Exception:
        get_product_image_path = lambda _name: ""

    term = (term or "").strip()
    st.markdown("### 제품 검색 결과")
    opts = product_options(term)
    if opts.empty:
        st.info("검색 결과가 없습니다.")
        return

    inv = q("""
        SELECT id, company, product_name, warehouse_name, lot, exp_date, location, qty
        FROM inventory
        WHERE qty>0
    """)
    if not inv.empty:
        inv["exp_date"] = inv["exp_date"].apply(display_date_only)
        for col in ["company", "warehouse_name", "lot", "location", "product_name"]:
            inv[col] = inv[col].fillna("-").astype(str)
        inv["warehouse_name"] = inv["warehouse_name"].apply(_map_search_warehouse_name)
        inv["qty"] = pd.to_numeric(inv["qty"], errors="coerce").fillna(0).astype(int)

    result_groups = []
    for product_name in opts["standard_name"].dropna().astype(str).drop_duplicates().tolist():
        result_groups.extend(_map_search_product_groups(product_name, inv))
        record_recent_view(current_username(), product_name)

    if len(result_groups) >= 2:
        st.markdown("""
        <style>
        .wms-floating-top{
            position:fixed;right:28px;bottom:28px;width:46px;height:46px;border-radius:999px;
            background:#0f172a;color:white!important;text-decoration:none!important;
            display:flex;align-items:center;justify-content:center;font-size:24px;font-weight:900;
            box-shadow:0 10px 24px rgba(15,23,42,.28);z-index:9999;line-height:1;
        }
        .wms-floating-top:hover{background:#2563eb;color:white!important;text-decoration:none!important;}
        </style>
        <a class="wms-floating-top" href="#wms-top-anchor" title="맨위로">↑</a>
        """, unsafe_allow_html=True)

    st.markdown("""
    <style>
    .product-main-name{font-size:18px;font-weight:400;color:#111827;line-height:1.35;margin:14px 0 9px;word-break:keep-all;text-align:center;}
    .product-photo-panel{
        width:250px;height:250px;max-width:100%;border:1.5px dashed #d6dee9;border-radius:20px;background:linear-gradient(180deg,#ffffff,#f8fafc);
        display:flex;align-items:center;justify-content:center;color:#94a3b8;font-weight:600;font-size:20px;line-height:1.55;
        margin:0 auto 10px;overflow:hidden;
    }
    .total-card-small{width:50%;min-width:180px;border:1.5px solid #e5e7eb;border-radius:20px;padding:12px 17px;margin:4px auto 48px;display:flex;flex-direction:column;justify-content:center;align-items:center;text-align:center;background:#fafafa;box-shadow:0 2px 8px rgba(15,23,42,.025);}
    .total-label{font-size:15px;font-weight:500;color:#6b7280;text-align:center;}
    .total-value{font-size:24px;font-weight:800;color:#111827;text-align:center;}
    .dist-header{font-size:18px;font-weight:800;color:#111827;margin:2px 0 12px;}
    .dist-rule{height:1px;background:#e5e7eb;margin:0 0 14px;}
    .company-head{display:flex;align-items:center;gap:10px;margin:0 0 10px;flex-wrap:wrap;}
    .company-pill{display:inline-flex;align-items:center;border-radius:12px;background:#e8f8ef;color:#118445;font-size:20px;font-weight:500;padding:7px 14px;white-space:nowrap;}
    .company-erp-name{font-size:20px;color:#4f6fff;font-weight:700;white-space:nowrap;margin-left:2px;}
    .company-total-blue{font-size:20px;color:#4f6fff;font-weight:700;white-space:nowrap;margin-left:2px;}
    .no-stock-box{border:1px dashed #cbd5e1;border-radius:16px;background:#f8fafc;padding:22px;color:#64748b;font-weight:800;}
    .dist-cell-text{display:flex;align-items:center;height:28px;font-size:14px;font-weight:400;color:#111827;white-space:nowrap;}
    .dist-cell-qty{display:flex;align-items:center;justify-content:flex-end;height:28px;font-size:14px;font-weight:400;color:#4f6fff;white-space:nowrap;}
    .dist-row-streamlit div[data-testid="stButton"] > button[kind="secondary"]{text-decoration:none;min-height:28px;height:28px;padding:0 10px;border-radius:8px;font-size:13px;}
    section[data-testid="stSidebar"] div[data-testid="stButton"] > button, section[data-testid="stSidebar"] div[data-testid="stButton"] > button[kind="secondary"], section[data-testid="stSidebar"] div[data-testid="stButton"] > button[kind="primary"]{background:transparent!important;color:white!important;border:0!important;min-height:auto!important;height:auto!important;padding:8px 10px!important;border-radius:10px!important;font-weight:800!important;font-size:123%!important;text-align:left!important;justify-content:flex-start!important;}
    section[data-testid="stSidebar"] div[data-testid="stButton"] > button p{color:white!important;text-align:left!important;width:100%!important;}
    </style>
    """, unsafe_allow_html=True)

    company_order = {"노투스팜": 0, "노투스": 1, "NOH": 2, "비자료": 3}

    for group in result_groups:
        product_name = group["product_name"]
        warehouse_name = group["warehouse_name"]
        rows = group["rows"]
        total_qty = int(group["total_qty"] or 0)

        with st.container(border=True):
            left, right = st.columns([0.95, 2.35], gap="large")
            with left:
                img_path = get_product_image_path(product_name)
                if img_path:
                    st.markdown(
                        f"<div class='product-photo-panel' style=\"border-style:solid;padding:0;\"><img src='file:///{img_path}' style='width:100%;height:100%;object-fit:contain;display:block;' /></div>",
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown("<div class='product-photo-panel'>제품 사진<br>(업로드 가능)</div>", unsafe_allow_html=True)
                st.markdown(f"<div class='product-main-name'>{escape(product_name)}</div>", unsafe_allow_html=True)
                st.markdown(
                    f"<div class='total-card-small'><span class='total-label'>총 재고</span><span class='total-value'>{total_qty} EA</span></div>",
                    unsafe_allow_html=True,
                )

            with right:
                header_col, fav_col = st.columns([8, 2], gap="small")
                with header_col:
                    st.markdown("<div class='dist-header'>재고 분포</div>", unsafe_allow_html=True)
                with fav_col:
                    _render_favorite_button(product_name, f"fav_card_{product_name}_{warehouse_name}")
                st.markdown("<div class='dist-rule'></div>", unsafe_allow_html=True)

                if rows.empty:
                    st.markdown("<div class='no-stock-box'>현재 재고가 없습니다.</div>", unsafe_allow_html=True)
                else:
                    rows = rows.copy()
                    rows["_company_order"] = rows["company"].map(company_order).fillna(9)
                    rows = rows.sort_values(["_company_order", "company", "lot", "exp_date", "location"])
                    for company, cg in rows.groupby("company", sort=False):
                        company_total = int(cg["qty"].sum())
                        erp_name = _company_erp_name(cg)
                        erp_html = f"<span class='company-erp-name'>{escape(erp_name)}</span>" if erp_name else ""
                        st.markdown(
                            f"<div class='company-head'><span class='company-pill'>{escape(str(company))}</span>"
                            f"{erp_html}<span class='company-total-blue'>{company_total} EA</span></div>",
                            unsafe_allow_html=True,
                        )
                        cg = cg.sort_values(["location", "lot", "exp_date", "warehouse_name"])
                        for rr in cg.itertuples():
                            loc = str(rr.location)
                            c_loc, c_lot, c_exp, c_qty, c_blank = st.columns([1.08, 1.05, 1.05, 0.55, 3.25], gap="small")
                            with c_loc:
                                if st.button(loc, key=f"map_dist_loc_{product_name}_{warehouse_name}_{rr.id}_{loc}", use_container_width=True):
                                    st.session_state["selected_location"] = loc
                                    st.session_state["map_view_mode"] = "map"
                                    st.rerun()
                            with c_lot:
                                st.markdown(f"<div class='dist-cell-text'>제조번호: {escape(str(rr.lot or '-'))}</div>", unsafe_allow_html=True)
                            with c_exp:
                                st.markdown(f"<div class='dist-cell-text'>유통기한: {escape(display_date_only(rr.exp_date))}</div>", unsafe_allow_html=True)
                            with c_qty:
                                st.markdown(f"<div class='dist-cell-qty'>{int(rr.qty)} EA</div>", unsafe_allow_html=True)
                        st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)


def page_map():
    from nohtus.services.location_map import render_location_map
    if st.session_state.pop("_scroll_map_top", False):
        components.html("""<script>
        try { window.parent.scrollTo({top:0,left:0,behavior:'auto'}); } catch(e) {}
        try { window.parent.document.documentElement.scrollTop = 0; window.parent.document.body.scrollTop = 0; } catch(e) {}
        </script>""", height=0, scrolling=False)
    st.markdown("""
<style>
/* RC3.3: 로케이션맵 타이틀/도면/상세영역 전체를 살짝 위로 이동 */
div[data-testid="stVerticalBlock"]:has(#wms-top-anchor) {
    margin-top: -15px !important;
}
</style>
<div id='wms-top-anchor'></div>
""", unsafe_allow_html=True)
    forced_search_term = ""
    try:
        qprod = st.session_state.pop("_map_forced_search_term", "") or st.session_state.pop("_pending_map_search_product", "") or st.query_params.get("map_search_product", "")
        if isinstance(qprod, list):
            qprod = qprod[0] if qprod else ""
        forced_search_term = str(qprod or "").strip()
        if forced_search_term:
            st.session_state["map_view_mode"] = "search"
            st.session_state["_last_map_product_search"] = ""
            for _k in ["map_product_search", "map_product_search_forced_blank"]:
                if _k in st.session_state:
                    st.session_state[_k] = ""
            try:
                del st.query_params["map_search_product"]
            except Exception:
                pass
    except Exception:
        forced_search_term = ""
    h1, h2 = st.columns([1.2, 1.8], gap="large")
    with h1:
        st.title("📍로케이션 맵")
    with h2:
        with st.form("map_product_search_form", clear_on_submit=False):
            search_col, btn_col = st.columns([8, 1], gap="small")
            with search_col:
                term = st.text_input(
                    "제품명 검색",
                    value="",
                    placeholder="제품명/ERP명/별칭 일부 입력",
                    key="map_product_search_forced_blank" if forced_search_term else "map_product_search",
                )
            with btn_col:
                st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
                search_submitted = st.form_submit_button("검색", use_container_width=True)

    if "map_view_mode" not in st.session_state:
        st.session_state["map_view_mode"] = "search"

    term_clean = forced_search_term or (term or "").strip()
    last_term = st.session_state.get("_last_map_product_search", "")

    if st.session_state.get("selected_location_from_search"):
        st.session_state["selected_location"] = st.session_state.pop("selected_location_from_search")
        st.session_state["map_view_mode"] = "map"

    if not term_clean:
        st.session_state["map_view_mode"] = "search"
    elif search_submitted or term_clean != last_term:
        st.session_state["map_view_mode"] = "search"

    st.session_state["_last_map_product_search"] = term_clean

    if term_clean and st.session_state.get("map_view_mode") != "map":
        page_map_search_results(term_clean)
    else:
        render_location_map()
