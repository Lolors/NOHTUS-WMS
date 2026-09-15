import json
import re
from datetime import date
from html import escape

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from nohtus.db import q
from nohtus.dates import display_date_only
from nohtus.export_app import db as export_db
from nohtus.services.closing import (
    _infer_customer_from_title,
    _extract_inbound_source_from_memo,
)
from nohtus.services.export_waiting import ensure_export_waiting_tables


_VALID_OUTBOUND_HISTORY_TYPES = (
    "'출고지시'",
    "'출고지시수정'",
    "'출고지시 재차감'",
    "'출고'",
    "'사업장이동'",
    "'사업장+위치이동'",
    "'사업장 이동'",
)
_PRINT_BUTTON_LABEL = "마감 체크리스트 출력"


def _safe_int(value, default=0):
    """NaN, None, 빈 문자열, 비정상 숫자를 안전하게 정수로 변환한다."""
    try:
        if value is None or pd.isna(value):
            return default
        text = str(value).strip().replace(",", "")
        if not text:
            return default
        return int(float(text))
    except (TypeError, ValueError, OverflowError):
        return default


def _safe_text(value, default=""):
    """NaN, None, 빈 문자열을 화면에 nan으로 노출하지 않도록 정리한다."""
    try:
        if value is None or pd.isna(value):
            return default
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return text if text and text.lower() != "nan" else default


def _closing_customer_name(row, customers_df=None):
    """수출대기는 제목을, 일반 출고는 실제 거래처명(매출처/입고처)을 표시한다."""
    title = _safe_text(row.get("출고지시서제목", ""))
    stored_customer = _safe_text(row.get("저장매출처", ""))
    try:
        order_id = int(row.get("출고지시서ID", 0) or 0)
    except (TypeError, ValueError):
        order_id = 0
    if order_id < 0:
        return title
    if stored_customer:
        return stored_customer
    return _infer_customer_from_title(title, customers_df)[0]


def _outbound_customer_from_saved_or_title(customer_name, title, customers_df, customer_company=""):
    """출고지시에 선택한 실제 거래처명과 담당자를 반환한다."""
    saved_customer = _safe_text(customer_name)
    if not saved_customer:
        return _infer_customer_from_title(title, customers_df)

    manager = ""
    if customers_df is not None and not customers_df.empty:
        matched = customers_df[
            customers_df["customer_name"].astype(str).str.strip() == saved_customer
        ]
        saved_company = _safe_text(customer_company)
        if saved_company and "company" in matched.columns:
            company_match = matched[matched["company"].astype(str).str.strip() == saved_company]
            if not company_match.empty:
                matched = company_match
        if not matched.empty:
            manager = _safe_text(matched.iloc[0].get("manager"))
    return saved_customer, manager


def _today_outbound_final_stock_map(items):
    if items.empty:
        return {}
    keys = items[["사업장", "표준제품명", "제조번호", "유통기한"]].drop_duplicates()
    result = {}
    for r in keys.itertuples(index=False):
        company = _safe_text(getattr(r, "사업장", ""))
        product = _safe_text(getattr(r, "표준제품명", ""))
        lot = _safe_text(getattr(r, "제조번호", "-"), "-")
        exp = _safe_text(getattr(r, "유통기한", "-"), "-")
        df = q(
            """
            SELECT COALESCE(SUM(qty), 0) AS qty
            FROM inventory
            WHERE company=?
              AND product_name=?
              AND COALESCE(lot, '-')=?
              AND COALESCE(exp_date, '-')=?
            """,
            (company, product, lot, exp),
        )
        result[(company, product, lot, exp)] = _safe_int(df.iloc[0]["qty"]) if not df.empty else 0
    return result


def _today_outbound_display_df(items):
    group_cols = ["사업장", "로케이션", "표준제품명", "제조번호", "유통기한"]
    final_map = _today_outbound_final_stock_map(items)
    rows = []
    for key, grp in items.groupby(group_cols, sort=False, dropna=False):
        company, location, product, lot, exp = key
        company = _safe_text(company)
        location = _safe_text(location, "-")
        product = _safe_text(product)
        lot = _safe_text(lot, "-")
        exp = _safe_text(exp, "-")
        total_qty = _safe_int(grp["출고수량"].sum())
        final_qty = final_map.get((company, product, lot, exp), 0)
        for i, rr in enumerate(grp.itertuples(index=False)):
            rows.append({
                "사업장": company if i == 0 else "",
                "로케이션": location if i == 0 else "",
                "제품명": product if i == 0 else "",
                "유통기한": exp if i == 0 else "",
                "매출처": _safe_text(getattr(rr, "매출처", "")),
                "수량": _safe_int(getattr(rr, "출고수량", 0)),
                "총 출고수량": total_qty if i == 0 else "",
                "최종재고": final_qty if i == 0 else "",
            })
    return pd.DataFrame(rows, columns=["사업장", "로케이션", "제품명", "유통기한", "매출처", "수량", "총 출고수량", "최종재고"])


def _natural_location_key(value):
    """A1, A2, A10 순서처럼 로케이션의 숫자 부분을 실제 숫자로 정렬한다."""
    text = str(value or "").strip().upper()
    if not text:
        return ((2, ""),)
    parts = re.findall(r"\d+|[^\d]+", text)
    key = []
    for part in parts:
        if part.isdigit():
            key.append((0, int(part)))
        else:
            key.append((1, part))
    return tuple(key)


def _sort_checklist_items(items):
    if items is None or items.empty or "로케이션" not in items.columns:
        return items
    sorted_items = items.copy()
    sorted_items["_location_sort"] = sorted_items["로케이션"].apply(_natural_location_key)
    sort_cols = ["_location_sort"]
    for column in ["사업장", "표준제품명", "제조번호", "유통기한", "출고지시서ID"]:
        if column in sorted_items.columns:
            sort_cols.append(column)
    sorted_items = sorted_items.sort_values(sort_cols, kind="stable").drop(columns=["_location_sort"])
    return sorted_items.reset_index(drop=True)


def _deduplicate_outbound_details(items):
    """일반 출고의 동일 상세가 여러 ID로 저장돼도 체크리스트에는 한 번만 남긴다."""
    if items is None or items.empty:
        return items

    result = items.copy()
    if "출고상세ID" in result.columns:
        detail_ids = result["출고상세ID"]
        duplicated_ids = detail_ids.notna() & detail_ids.duplicated(keep="first")
        result = result.loc[~duplicated_ids].copy()

    signature_columns = [
        "출고지시서ID", "재고ID", "사업장", "로케이션", "표준제품명",
        "제조번호", "유통기한", "출고수량",
    ]
    if not all(column in result.columns for column in signature_columns):
        return result.reset_index(drop=True)

    order_ids = pd.to_numeric(result["출고지시서ID"], errors="coerce")
    regular_outbound = order_ids.gt(0)
    duplicated_signatures = result.duplicated(subset=signature_columns, keep="first")
    return result.loc[~(regular_outbound & duplicated_signatures)].reset_index(drop=True)


def _location_final_stock_map(items):
    """출고·수출대기 후 각 출발 로케이션에 실제로 남은 현재 수량을 계산한다."""
    if items is None or items.empty:
        return {}
    key_cols = ["사업장", "로케이션", "표준제품명", "제조번호", "유통기한"]
    result = {}
    for row in items[key_cols].drop_duplicates().itertuples(index=False):
        company, location, product, lot, exp = [str(value or "-") for value in row]
        stock = q(
            """
            SELECT COALESCE(SUM(qty), 0) AS qty
            FROM inventory
            WHERE company=?
              AND location=?
              AND product_name=?
              AND COALESCE(lot, '-')=?
              AND COALESCE(exp_date, '-')=?
            """,
            (company, location, product, lot, exp),
        )
        result[(company, location, product, lot, exp)] = int(stock.iloc[0]["qty"] or 0) if not stock.empty else 0
    return result


def _export_waiting_rows(ds):
    """마감에는 당일 신규 등록 전체와 당일 수정 중 실제 P 적재 증가분만 표시한다."""
    ensure_export_waiting_tables()
    date_text = str(ds or "")

    # 당일 새로 등록한 수출대기는 현재 남아 있는 목록만 마감 대상으로 본다.
    # 수정 과정에서 삭제된 품목은 export_waiting_items에서 제거되므로 표시되지 않는다.
    created_rows = q(
        """
        SELECT o.title AS 출고지시서제목,
               -o.id AS 출고지시서ID,
               i.source_inventory_id AS 재고ID,
               i.company AS 사업장,
               i.source_location AS 로케이션,
               i.product_name AS 표준제품명,
               COALESCE(i.lot, '-') AS 제조번호,
               COALESCE(i.exp_date, '-') AS 유통기한,
               i.qty AS 출고수량
        FROM export_waiting_orders o
        JOIN export_waiting_items i ON o.id=i.order_id
        WHERE substr(COALESCE(o.created_at, ''), 1, 10)=?
          AND o.status IN ('waiting', 'partial', 'confirmed')
        ORDER BY i.company, i.source_location, i.product_name,
                 i.lot, i.exp_date, o.id, i.id
        """,
        (date_text,),
    )

    # 과거 수출대기 수정은 기존 목록 전체를 원복한 뒤 다시 P에 적재한다.
    # 따라서 P 적재 이력만 세면 수정/삭제 시도 횟수만큼 주문 전체가 반복된다.
    # 같은 날의 P 입출고를 재고키별로 상계해 실제 순증가분만 표시한다.
    changed_rows = q(
        """
        SELECT o.title AS 출고지시서제목,
               -o.id AS 출고지시서ID,
               NULL AS 재고ID,
               CASE
                 WHEN TRIM(COALESCE(t.to_location,''))='P' THEN COALESCE(NULLIF(TRIM(t.from_company),''), t.to_company)
                 ELSE COALESCE(NULLIF(TRIM(t.to_company),''), t.from_company)
               END AS 사업장,
               CASE
                 WHEN TRIM(COALESCE(t.to_location,''))='P' THEN COALESCE(NULLIF(TRIM(t.from_location),''), '-')
                 ELSE COALESCE(NULLIF(TRIM(t.to_location),''), '-')
               END AS 로케이션,
               t.product_name AS 표준제품명,
               COALESCE(t.lot, '-') AS 제조번호,
               COALESCE(t.exp_date, '-') AS 유통기한,
               SUM(
                 CASE
                   WHEN TRIM(COALESCE(t.to_location,''))='P' THEN ABS(COALESCE(t.qty,0))
                   WHEN TRIM(COALESCE(t.from_location,''))='P' THEN -ABS(COALESCE(t.qty,0))
                   ELSE 0
                 END
               ) AS 출고수량
        FROM transactions t
        JOIN export_waiting_orders o
          ON COALESCE(t.memo,'') LIKE '%수출번호: ' || o.export_no || '%'
         AND o.id = (
             SELECT MAX(o2.id)
             FROM export_waiting_orders o2
             WHERE COALESCE(t.memo,'') LIKE '%수출번호: ' || o2.export_no || '%'
         )
        WHERE substr(COALESCE(t.created_at,''), 1, 10)=?
          AND t.tx_type='위치이동'
          AND COALESCE(t.memo,'') LIKE '수출대기 수정 /%'
          AND (
                TRIM(COALESCE(t.to_location,''))='P'
                OR TRIM(COALESCE(t.from_location,''))='P'
              )
          AND substr(COALESCE(o.created_at,''), 1, 10)<>?
        GROUP BY o.id, o.title,
                 CASE
                   WHEN TRIM(COALESCE(t.to_location,''))='P' THEN COALESCE(NULLIF(TRIM(t.from_company),''), t.to_company)
                   ELSE COALESCE(NULLIF(TRIM(t.to_company),''), t.from_company)
                 END,
                 CASE
                   WHEN TRIM(COALESCE(t.to_location,''))='P' THEN COALESCE(NULLIF(TRIM(t.from_location),''), '-')
                   ELSE COALESCE(NULLIF(TRIM(t.to_location),''), '-')
                 END,
                 t.product_name, COALESCE(t.lot,'-'), COALESCE(t.exp_date,'-')
        HAVING SUM(
                 CASE
                   WHEN TRIM(COALESCE(t.to_location,''))='P' THEN ABS(COALESCE(t.qty,0))
                   WHEN TRIM(COALESCE(t.from_location,''))='P' THEN -ABS(COALESCE(t.qty,0))
                   ELSE 0
                 END
               ) > 0
        ORDER BY 사업장, 로케이션, 표준제품명
        """,
        (date_text, date_text),
    )

    frames = []
    if created_rows is not None and not created_rows.empty:
        frames.append(created_rows)
    if changed_rows is not None and not changed_rows.empty:
        frames.append(changed_rows)
    if not frames:
        return pd.DataFrame(
            columns=[
                "출고지시서제목", "출고지시서ID", "재고ID", "사업장", "로케이션",
                "표준제품명", "제조번호", "유통기한", "출고수량",
            ]
        )
    return pd.concat(frames, ignore_index=True)


def _today_outbound_html(items, *, include_style=True):
    items = _sort_checklist_items(items)
    group_cols = ["사업장", "로케이션", "표준제품명", "제조번호", "유통기한"]
    final_map = _location_final_stock_map(items)
    html = []
    if include_style:
        html.extend([
            "<style>",
            ".today-out-table{width:100%;border-collapse:collapse;background:white;border:1px solid #e5e7eb;font-size:14px;}",
            ".today-out-table th{background:#f1f5f9;color:#111827;font-weight:800;border:1px solid #e5e7eb;padding:8px;text-align:center;}",
            ".today-out-table td{border:1px solid #e5e7eb;padding:8px;vertical-align:middle;color:#111827;}",
            ".today-out-table td.num{text-align:right;font-weight:700;}",
            "</style>",
        ])
    html.extend([
        "<table class='today-out-table'>",
        "<thead><tr><th>사업장</th><th>로케이션</th><th>제품명</th><th>유통기한</th><th>매출처</th><th>수량</th><th>총 출고수량</th><th>최종재고</th></tr></thead><tbody>",
    ])
    for key, group in items.groupby(group_cols, sort=False, dropna=False):
        company, location, product, lot, exp = key
        total_qty = int(group["출고수량"].sum())
        final_qty = final_map.get(tuple(str(value or "-") for value in key), 0)
        rowspan = len(group)
        for index, row in enumerate(group.itertuples(index=False)):
            html.append("<tr>")
            if index == 0:
                html.append(f"<td rowspan='{rowspan}'>{escape(str(company))}</td>")
                html.append(f"<td rowspan='{rowspan}'>{escape(str(location))}</td>")
                html.append(f"<td rowspan='{rowspan}'>{escape(str(product))}</td>")
                html.append(f"<td rowspan='{rowspan}'>{escape(str(exp))}</td>")
            html.append(f"<td>{escape(str(getattr(row, '매출처', '') or '-'))}</td>")
            html.append(f"<td class='num'>{int(getattr(row, '출고수량', 0) or 0):,}</td>")
            if index == 0:
                html.append(f"<td class='num' rowspan='{rowspan}'>{total_qty:,}</td>")
                html.append(f"<td class='num' rowspan='{rowspan}'>{final_qty:,}</td>")
            html.append("</tr>")
    html.append("</tbody></table>")
    return "".join(html)


def _render_today_outbound_html(items):
    st.markdown(_today_outbound_html(items), unsafe_allow_html=True)


def _render_print_button(items, ds: str) -> None:
    table_html = _today_outbound_html(items, include_style=False)
    printable_document = f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>마감 체크리스트 · {ds}</title>
<style>
@page {{ size: A4 landscape; margin: 10mm; }}
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; padding: 0; color: #111827; font-family: Arial, 'Malgun Gothic', sans-serif; }}
h1 {{ margin: 0 0 4px; font-size: 22px; }}
.print-date {{ margin: 0 0 14px; color: #475569; font-size: 12px; }}
.today-out-table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #94a3b8; font-size: 10px; table-layout: auto; }}
.today-out-table th {{ background: #f1f5f9; color: #111827; font-weight: 800; border: 1px solid #94a3b8; padding: 5px; text-align: center; white-space: nowrap; }}
.today-out-table td {{ border: 1px solid #94a3b8; padding: 5px; vertical-align: middle; color: #111827; word-break: keep-all; }}
.today-out-table td.num {{ text-align: right; font-weight: 700; white-space: nowrap; }}
thead {{ display: table-header-group; }}
tr {{ break-inside: avoid; page-break-inside: avoid; }}
</style>
</head>
<body>
<h1>마감 체크리스트</h1>
<div class="print-date">기준일: {ds}</div>
{table_html}
</body>
</html>"""
    document_json = json.dumps(printable_document, ensure_ascii=False)

    components.html(
        f"""
        <style>
        html, body {{ margin: 0; padding: 0; background: transparent; }}
        .print-button {{
            width: 100%;
            min-height: 40px;
            border: 1px solid rgba(49, 51, 63, 0.2);
            border-radius: 8px;
            background: white;
            color: #31333f;
            font: 600 14px Arial, 'Malgun Gothic', sans-serif;
            cursor: pointer;
        }}
        .print-button:hover {{ border-color: #ff4b4b; color: #ff4b4b; }}
        </style>
        <button class="print-button" id="closing-print-button" type="button">{_PRINT_BUTTON_LABEL}</button>
        <script>
        const printableDocument = {document_json};
        const button = document.getElementById('closing-print-button');

        button.addEventListener('click', function () {{
            button.disabled = true;
            const oldFrame = document.getElementById('closing-print-frame');
            if (oldFrame) oldFrame.remove();

            const frame = document.createElement('iframe');
            frame.id = 'closing-print-frame';
            frame.setAttribute('title', '마감 체크리스트 인쇄');
            frame.style.position = 'fixed';
            frame.style.right = '0';
            frame.style.bottom = '0';
            frame.style.width = '1px';
            frame.style.height = '1px';
            frame.style.border = '0';
            frame.style.opacity = '0';
            frame.style.pointerEvents = 'none';
            document.body.appendChild(frame);

            try {{
                const printDocument = frame.contentWindow.document;
                printDocument.open();
                printDocument.write(printableDocument);
                printDocument.close();

                const runPrint = function () {{
                    try {{
                        frame.contentWindow.focus();
                        frame.contentWindow.print();
                    }} catch (error) {{
                        alert('인쇄창을 열지 못했습니다. 브라우저에서 인쇄 기능을 허용한 뒤 다시 시도해주세요.');
                    }} finally {{
                        button.disabled = false;
                        setTimeout(function () {{ frame.remove(); }}, 1200);
                    }}
                }};

                if (printDocument.readyState === 'complete') {{
                    setTimeout(runPrint, 80);
                }} else {{
                    frame.onload = function () {{ setTimeout(runPrint, 80); }};
                }}
            }} catch (error) {{
                button.disabled = false;
                frame.remove();
                alert('인쇄용 체크리스트를 만들지 못했습니다. 화면을 새로고침한 뒤 다시 시도해주세요.');
            }}
        }});
        </script>
        """,
        height=44,
        scrolling=False,
    )


def _business_log_company_and_partner(row, memo, customers_df):
    tx_type = _safe_text(getattr(row, "tx_type", ""))
    from_company = _safe_text(getattr(row, "from_company", ""))
    to_company = _safe_text(getattr(row, "to_company", ""))

    if tx_type in {"출고지시", "출고지시수정", "출고지시 재차감", "출고"}:
        partner = ""
        manager = ""
        title_marker = "출고지시서 제목:"
        if title_marker in memo:
            title = memo.split(title_marker, 1)[1].split(" / ", 1)[0].strip()
            partner, manager = _infer_customer_from_title(title, customers_df)
        return from_company or to_company, partner, manager

    inbound_partner = _extract_inbound_source_from_memo(memo)
    if inbound_partner:
        manager = ""
        if customers_df is not None and not customers_df.empty:
            matched = customers_df[customers_df["customer_name"].astype(str).str.strip() == inbound_partner]
            if not matched.empty:
                manager = _safe_text(matched.iloc[0].get("manager"))
        return to_company or from_company, inbound_partner, manager

    if from_company and to_company and from_company != to_company:
        return from_company, to_company, ""
    return from_company or to_company, "", ""


def _scheduled_outbound_business_log(ds, customers_df):
    outbound = q(
        """
        SELECT o.order_date AS log_date,
               COALESCE(o.created_at, '') AS created_at,
               COALESCE(o.title, '') AS title,
               COALESCE(o.customer_name, '') AS customer_name,
               COALESCE(o.customer_company, '') AS customer_company,
               i.company AS company,
               i.product_name AS product_name,
               COALESCE(i.lot, '-') AS lot,
               COALESCE(i.exp_date, '-') AS exp_date,
               i.qty AS qty,
               COALESCE(o.memo, '') AS order_memo
        FROM outbound_orders o
        JOIN outbound_order_items i ON o.id=i.order_id
        WHERE o.order_date=?
          AND IFNULL(o.status,'')<>'취소됨'
        ORDER BY COALESCE(o.created_at, ''), o.id, i.id
        """,
        (ds,),
    )
    rows = []
    for r in outbound.itertuples(index=False):
        company = _safe_text(getattr(r, "company", ""))
        product_name = _safe_text(getattr(r, "product_name", ""))
        qty = _safe_int(getattr(r, "qty", 0))
        if not company and not product_name and qty == 0:
            continue
        title = _safe_text(getattr(r, "title", ""))
        customer_company = _safe_text(getattr(r, "customer_company", ""))
        partner, manager = _outbound_customer_from_saved_or_title(
            getattr(r, "customer_name", ""),
            title,
            customers_df,
            customer_company,
        )
        created_at = _safe_text(getattr(r, "created_at", ""))
        time_text = created_at[11:16] if len(created_at) >= 16 else ""
        rows.append({
            "시간": time_text,
            "유형": "출고지시",
            # 매출 사업장은 실제로 재고를 뺀 사업장(company)이 아니라, 매출처
            # 선택 시 정한 사업장(customer_company) 기준이어야 한다 — "사업장
            # 구분 없이"로 다른 사업장 재고를 골라도 매출은 선택한 매출처의
            # 사업장으로 잡혀야 하기 때문. customer_company가 없는(직접입력
            # 매출처 등) 옛 지시서만 실제 재고 사업장으로 되돌아간다.
            "사업장": customer_company or company,
            "거래처(매출처/입고처)": _safe_text(partner),
            "담당자": _safe_text(manager),
            "제품명": product_name,
            "제조번호": _safe_text(getattr(r, "lot", "-"), "-"),
            "유통기한": display_date_only(_safe_text(getattr(r, "exp_date", "-"), "-")),
            "수량": qty,
            "메모": _safe_text(getattr(r, "order_memo", "")),
        })
    return rows


def _confirmed_export_business_log(ds, customers_df):
    eligible_cases = export_db.rows(
        """SELECT export_no, actual_ship_date
           FROM export_cases
           WHERE case_type<>'historical'
             AND status<>'취소'
             AND stage='국내배송'
             AND substr(COALESCE(actual_ship_date,''),1,10)=?
           ORDER BY id""",
        (ds,),
    )
    export_nos = [str(row['export_no'] or '').strip() for row in eligible_cases if str(row['export_no'] or '').strip()]
    if not export_nos:
        return []

    placeholders = ",".join("?" for _ in export_nos)
    exported = q(
        f"""
        SELECT COALESCE(i.confirmed_at, o.confirmed_at, '') AS confirmed_at,
               COALESCE(i.confirmed_company, o.erp_company, i.company, '') AS company,
               COALESCE(i.confirmed_customer_name, o.erp_customer_name, o.buyer, '') AS customer_name,
               COALESCE(o.title, '') AS title,
               COALESCE(o.export_no, '') AS export_no,
               i.product_name AS product_name,
               COALESCE(i.lot, '-') AS lot,
               COALESCE(i.exp_date, '-') AS exp_date,
               i.qty AS qty
        FROM export_waiting_orders o
        JOIN export_waiting_items i ON o.id=i.order_id
        WHERE COALESCE(i.confirmed, 0)=1
          AND TRIM(COALESCE(o.export_no,'')) IN ({placeholders})
        ORDER BY COALESCE(i.confirmed_at, o.confirmed_at, ''), o.id, i.id
        """,
        tuple(export_nos),
    )
    rows = []
    for r in exported.itertuples(index=False):
        confirmed_at = _safe_text(getattr(r, "confirmed_at", ""))
        customer_name = _safe_text(getattr(r, "customer_name", ""))
        manager = ""
        if customer_name and customers_df is not None and not customers_df.empty:
            matched = customers_df[customers_df["customer_name"].astype(str).str.strip() == customer_name]
            if not matched.empty:
                manager = _safe_text(matched.iloc[0].get("manager"))
        memo_parts = ["수출", "국내배송 단계"]
        export_no = _safe_text(getattr(r, "export_no", ""))
        title = _safe_text(getattr(r, "title", ""))
        if export_no:
            memo_parts.append(f"수출번호: {export_no}")
        if title:
            memo_parts.append(title)
        rows.append({
            "시간": confirmed_at[11:16] if len(confirmed_at) >= 16 else "",
            "유형": "출고지시",
            "사업장": _safe_text(getattr(r, "company", "")),
            "거래처(매출처/입고처)": customer_name,
            "담당자": manager,
            "제품명": _safe_text(getattr(r, "product_name", "")),
            "제조번호": _safe_text(getattr(r, "lot", "-"), "-"),
            "유통기한": display_date_only(_safe_text(getattr(r, "exp_date", "-"), "-")),
            "수량": _safe_int(getattr(r, "qty", 0)),
            "메모": " / ".join(memo_parts),
        })
    return rows


def page_closing():
    st.title("마감")
    st.caption("출고의 마지막 단계입니다. 오늘 출고 체크와 업무일지 작성 기능을 한 화면에서 전환합니다.")
    tab = st.radio("마감", ["오늘 출고 체크", "업무일지 작성"], horizontal=True, key="closing_sub")
    target_date = st.date_input("기준일", value=date.today(), key="closing_date")
    ds = str(target_date)

    if tab == "오늘 출고 체크":
        items = q(f"""SELECT COALESCE(o.title, '') AS 출고지시서제목,
                            o.id AS 출고지시서ID,
                            COALESCE(NULLIF(TRIM(o.customer_name), ''), '') AS 저장매출처,
                            COALESCE(NULLIF(TRIM(o.customer_company), ''), '') AS 저장매출처사업장,
                            i.id AS 출고상세ID,
                            i.inventory_id AS 재고ID,
                            i.company AS 사업장,
                            i.location AS 로케이션,
                            i.product_name AS 표준제품명,
                            COALESCE(i.lot, '-') AS 제조번호,
                            COALESCE(i.exp_date, '-') AS 유통기한,
                            i.qty AS 출고수량
                     FROM outbound_orders o
                     JOIN outbound_order_items i ON o.id=i.order_id
                     WHERE o.order_date=?
                       AND IFNULL(o.status,'')<>'취소됨'
                       AND EXISTS (
                           SELECT 1
                           FROM transactions t
                           WHERE t.tx_type IN ({",".join(_VALID_OUTBOUND_HISTORY_TYPES)})
                             AND COALESCE(t.memo,'') LIKE '%' || '출고지시서 #' || CAST(o.id AS TEXT) || '%'
                       )
                     ORDER BY i.company, i.location, i.product_name, i.lot, i.exp_date, o.id, i.id""", (ds,))

        export_rows = _export_waiting_rows(ds)
        if export_rows is not None and not export_rows.empty:
            if items is None or items.empty:
                items = export_rows
            else:
                items = pd.concat([items, export_rows], ignore_index=True)
        items = _sort_checklist_items(_deduplicate_outbound_details(items))

        if items.empty:
            st.info("해당 날짜의 출고지시가 없습니다.")
        else:
            items["로케이션"] = items["로케이션"].apply(lambda v: _safe_text(v, "-"))
            items["유통기한"] = items["유통기한"].apply(lambda v: display_date_only(_safe_text(v, "-")))
            items["출고수량"] = pd.to_numeric(items["출고수량"], errors="coerce").fillna(0).astype(int)
            try:
                customers_for_close = q("SELECT customer_name, company, manager FROM customers ORDER BY LENGTH(customer_name) DESC")
                items["매출처"] = items.apply(
                    lambda row: _closing_customer_name(row, customers_for_close),
                    axis=1,
                )
            except Exception:
                items["매출처"] = items["저장매출처"].apply(_safe_text)
            _render_today_outbound_html(items)
            btn_left, btn_mid, btn_right = st.columns([3, 2, 3])
            with btn_mid:
                _render_print_button(items, ds)
        return

    st.subheader("업무일지 작성")
    history = q(
        """
        SELECT created_at, tx_type, product_name, lot, exp_date,
               from_company, from_location, to_company, to_location, qty, memo
        FROM transactions
        WHERE substr(created_at, 1, 10)=?
          AND tx_type NOT IN ('출고지시', '출고지시수정', '출고지시 재차감', '출고', '출고지시취소')
          AND COALESCE(tx_type, '') NOT LIKE '%이동%'
          AND COALESCE(tx_type, '') <> '재고조사불러오기'
          AND COALESCE(memo, '') NOT LIKE '%패킹완료 단계로 되돌리기%'
        ORDER BY created_at, id
        """,
        (ds,),
    )
    try:
        customers_for_log = q("SELECT customer_name, company, manager FROM customers ORDER BY LENGTH(customer_name) DESC")
    except Exception:
        customers_for_log = pd.DataFrame(columns=["customer_name", "company", "manager"])

    rows = _scheduled_outbound_business_log(ds, customers_for_log)
    try:
        rows.extend(_confirmed_export_business_log(ds, customers_for_log))
    except Exception:
        pass

    for r in history.itertuples(index=False):
        memo = _safe_text(getattr(r, "memo", ""))
        company, partner, manager = _business_log_company_and_partner(r, memo, customers_for_log)
        created_at = _safe_text(getattr(r, "created_at", ""))
        rows.append({
            "시간": created_at[11:16] if len(created_at) >= 16 else "",
            "유형": _safe_text(getattr(r, "tx_type", "")),
            "사업장": _safe_text(company),
            "거래처(매출처/입고처)": _safe_text(partner),
            "담당자": _safe_text(manager),
            "제품명": _safe_text(getattr(r, "product_name", "")),
            "제조번호": _safe_text(getattr(r, "lot", "-"), "-"),
            "유통기한": display_date_only(_safe_text(getattr(r, "exp_date", "-"), "-")),
            "수량": _safe_int(getattr(r, "qty", 0)),
            "메모": memo,
        })

    if not rows:
        st.info("해당 날짜의 업무 이력이 없습니다.")
        return
    log_df = pd.DataFrame(rows, columns=["시간", "유형", "사업장", "거래처(매출처/입고처)", "담당자", "제품명", "제조번호", "유통기한", "수량", "메모"])
    log_df = log_df.sort_values(["시간", "유형", "사업장", "제품명"], kind="stable").reset_index(drop=True)
    st.dataframe(log_df, hide_index=True, use_container_width=True)
