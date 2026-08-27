from __future__ import annotations

from datetime import date
from html import escape

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from nohtus.db import q
from nohtus.pages.discrepancy_comic import render_discrepancy_comic_panel
from nohtus.services.stock_compare import ignored_erp_diffs

COMPANIES = ["노투스팜", "NOH", "노투스"]
OWN_PRODUCTS = [
    "리쥬네르 골드라벨",
    "리쥬네르 블랙라벨",
    "델가다 (5EA)",
    "디센바 (5EA)",
    "디센바B (5EA)",
    "마이클리어 (10 EA)",
]
OWN_PRODUCTS_BY_COMPANY = {
    "노투스팜": OWN_PRODUCTS + ["바이리쥬 2ml"],
    "NOH": OWN_PRODUCTS,
    "노투스": OWN_PRODUCTS,
}
ALL_OWN_PRODUCTS = list(dict.fromkeys(
    product
    for company in COMPANIES
    for product in OWN_PRODUCTS_BY_COMPANY[company]
))
INBOUND_TYPES = {"입고", "출고지시취소"}
OUTBOUND_TYPES = {"출고지시", "출고지시수정", "출고지시 재차감", "출고", "출고확정"}
MOVE_TYPES = {"사업장이동", "사업장+위치이동", "비자료전환", "이동"}


def _today_text():
    return date.today().strftime("%Y-%m-%d")


def _company_current_stock(company: str) -> pd.DataFrame:
    products = OWN_PRODUCTS_BY_COMPANY[company]
    placeholders = ",".join(["?"] * len(products))
    return q(
        f"""
        SELECT product_name, COALESCE(SUM(qty),0) AS qty
        FROM inventory
        WHERE company=? AND product_name IN ({placeholders})
        GROUP BY product_name
        """,
        tuple([company] + products),
    )


def _today_transactions() -> pd.DataFrame:
    product_placeholders = ",".join(["?"] * len(ALL_OWN_PRODUCTS))
    tx_types = sorted(INBOUND_TYPES | OUTBOUND_TYPES | MOVE_TYPES)
    tx_placeholders = ",".join(["?"] * len(tx_types))
    return q(
        f"""
        SELECT tx_type, product_name, from_company, to_company, qty
        FROM transactions
        WHERE substr(created_at,1,10)=?
          AND product_name IN ({product_placeholders})
          AND tx_type IN ({tx_placeholders})
        """,
        tuple([_today_text()] + ALL_OWN_PRODUCTS + tx_types),
    )


def _today_delta_map() -> dict[tuple[str, str], int]:
    deltas = {
        (company, product): 0
        for company in COMPANIES
        for product in OWN_PRODUCTS_BY_COMPANY[company]
    }
    tx_df = _today_transactions()
    if tx_df.empty:
        return deltas
    for _, row in tx_df.iterrows():
        product = str(row.get("product_name") or "").strip()
        tx_type = str(row.get("tx_type") or "").strip()
        from_company = str(row.get("from_company") or "").strip()
        to_company = str(row.get("to_company") or "").strip()
        qty = int(row.get("qty") or 0)
        if tx_type in INBOUND_TYPES and to_company in COMPANIES:
            key = (to_company, product)
            if key in deltas:
                deltas[key] += qty
        elif tx_type in OUTBOUND_TYPES and from_company in COMPANIES:
            key = (from_company, product)
            if key in deltas:
                deltas[key] -= qty
        elif tx_type in MOVE_TYPES and from_company != to_company:
            from_key = (from_company, product)
            to_key = (to_company, product)
            if from_key in deltas:
                deltas[from_key] -= qty
            if to_key in deltas:
                deltas[to_key] += qty
    return deltas


def _fmt_qty(value) -> str:
    value = int(value or 0)
    return "-" if value == 0 else f"{value:,}"


def _fmt_delta(value) -> str:
    value = int(value or 0)
    if value > 0:
        return f"+{value:,}"
    if value < 0:
        return f"{value:,}"
    return "-"


def _ignored_diff_text(company: str, product: str, ignored_diffs: dict) -> str:
    entry = ignored_diffs.get((company, product))
    if not entry:
        return "-"
    return entry["reason"] or "-"


def _company_table(
    company: str,
    delta_map: dict[tuple[str, str], int],
    ignored_diffs: dict,
) -> pd.DataFrame:
    products = OWN_PRODUCTS_BY_COMPANY[company]
    base = pd.DataFrame({"표준제품명": products})
    current = _company_current_stock(company)
    if not current.empty:
        current = current.rename(columns={"product_name": "표준제품명", "qty": "현재수량"})
    else:
        current = pd.DataFrame(columns=["표준제품명", "현재수량"])
    out = base.merge(current, on="표준제품명", how="left")
    out["현재수량"] = out["현재수량"].fillna(0).astype(int)
    out["증감"] = out["표준제품명"].map(lambda p: int(delta_map.get((company, p), 0) or 0))
    out["전일수량"] = out["현재수량"] - out["증감"]
    out["실물vs전산 차이 원인"] = out["표준제품명"].map(
        lambda p: _ignored_diff_text(company, p, ignored_diffs)
    )
    out = out[["표준제품명", "전일수량", "증감", "현재수량", "실물vs전산 차이 원인"]]
    out["전일수량"] = out["전일수량"].map(_fmt_qty)
    out["증감"] = out["증감"].map(_fmt_delta)
    out["현재수량"] = out["현재수량"].map(_fmt_qty)
    return out


def _table_html(df: pd.DataFrame) -> str:
    head = "".join(f"<th>{escape(str(c))}</th>" for c in df.columns)
    rows = []
    for _, row in df.iterrows():
        cells = []
        for col in df.columns:
            if col == "표준제품명":
                cls = "name"
            elif col == "실물vs전산 차이 원인":
                cls = "note"
            else:
                cls = "num"
            cells.append(f"<td class='{cls}'>{escape(str(row[col]))}</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return """
    <table tabindex='-1'>
      <colgroup><col class='col-name'><col class='col-num'><col class='col-num'><col class='col-num'><col class='col-note'></colgroup>
      <thead><tr>{head}</tr></thead>
      <tbody>{body}</tbody>
    </table>
    """.format(head=head, body="".join(rows))


def _report_html(delta_map: dict[tuple[str, str], int], ignored_diffs: dict) -> str:
    cards = []
    for company in COMPANIES:
        table = _company_table(company, delta_map, ignored_diffs)
        cards.append(f"<section><h2>{escape(company)}</h2>{_table_html(table)}</section>")
    file_name = f"자사제품_조회_{_today_text()}.jpg"
    return f"""
    <!doctype html><html lang='ko'><head><meta charset='utf-8'>
    <script src='https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js'></script>
    <style>
      html,body,*{{caret-color:transparent!important;}}
      body{{margin:0;padding:0;background:transparent;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#0f172a;cursor:default;user-select:none;overflow:visible;}}
      .toolbar{{display:flex;justify-content:flex-start;padding:0 0 12px 0;}}
      .dl-btn{{appearance:none;border:1px solid #cbd5e1;background:#f8fafc;color:#0f172a;font-size:13px;font-weight:600;padding:8px 14px;border-radius:6px;cursor:pointer;user-select:none;}}
      .dl-btn:hover{{background:#eef2f7;}}
      .dl-btn:disabled{{opacity:.6;cursor:default;}}
      .grid{{display:flex;flex-direction:column;gap:26px;align-items:flex-start;justify-content:flex-start;width:100%;background:transparent;}}
      section{{width:56vw;min-width:720px;box-sizing:border-box;overflow-x:auto;}}
      h2{{text-align:center;font-size:32px;font-weight:600;margin:0 0 10px 0;line-height:1.2;}}
      table{{border-collapse:collapse;table-layout:fixed;width:100%;background:white;font-size:13px;outline:0;}}
      .col-name{{width:150px;}}
      .col-num{{width:72px;}}
      .col-note{{width:260px;}}
      th,td{{border:1px solid #e5e7eb;padding:6px 6px;line-height:1.25;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
      th{{background:#f8fafc;color:#334155;font-weight:800;text-align:center;}}
      td.name{{text-align:center;}}
      td.num{{text-align:center;}}
      td.note{{text-align:left;color:#b45309;white-space:normal;}}
      @media(max-width:768px){{.grid{{display:block;width:100%;}}section{{width:100%;min-width:0;margin-bottom:28px;}}body{{overflow:auto;}}}}
    </style></head><body tabindex='-1'>
    <div class='toolbar'><button id='dl-btn' class='dl-btn' type='button'>JPG로 다운로드</button></div>
    <div class='grid' id='capture-target'>{''.join(cards)}</div>
    <script>
      document.getElementById('dl-btn').addEventListener('click', function () {{
        var btn = this;
        var target = document.getElementById('capture-target');
        btn.disabled = true;
        var originalText = btn.textContent;
        btn.textContent = '다운로드 준비 중...';
        var sections = target.querySelectorAll('section');
        var contentWidth = Math.ceil(Math.max.apply(null,
          Array.prototype.map.call(sections, function (el) {{ return el.getBoundingClientRect().width; }})
        ));
        html2canvas(target, {{
          backgroundColor: '#ffffff', scale: 2, useCORS: true,
          width: contentWidth, height: target.scrollHeight,
        }}).then(function (canvas) {{
          var dataUrl = canvas.toDataURL('image/jpeg', 0.95);
          var link = document.createElement('a');
          link.href = dataUrl;
          link.download = {file_name!r};
          document.body.appendChild(link);
          link.click();
          document.body.removeChild(link);
        }}).catch(function (err) {{
          alert('이미지 생성에 실패했습니다: ' + err);
        }}).finally(function () {{
          btn.disabled = false;
          btn.textContent = originalText;
        }});
      }});

      function resizeToContent() {{
        try {{
          var frame = window.frameElement;
          if (frame) {{
            frame.style.height = document.documentElement.scrollHeight + 'px';
          }}
        }} catch (e) {{}}
      }}
      window.addEventListener('load', resizeToContent);
      window.addEventListener('resize', resizeToContent);
      resizeToContent();
      setTimeout(resizeToContent, 300);
    </script>
    </body></html>
    """


def page_own_product_status():
    st.title("자사제품 조회")
    st.caption(
        f"기준일자: {_today_text()} · 전일수량 = 현재수량 - 금일 입고/출고/사업장 이동 증감 · "
        "실물vs전산 차이 원인 = 재고실사 데이터비교의 무시목록(사업장+표준제품명 완전일치)에 등록된 ERP 차이"
    )
    table_col, comic_col = st.columns([2, 1])
    with table_col:
        components.html(
            _report_html(_today_delta_map(), ignored_erp_diffs()), height=960, scrolling=False
        )
    with comic_col:
        render_discrepancy_comic_panel()
