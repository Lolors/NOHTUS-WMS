import streamlit as st


def apply_style():
    st.markdown("""
<style>
/* ===========================
   NOHTUS WMS Base Theme
   =========================== */
:root {
    --nohtus-sidebar: #082f4f;
    --nohtus-sidebar-2: #0b4268;
    --nohtus-text: #111827;
    --nohtus-muted: #64748b;
    --nohtus-border: #dbe4f0;
    --nohtus-bg: #f8fafc;
}

.stApp {
    background: var(--nohtus-bg) !important;
}

h1, h2, h3 {
    color: var(--nohtus-text) !important;
}

/* 본문 폭: 로케이션맵 오른쪽 잘림 방지 */
section.main > div.block-container {
    max-width: none !important;
    padding-left: 2.2rem !important;
    padding-right: 2.2rem !important;
}

/* ===========================
   Sidebar Layout / Color
   =========================== */
section[data-testid="stSidebar"] {
    width: 15vw !important;
    min-width: 150px !important;
    max-width: 200px !important;
    background: linear-gradient(180deg, var(--nohtus-sidebar) 0%, var(--nohtus-sidebar-2) 100%) !important;
}

section[data-testid="stSidebar"] > div,
section[data-testid="stSidebar"] [data-testid="stSidebarContent"] {
    background: transparent !important;
}

section[data-testid="stSidebar"] * {
    color: #ffffff;
}

section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3,
section[data-testid="stSidebar"] .stMarkdown h1,
section[data-testid="stSidebar"] .stMarkdown h2,
section[data-testid="stSidebar"] .stMarkdown h3 {
    color: #ffffff !important;
    font-weight: 900 !important;
}

section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] span,
section[data-testid="stSidebar"] label {
    color: rgba(255,255,255,.92) !important;
}

/* 상위메뉴: 출고/재고/기초 등 markdown 제목은 볼드 유지 */
section[data-testid="stSidebar"] div[data-testid="stMarkdownContainer"] strong,
section[data-testid="stSidebar"] div[data-testid="stMarkdownContainer"] h1,
section[data-testid="stSidebar"] div[data-testid="stMarkdownContainer"] h2,
section[data-testid="stSidebar"] div[data-testid="stMarkdownContainer"] h3,
section[data-testid="stSidebar"] div[data-testid="stMarkdownContainer"] h4 {
    color: #ffffff !important;
    font-weight: 900 !important;
}

/* 하위메뉴 버튼: 왼쪽 정렬 + 볼드 해제 */
section[data-testid="stSidebar"] div[data-testid="stButton"] {
    width: 100% !important;
    text-align: left !important;
}

section[data-testid="stSidebar"] div[data-testid="stButton"] > button,
section[data-testid="stSidebar"] div[data-testid="stButton"] button[kind="secondary"],
section[data-testid="stSidebar"] div[data-testid="stButton"] button[kind="primary"] {
    width: 100% !important;
    display: flex !important;
    justify-content: flex-start !important;
    align-items: center !important;
    text-align: left !important;
    background: transparent !important;
    border: 0 !important;
    box-shadow: none !important;
    padding: .42rem .75rem .42rem .95rem !important;
    min-height: 2.15rem !important;
    border-radius: 10px !important;
}

section[data-testid="stSidebar"] div[data-testid="stButton"] > button:hover,
section[data-testid="stSidebar"] div[data-testid="stButton"] button[kind="secondary"]:hover,
section[data-testid="stSidebar"] div[data-testid="stButton"] button[kind="primary"]:hover {
    background: rgba(255,255,255,.10) !important;
}

section[data-testid="stSidebar"] div[data-testid="stButton"] button > div,
section[data-testid="stSidebar"] div[data-testid="stButton"] button div[data-testid="stMarkdownContainer"],
section[data-testid="stSidebar"] div[data-testid="stButton"] button p,
section[data-testid="stSidebar"] div[data-testid="stButton"] button span {
    width: 100% !important;
    max-width: 100% !important;
    display: block !important;
    text-align: left !important;
    justify-content: flex-start !important;
    margin: 0 !important;
    color: rgba(255,255,255,.94) !important;
    font-weight: 400 !important;
}

/* ===========================
   Location Map / Cards
   =========================== */
.legend-wrap {
    display: flex;
    gap: 12px;
    flex-wrap: wrap;
    margin: 4px 0 14px 0;
}

.legend-chip {
    display: flex;
    align-items: center;
    gap: 8px;
    border: 1px solid var(--nohtus-border);
    background: #fff;
    border-radius: 12px;
    padding: 9px 14px;
    font-weight: 800;
    color: var(--nohtus-text);
}

.swatch {
    width: 18px;
    height: 18px;
    border-radius: 5px;
    border: 1px solid rgba(15,23,42,.12);
    display: inline-block;
}
.swatch.y {background:#fff39b;}
.swatch.b {background:#68d2e7;}
.swatch.p {background:#f0a7e6;}
.swatch.g {background:#f3f4f6;}

.map-card {
    background: #fff;
    border: 1px solid var(--nohtus-border);
    border-radius: 18px;
    padding: 16px;
    box-shadow: 0 8px 24px rgba(15,23,42,.06);
    overflow-x: auto !important;
    overflow-y: visible !important;
    max-width: 100% !important;
}

.map-card > div {
    min-width: max-content;
}

.rack-title {
    text-align: center;
    font-size: 11px;
    color: var(--nohtus-muted);
    font-weight: 800;
    margin-top: 2px;
    height: 0;
    overflow: visible;
}

.mapbtn-wrap {
    position: relative;
    margin: 0;
}

.mapbtn-wrap .stButton > button {
    height: 42px;
    padding: 0 !important;
    border-radius: 0 !important;
    border: 1px solid rgba(51,65,85,.34) !important;
    color: #0f172a !important;
    font-weight: 900 !important;
    font-size: 13px !important;
    box-shadow: none !important;
}

.mapbtn-wrap.yellow .stButton > button {background:#fff39b!important;}
.mapbtn-wrap.blue .stButton > button {background:#68d2e7!important;}
.mapbtn-wrap.pink .stButton > button {background:#f0a7e6!important;}
.mapbtn-wrap.gray .stButton > button {background:#f7f8fa!important;}
.mapbtn-wrap.bidata .stButton > button {background:#d1d5db!important;}
.mapbtn-wrap.white .stButton > button {background:#fff!important;}
.mapbtn-wrap .stButton > button:hover {
    outline: 3px solid rgba(37,99,235,.22) !important;
    z-index: 2;
    position: relative;
}
.mapbtn-wrap.selected .stButton > button {outline:3px solid #2563eb!important;}
.mapbtn-wrap.has-stock:after {
    content:'';
    position:absolute;
    right:8px;
    top:8px;
    width:9px;
    height:9px;
    border-radius:999px;
    background:#65d84f;
    border:1.5px solid #166534;
    z-index:4;
    pointer-events:none;
}

.gbox {
    border:1px solid var(--nohtus-border);
    border-radius:12px;
    overflow:hidden;
    background:#fff;
}
.blank-g {height:78px;border-bottom:1px solid var(--nohtus-border);}
.box-label {text-align:center;padding:10px;font-weight:900;}
.center-label {text-align:center;font-weight:900;font-size:13px;margin-top:8px;color:var(--nohtus-text);}
.memo {padding:46px 8px 8px 8px;line-height:2.8;color:#334155;font-size:14px;white-space:nowrap;}
.qptext {height:42px;display:flex;align-items:center;font-weight:900;border:1px solid #e2e8f0;border-left:0;padding-left:8px;background:#fff;}

.map-detail-title-wrap div[data-testid="stButton"] > button {
    font-size:12pt!important;
    font-weight:400!important;
    text-align:center!important;
    justify-content:center!important;
    border:0!important;
    background:transparent!important;
    color:#111827!important;
    box-shadow:none!important;
    padding:0.15rem 0!important;
}

.detail-total-text {display:flex;gap:8px;align-items:baseline;justify-content:center;color:#334155;font-size:13px;margin:2px auto 10px;}
.detail-total-text strong {font-weight:600;color:#111827;}
.popup-box {background:#ffffff;border:1px solid #bfdbfe;border-radius:16px;padding:14px;margin:8px 0 18px 0;box-shadow:0 10px 28px rgba(37,99,235,.08);}
.zone-pill {display:inline-block;background:#e8f5ee;color:#15803d;font-weight:800;border-radius:10px;padding:6px 10px;margin-bottom:10px;}
.detail-card {background:white;border:1px solid var(--nohtus-border);border-radius:14px;padding:12px;margin:8px 0;box-shadow:0 5px 16px rgba(15,23,42,.05);}
.card-top {display:flex;justify-content:space-between;align-items:center;gap:8px;}
.company-badge {display:inline-block;background:#eff6ff;color:#1d4ed8;font-weight:800;border-radius:999px;padding:3px 8px;font-size:12px;}
.product-title {font-weight:400;font-size:14px;margin-top:8px;color:#111827;}
.muted {color:#64748b;font-size:12px;line-height:1.6;}
.qty-text {font-weight:900;color:#111827;white-space:nowrap;}
.photo-box {width:250px;height:250px;margin-left:auto;margin-right:auto;border:1px dashed #cbd5e1;border-radius:16px;background:#f8fafc;display:flex;align-items:center;justify-content:center;color:#94a3b8;font-weight:800;margin-bottom:10px;}

div[data-testid="stMetric"] {
    background:white;
    border:1px solid var(--nohtus-border);
    border-radius:16px;
    padding:16px;
    box-shadow:0 8px 20px rgba(15,23,42,.05);
}

.mini-cal {background:#fff;border:1px solid var(--nohtus-border);border-radius:16px;padding:14px;margin:8px 0 16px 0;box-shadow:0 8px 20px rgba(15,23,42,.05);}
.mini-cal-head {font-weight:900;margin-bottom:10px;color:#111827;}
.mini-grid {display:grid;grid-template-columns:repeat(7,1fr);gap:6px;margin-bottom:6px;}
.mini-week span {text-align:center;color:#64748b;font-size:12px;font-weight:900;}
.cal-day {height:34px;display:flex;align-items:center;justify-content:center;border-radius:10px;background:#f8fafc;color:#334155;font-weight:800;position:relative;}
.cal-day.on {background:#2563eb;color:white;box-shadow:0 0 0 3px rgba(37,99,235,.15);}
.cal-day small {position:absolute;right:4px;top:3px;font-size:10px;background:white;color:#2563eb;border-radius:999px;min-width:15px;height:15px;line-height:15px;text-align:center;}
.cal-day.empty {background:transparent;}
</style>
""", unsafe_allow_html=True)


def apply_inbound_bridge_style():
    """입고 도면 클릭 브리지용 숨김 input/button CSS."""
    st.markdown("""
<style>
/* 입고 도면 클릭 브리지: 화면에는 보이지 않게 숨기되 기능은 유지한다. */
div.st-key-_inbound_js_loc_buffer,
div.st-key-_inbound_apply_btn,
.st-key-_inbound_js_loc_buffer,
.st-key-_inbound_apply_btn {
    position: absolute !important;
    left: -9999px !important;
    top: -9999px !important;
    width: 1px !important;
    min-width: 1px !important;
    max-width: 1px !important;
    height: 1px !important;
    min-height: 1px !important;
    max-height: 1px !important;
    overflow: hidden !important;
    opacity: 0 !important;
    pointer-events: none !important;
    margin: 0 !important;
    padding: 0 !important;
    z-index: -1 !important;
}

div[data-testid="stTextInput"]:has(input[aria-label="__입고도면선택값"]),
div.st-key-_inbound_apply_btn button {
    position: absolute !important;
    left: -9999px !important;
    top: -9999px !important;
    width: 1px !important;
    height: 1px !important;
    overflow: hidden !important;
    opacity: 0 !important;
    pointer-events: none !important;
    margin: 0 !important;
    padding: 0 !important;
}
</style>
""", unsafe_allow_html=True)
