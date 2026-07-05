from html import escape

import pandas as pd
import streamlit as st

from nohtus.db import q
from nohtus.dates import display_date_only
from nohtus.locations import parse_location
from nohtus.services.location_map import get_product_image_path
from nohtus.services.products import product_options
from nohtus.services.outbound_runtime import product_mapping_name_for
try:
    from nohtus.config_runtime import SPECIAL_LOCATIONS
except Exception:
    SPECIAL_LOCATIONS = ["홍보물랙", "회색 카트", "오른쪽 창고", "사무실(4층)"]


def has_stock_map():
    df = q("SELECT location, SUM(qty) qty FROM inventory WHERE qty>0 GROUP BY location")
    return {r.location: int(r.qty) for r in df.itertuples()}

def loc_has_stock(loc, stock=None):
    stock = stock or has_stock_map()
    return loc in stock or any(k.startswith(loc + "-") for k in stock)

def set_loc(loc):
    st.session_state["selected_loc"] = loc
    st.session_state.pop("selected_product_for_detail", None)

def get_loc():
    try:
        loc = st.query_params.get("loc", "")
        if isinstance(loc, list):
            loc = loc[0] if loc else ""
        if loc:
            st.session_state["selected_loc"] = loc
            return loc
    except Exception:
        pass
    return st.session_state.get("selected_loc", "")

def _loc_group_from_df(df):
    data = {}
    for r in df.itertuples():
        loc = str(r.location)
        data.setdefault(loc, []).append({
            "id": int(r.id),
            "company": str(r.company),
            "product_name": str(r.product_name),
            "warehouse_name": str(r.warehouse_name or "-"),
            "lot": str(r.lot or "-"),
            "exp_date": display_date_only(r.exp_date),
            "qty": int(r.qty),
        })
    return data

def location_zone_name(loc):
    if (loc or '') in SPECIAL_LOCATIONS:
        return '기타 위치'
    area = (loc or '').split('-')[0]
    if area in ["A1","A2","B1","B2","C1"]: return "노투스팜"
    if area in ["C2","D1"]: return "노투스"
    if area == "E1": return "NOH"
    if area == "Q": return "유통기간임박"
    if area == "F1": return "비자료"
    if area == "X1": return "폐기"
    if area == "X2": return "기타 보관 구역"
    if area == "G2": return "패키지 창고"
    if area == "R1": return "냉장고(자료)"
    if area == "R2": return "냉장고(비자료)"
    if area == "REC": return "매입등록대기"
    if area == "P": return "수출대기"
    if area == "N": return "기타 위치"
    return "기타 보관 구역"

def level_label(location):
    if (location or '') in SPECIAL_LOCATIONS:
        return '단 구분 없음'
    parts = (location or '').split('-')
    if len(parts) == 2 and parts[0] == "X1":
        return "1단"
    if len(parts) >= 3 and parts[2].isdigit(): return f"{int(parts[2])}단"
    return "단 구분 없음"

def format_history_rows(tx, current_total):
    rows = []
    running = int(current_total or 0)
    for r in tx.itertuples():
        typ = str(getattr(r, "tx_type", "이력") or "이력")
        qty = int(getattr(r, "qty", 0) or 0)
        if "이동" in typ:
            desc = f"{getattr(r, 'from_location', '-') or '-'} → {getattr(r, 'to_location', '-') or '-'} ({qty}EA)"
        elif "입고" in typ:
            after = running
            before = max(0, after - qty)
            desc = f"{before}EA → {after}EA"
            running = before
        elif "출고" in typ:
            after = running
            before = after + qty
            desc = f"{before}EA → {after}EA"
            running = before
        elif "조정" in typ:
            desc = f"{qty}EA 조정"
        else:
            desc = f"{qty}EA"
        rows.append({"일자": str(getattr(r, "created_at", "") or "")[:10], "이력": f"[{typ}] {desc}"})
    return pd.DataFrame(rows)

def render_product_detail(product_name):
    if not product_name:
        return
    inv = q("""SELECT company, product_name, warehouse_name, lot, exp_date, location, qty
             FROM inventory WHERE product_name=? AND qty>0 ORDER BY location, company""", (product_name,))
    tx = q("""SELECT created_at, tx_type, lot, exp_date, from_location, to_location, qty
             FROM transactions WHERE product_name=? ORDER BY id DESC LIMIT 5""", (product_name,))
    total = int(inv["qty"].sum()) if not inv.empty else 0
    st.markdown("---")
    st.markdown("### 제품 상세")
    st.markdown("<div style='width:150px;height:150px;margin:0 auto 10px;border:1px dashed #cbd5e1;border-radius:16px;background:#f8fafc;display:flex;align-items:center;justify-content:center;color:#94a3b8;'>📷</div>", unsafe_allow_html=True)
    st.markdown("<div class='map-detail-title-wrap'>", unsafe_allow_html=True)
    if st.button(product_name, key=f"detail_search_product_{product_name}", use_container_width=True):
        # iframe/URL 파라미터에 의존하지 않고, 로케이션맵 검색 결과 상태를 직접 지정한다.
        # 검색 입력칸은 빈 상태로 렌더링하고, 결과만 해당 제품명으로 표시한다.
        st.session_state["_map_forced_search_term"] = product_name
        st.session_state["map_view_mode"] = "search"
        st.session_state["_last_map_product_search"] = ""
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='detail-total-text'><span>창고 총재고</span><strong>{total} EA</strong></div>", unsafe_allow_html=True)
    st.markdown("<h5 style='text-align:left;margin:8px 0 6px;'>분산 로케이션</h5>", unsafe_allow_html=True)
    if inv.empty:
        st.caption("재고 위치가 없습니다.")
    else:
        loc_sum = (
            inv.groupby("location", as_index=False)
               .agg(qty=("qty", "sum"), company=("company", lambda x: ", ".join(sorted(set([str(v) for v in x if str(v).strip()])))))
               .sort_values("location")
        )
        for r in loc_sum.itertuples():
            label = f"{r.location}  |  {r.company or '-'}    {int(r.qty)} EA"
            if st.button(label, key=f"jump_loc_{product_name}_{r.location}", use_container_width=True):
                st.session_state["selected_location"] = r.location
                st.rerun()
    st.markdown("<h5 style='text-align:center;margin:8px 0 4px;'>최근 이력 5건</h5>", unsafe_allow_html=True)
    if tx.empty:
        st.caption("최근 이력이 없습니다.")
    else:
        st.dataframe(format_history_rows(tx, total), hide_index=True, use_container_width=True)

def render_detail(loc):
    st.markdown("## 위치 상세 정보")
    if not loc:
        st.info("맵에서 로케이션을 선택하면 상세 재고가 여기에 표시됩니다.")
        return
    area, line, level = parse_location(loc)
    title = f"{area}-{line}" if line else area
    st.caption("선택 위치")
    st.markdown(f"### {title}")
    st.markdown(f"<div class='zone-pill'>{location_zone_name(loc)}</div>", unsafe_allow_html=True)
    df = q("""SELECT id, company, product_name, warehouse_name, lot, exp_date, location, qty
              FROM inventory
              WHERE qty>0 AND (location=? OR location LIKE ?)
              ORDER BY location DESC, company, product_name""", (loc, loc+'-%'))
    if df.empty:
        st.info("현재 이 로케이션에는 표시할 재고가 없습니다.")
        return
    st.metric("현재 총재고", f"{int(df['qty'].sum())} EA")
    df["단"] = df["location"].apply(level_label)
    order = {"3단": 0, "2단": 1, "1단": 2, "단 구분 없음": 9}
    df["_order"] = df["단"].map(order).fillna(5)
    df = df.sort_values(["_order", "company", "product_name"])
    for lvl, g in df.groupby("단", sort=False):
        st.markdown(f"#### {lvl}")
        for product_name, pg in g.groupby("product_name", sort=True):
            total_qty = int(pg["qty"].sum())
            companies = ", ".join(sorted({str(x) for x in pg["company"].dropna().tolist() if str(x).strip()})) or "-"
            lines = []
            for rr in pg.sort_values(["exp_date", "lot", "company"]).itertuples():
                prefix = f"<span class='company-badge'>{rr.company}</span> " if "," in companies else ""
                lines.append(f"<div class='lot-exp'>{prefix}{int(rr.qty)}EA&nbsp;&nbsp;{rr.lot or '-'} | {display_date_only(rr.exp_date)}</div>")
            html_lines = "".join(lines)
            st.markdown(f"""
            <div class="detail-card">
              <div class="card-top"><span class="product-title">{product_name}</span><span class="qty-text">{total_qty} EA</span></div>
              <div class="muted">사업장: {companies}</div>
              {html_lines}
            </div>
            """, unsafe_allow_html=True)
            _btn_l, _btn_c, _btn_r = st.columns([1, 2, 1])
            with _btn_c:
                if st.button("제품 상세 보기", key=f"prod_detail_group_{lvl}_{product_name}", use_container_width=True):
                    st.session_state["selected_product_for_detail"] = product_name
                    st.rerun()
    render_product_detail(st.session_state.get("selected_product_for_detail"))

def page_map_search_results(term):
    """로케이션맵 > 제품명 검색 결과.
    제품 카드 내부의 재고분포를 웹 레이아웃 방식으로 재정렬한다.
    """
    term = (term or "").strip()
    st.markdown("### 제품 검색 결과")
    opts = product_options(term)
    if opts.empty:
        st.info("검색 결과가 없습니다.")
        return

    if len(opts) >= 2:
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

    inv = q("""SELECT id, company, product_name, warehouse_name, lot, exp_date, location, qty
             FROM inventory WHERE qty>0""")
    if not inv.empty:
        inv["exp_date"] = inv["exp_date"].apply(display_date_only)
        for col in ["company", "warehouse_name", "lot", "location", "product_name"]:
            inv[col] = inv[col].fillna("-").astype(str)
        inv["qty"] = pd.to_numeric(inv["qty"], errors="coerce").fillna(0).astype(int)

    totals = pd.DataFrame(columns=["product_name", "total_qty"])
    if not inv.empty:
        totals = inv.groupby("product_name", as_index=False)["qty"].sum().rename(columns={"qty": "total_qty"})
    merged = opts.merge(totals, left_on="standard_name", right_on="product_name", how="left")
    merged["total_qty"] = merged["total_qty"].fillna(0).astype(int)

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
    .dist-wrap{padding:0 0 38px 0;}
    .dist-header{font-size:18px;font-weight:800;color:#111827;margin:2px 0 12px;}
    .dist-rule{height:1px;background:#e5e7eb;margin:0 0 14px;}
    .company-section{margin:0 0 26px 0;}
    .company-section:last-child{margin-bottom:42px;}
    .company-head{display:flex;align-items:center;gap:10px;margin:0 0 10px;flex-wrap:wrap;}
    .company-pill{display:inline-flex;align-items:center;border-radius:12px;background:#e8f8ef;color:#118445;font-size:20px;font-weight:500;padding:7px 14px;white-space:nowrap;}
    .company-erp-name{font-size:14px;color:#9ca3af;font-weight:400;word-break:keep-all;}
    .company-total-blue{font-size:20px;color:#4f6fff;font-weight:700;white-space:nowrap;margin-left:2px;}
    .dist-row{display:grid;grid-template-columns:128px 160px 185px 72px;align-items:center;column-gap:24px;margin:7px 0;max-width:650px;}
    .loc-pill-btn{display:flex;align-items:center;justify-content:center;height:34px;border:1px solid #d8dee8;border-radius:9px;background:#fff;color:#334155;text-decoration:none!important;font-size:15px;font-weight:400;box-shadow:0 1px 1px rgba(15,23,42,.02);}
    .loc-pill-btn:hover{background:#f8fafc;border-color:#94a3b8;color:#111827;text-decoration:none!important;}
    .dist-row a,.dist-row a:visited,.dist-row a:hover,.dist-row a:active{text-decoration:none!important;}
    .dist-row a *{text-decoration:none!important;}
    .lot-info,.exp-info{font-size:16px;font-weight:400;color:#111827;line-height:1.35;white-space:nowrap;}
    .qty-blue{font-size:16px;font-weight:400;color:#4f6fff;text-align:right;white-space:nowrap;line-height:1.35;}
    .no-stock-box{border:1px dashed #cbd5e1;border-radius:16px;background:#f8fafc;padding:22px;color:#64748b;font-weight:800;}
    .detail-total-center{border:1px solid #e5e7eb;border-radius:16px;background:#fafafa;padding:12px 14px;margin:8px auto 14px;text-align:center;} .detail-total-narrow{width:150px;max-width:150px;min-width:150px;}
    .detail-total-label{font-size:13px;color:#6b7280;margin-bottom:4px;}
    .detail-total-value{font-size:24px;color:#111827;font-weight:600;}
    .dist-row-streamlit{margin:0 0 1px;}
    .dist-cell-text{display:flex;align-items:center;height:28px;font-size:14px;font-weight:400;color:#111827;white-space:nowrap;}
    .dist-cell-qty{display:flex;align-items:center;justify-content:flex-end;height:28px;font-size:14px;font-weight:400;color:#4f6fff;white-space:nowrap;}
    .dist-row-streamlit div[data-testid="stButton"] > button[kind="secondary"]{text-decoration:none;min-height:28px;height:28px;padding:0 10px;border-radius:8px;font-size:13px;}
    section[data-testid="stSidebar"] div[data-testid="stButton"] > button, section[data-testid="stSidebar"] div[data-testid="stButton"] > button[kind="secondary"], section[data-testid="stSidebar"] div[data-testid="stButton"] > button[kind="primary"]{background:transparent!important;color:white!important;border:0!important;min-height:auto!important;height:auto!important;padding:8px 10px!important;border-radius:10px!important;font-weight:800!important;font-size:123%!important;text-align:left!important;justify-content:flex-start!important;}
    section[data-testid="stSidebar"] div[data-testid="stButton"] > button p{color:white!important;text-align:left!important;width:100%!important;}
    /* 제품검색 결과 전용 CSS가 사이드바/상단 타이틀 카드까지 침범하지 않도록
       전역 stVerticalBlockBorderWrapper 배경 강제 지정은 제거한다. */
    @media(max-width:1200px){.dist-row{grid-template-columns:110px 130px 150px 65px;column-gap:16px}.lot-info,.exp-info,.qty-blue{font-size:14px}}
    </style>
    """, unsafe_allow_html=True)

    company_order = {"노투스팜": 0, "노투스": 1, "NOH": 2, "비자료": 3}

    def mapping_name_for_company(row_obj, company, product_name):
        company = str(company or "")
        attr_map = {
            "노투스팜": "erp_nohtuspharm_name",
            "NOH": "erp_noh_name",
            "노투스": "erp_nohtus_name",
            "비자료": "bidata_name",
        }
        attr = attr_map.get(company)
        if attr and hasattr(row_obj, attr):
            v = getattr(row_obj, attr, "")
            if str(v or "").strip() and str(v).strip().lower() != "nan":
                return str(v).strip()
        v = product_mapping_name_for(company, product_name)
        return str(v).strip() if str(v or "").strip() else "-"

    for r in merged.itertuples():
        product_name = str(r.standard_name)
        rows = inv[inv["product_name"] == product_name].copy() if not inv.empty else pd.DataFrame()
        total_qty = int(getattr(r, "total_qty", 0) or 0)

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
                st.markdown("<div class='dist-header'>재고 분포</div><div class='dist-rule'></div>", unsafe_allow_html=True)
                if rows.empty:
                    st.markdown("<div class='no-stock-box'>현재 재고가 없습니다.</div>", unsafe_allow_html=True)
                else:
                    rows["_company_order"] = rows["company"].map(company_order).fillna(9)
                    rows = rows.sort_values(["_company_order", "company", "lot", "exp_date", "location"])
                    for company, cg in rows.groupby("company", sort=False):
                        company_total = int(cg["qty"].sum())
                        erp_name = mapping_name_for_company(r, company, product_name)
                        st.markdown(
                            f"<div class='company-head'><span class='company-pill'>{escape(str(company))}</span>"
                            f"<span class='company-erp-name'>{escape(erp_name)}</span>"
                            f"<span class='company-total-blue'>{company_total} EA</span></div>",
                            unsafe_allow_html=True,
                        )
                        cg = cg.sort_values(["location", "lot", "exp_date", "warehouse_name"])
                        for rr in cg.itertuples():
                            loc = str(rr.location)
                            c_loc, c_lot, c_exp, c_qty, c_blank = st.columns([1.08, 1.05, 1.05, 0.55, 3.25], gap="small")
                            with c_loc:
                                if st.button(loc, key=f"map_dist_loc_{product_name}_{rr.id}_{loc}", use_container_width=True):
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

def _map_search_changed():
    # 검색어를 새로 입력하면 검색결과 화면으로 즉시 돌아간다.
    st.session_state["map_view_mode"] = "search"
