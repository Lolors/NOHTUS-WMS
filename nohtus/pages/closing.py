from datetime import date
from html import escape

import pandas as pd
import streamlit as st

from nohtus.db import q
from nohtus.dates import display_date_only
from nohtus.services.closing import (
    _infer_customer_from_title,
    _extract_inbound_source_from_memo,
    dataframe_to_excel_bytes,
    page_erp_stock_compare,
)


def _join_unique(values):
    result = []
    for v in values:
        text = str(v or "").strip()
        if text and text not in result:
            result.append(text)
    return ", ".join(result)


def _daily_outbound_check_rows(items: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """오늘 출고 체크 표를 병합형 화면표시용/엑셀용 데이터로 만든다.

    화면은 HTML rowspan으로 제품명/제조번호/유통기한/총 출고수량/최종재고를 병합 표시한다.
    엑셀 다운로드용 데이터는 같은 값을 첫 행에만 남겨 캡처와 비슷하게 보이도록 만든다.
    """
    html_rows = []
    excel_rows = []
    columns = ["제품명", "제조번호", "유통기한", "매출처", "수량", "총 출고수량", "최종재고"]
    if items.empty:
        empty = pd.DataFrame(columns=columns)
        return empty, empty

    work = items.copy()
    work["매출처"] = work["매출처"].fillna("").astype(str).replace("", "-")
    work["표준제품명"] = work["표준제품명"].fillna("-").astype(str)
    work["제조번호"] = work["제조번호"].fillna("-").astype(str).replace("", "-")
    work["유통기한"] = work["유통기한"].fillna("-").astype(str).replace("", "-")
    work["출고수량"] = pd.to_numeric(work["출고수량"], errors="coerce").fillna(0).astype(int)
    work["현재수량"] = pd.to_numeric(work["현재수량"], errors="coerce").fillna(0).astype(int)

    product_groups = []
    for product, product_df in work.groupby("표준제품명", sort=True):
        lot_groups = []
        product_rowspan = 0
        for lot, lot_df in product_df.groupby("제조번호", sort=True):
            exp_groups = []
            lot_rowspan = 0
            for exp, exp_df in lot_df.groupby("유통기한", sort=True):
                customer_qty = (
                    exp_df.groupby("매출처", as_index=False)["출고수량"]
                    .sum()
                    .sort_values(["매출처"])
                    .reset_index(drop=True)
                )
                row_count = max(1, len(customer_qty))
                total_qty = int(customer_qty["출고수량"].sum()) if not customer_qty.empty else 0
                if "재고ID" in exp_df.columns and exp_df["재고ID"].notna().any():
                    stock_base = exp_df.drop_duplicates(subset=["재고ID"])["현재수량"]
                else:
                    stock_base = exp_df["현재수량"]
                final_stock = int(pd.to_numeric(stock_base, errors="coerce").fillna(0).sum())
                exp_groups.append({
                    "exp": exp,
                    "rows": customer_qty,
                    "rowspan": row_count,
                    "total_qty": total_qty,
                    "final_stock": final_stock,
                })
                lot_rowspan += row_count
            lot_groups.append({"lot": lot, "rowspan": lot_rowspan, "exp_groups": exp_groups})
            product_rowspan += lot_rowspan
        product_groups.append({"product": product, "rowspan": product_rowspan, "lot_groups": lot_groups})

    for product_group in product_groups:
        product_written = False
        for lot_group in product_group["lot_groups"]:
            lot_written = False
            for exp_group in lot_group["exp_groups"]:
                exp_written = False
                rows_df = exp_group["rows"]
                if rows_df.empty:
                    rows_iter = [{"매출처": "-", "출고수량": 0}]
                else:
                    rows_iter = rows_df.to_dict("records")
                for r in rows_iter:
                    row = {
                        "제품명": product_group["product"] if not product_written else "",
                        "제품명_rowspan": product_group["rowspan"] if not product_written else 0,
                        "제조번호": lot_group["lot"] if not lot_written else "",
                        "제조번호_rowspan": lot_group["rowspan"] if not lot_written else 0,
                        "유통기한": exp_group["exp"] if not exp_written else "",
                        "유통기한_rowspan": exp_group["rowspan"] if not exp_written else 0,
                        "매출처": str(r.get("매출처", "") or "-"),
                        "수량": int(r.get("출고수량", 0) or 0),
                        "총 출고수량": exp_group["total_qty"] if not exp_written else "",
                        "총 출고수량_rowspan": exp_group["rowspan"] if not exp_written else 0,
                        "최종재고": exp_group["final_stock"] if not exp_written else "",
                        "최종재고_rowspan": exp_group["rowspan"] if not exp_written else 0,
                    }
                    html_rows.append(row)
                    excel_rows.append({c: row[c] for c in columns})
                    product_written = True
                    lot_written = True
                    exp_written = True

    return pd.DataFrame(html_rows), pd.DataFrame(excel_rows, columns=columns)


def _render_daily_outbound_check_html(display_df: pd.DataFrame):
    if display_df.empty:
        st.info("표시할 출고 체크 데이터가 없습니다.")
        return

    def td(value, *, rowspan=0, align="center"):
        rs = f' rowspan="{int(rowspan)}"' if int(rowspan or 0) > 1 else ""
        text = escape(str(value if value is not None else ""))
        return f'<td{rs} style="text-align:{align};vertical-align:middle;">{text}</td>'

    trs = []
    for row in display_df.to_dict("records"):
        cells = []
        if int(row.get("제품명_rowspan", 0) or 0) > 0:
            cells.append(td(row.get("제품명", ""), rowspan=row.get("제품명_rowspan"), align="left"))
        if int(row.get("제조번호_rowspan", 0) or 0) > 0:
            cells.append(td(row.get("제조번호", ""), rowspan=row.get("제조번호_rowspan")))
        if int(row.get("유통기한_rowspan", 0) or 0) > 0:
            cells.append(td(row.get("유통기한", ""), rowspan=row.get("유통기한_rowspan")))
        cells.append(td(row.get("매출처", ""), align="left"))
        cells.append(td(row.get("수량", "")))
        if int(row.get("총 출고수량_rowspan", 0) or 0) > 0:
            cells.append(td(row.get("총 출고수량", ""), rowspan=row.get("총 출고수량_rowspan")))
        if int(row.get("최종재고_rowspan", 0) or 0) > 0:
            cells.append(td(row.get("최종재고", ""), rowspan=row.get("최종재고_rowspan")))
        trs.append("<tr>" + "".join(cells) + "</tr>")

    html = """
<style>
.nohtus-close-table-wrap{width:100%;overflow-x:auto;margin-top:8px;}
.nohtus-close-table{border-collapse:collapse;width:100%;background:white;font-size:14px;table-layout:fixed;}
.nohtus-close-table th{background:#f1f5f9;border:1px solid #94a3b8;padding:8px 6px;text-align:center;font-weight:800;color:#0f172a;white-space:nowrap;}
.nohtus-close-table td{border:1px solid #94a3b8;padding:7px 6px;color:#111827;line-height:1.35;word-break:keep-all;}
.nohtus-close-table th:nth-child(1){width:20%;}
.nohtus-close-table th:nth-child(2){width:13%;}
.nohtus-close-table th:nth-child(3){width:13%;}
.nohtus-close-table th:nth-child(4){width:24%;}
.nohtus-close-table th:nth-child(5){width:8%;}
.nohtus-close-table th:nth-child(6){width:11%;}
.nohtus-close-table th:nth-child(7){width:11%;}
</style>
<div class="nohtus-close-table-wrap">
<table class="nohtus-close-table">
<thead><tr><th>제품명</th><th>제조번호</th><th>유통기한</th><th>매출처</th><th>수량</th><th>총 출고수량</th><th>최종재고</th></tr></thead>
<tbody>
""" + "\n".join(trs) + """
</tbody></table></div>
"""
    st.markdown(html, unsafe_allow_html=True)


def page_closing():
    st.title("마감")
    st.caption("출고의 마지막 단계입니다. 오늘 출고 체크, ERP 재고 비교, 업무일지 작성 기능을 한 화면에서 전환합니다.")
    tab = st.radio("마감", ["오늘 출고 체크", "ERP 재고 비교", "업무일지 작성"], horizontal=True, key="closing_sub")

    if tab == "ERP 재고 비교":
        page_erp_stock_compare()
        return

    target_date = st.date_input("기준일", value=date.today(), key="closing_date")
    ds = str(target_date)

    if tab == "오늘 출고 체크":
        items = q("""SELECT o.id AS 지시서번호,
                            COALESCE(o.title, '') AS 출고지시서제목,
                            i.inventory_id AS 재고ID,
                            i.company AS 사업장,
                            i.location AS 로케이션,
                            i.product_name AS 표준제품명,
                            COALESCE(i.lot, '-') AS 제조번호,
                            COALESCE(i.exp_date, '-') AS 유통기한,
                            i.qty AS 출고수량,
                            COALESCE(inv.qty, 0) AS 현재수량
                     FROM outbound_orders o
                     JOIN outbound_order_items i ON o.id=i.order_id
                     LEFT JOIN inventory inv ON i.inventory_id=inv.id
                     WHERE o.order_date=? AND IFNULL(o.status,'')<>'취소됨'
                     ORDER BY i.product_name, i.lot, i.exp_date, o.id, i.company, i.location""", (ds,))
        if items.empty:
            st.info("해당 날짜의 출고지시가 없습니다.")
        else:
            items["유통기한"] = items["유통기한"].apply(display_date_only)
            items["출고수량"] = pd.to_numeric(items["출고수량"], errors="coerce").fillna(0).astype(int)
            items["현재수량"] = pd.to_numeric(items["현재수량"], errors="coerce").fillna(0).astype(int)
            try:
                customers_for_close = q("SELECT customer_name, manager FROM customers ORDER BY LENGTH(customer_name) DESC")
                items["매출처"] = items["출고지시서제목"].apply(lambda x: _infer_customer_from_title(x, customers_for_close)[0])
            except Exception:
                items["매출처"] = ""

            display_df, excel_df = _daily_outbound_check_rows(items)
            _render_daily_outbound_check_html(display_df)
            st.download_button(
                "마감 체크리스트 엑셀 다운로드",
                data=dataframe_to_excel_bytes(excel_df, "마감체크"),
                file_name=f"NOHTUS_마감체크_{ds}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
    else:
        st.markdown("### 출고")
        out_raw = q("""SELECT o.id AS 지시서번호, COALESCE(o.title, '') AS 출고지시서제목,
                              i.product_name AS 표준제품명, i.qty AS 수량
                       FROM outbound_orders o
                       JOIN outbound_order_items i ON o.id=i.order_id
                       WHERE o.order_date=? AND IFNULL(o.status,'')<>'취소됨'
                       ORDER BY o.id, i.id""", (ds,))
        if out_raw.empty: st.info("출고 업무일지 데이터가 없습니다.")
        else:
            customers_for_worklog = q("SELECT customer_name, manager FROM customers ORDER BY LENGTH(customer_name) DESC")
            out_raw[["출고처", "담당자"]] = out_raw["출고지시서제목"].apply(
                lambda x: pd.Series(_infer_customer_from_title(x, customers_for_worklog))
            )
            out = (out_raw.assign(내역=out_raw["표준제품명"].astype(str) + " * " + out_raw["수량"].astype(int).astype(str))
                         .groupby(["출고처", "담당자"], as_index=False)["내역"]
                         .agg(lambda x: ", ".join(x)))
            tsv = out.to_csv(sep='\t', index=False, header=False)
            st.text_area("드래그해서 복사", value=tsv, height=140, key="worklog_out_tsv")

        st.markdown("### 입고")
        inbound_raw = q("""SELECT COALESCE(t.memo,'') AS 메모,
                                 COALESCE(t.to_location, '') AS 적치위치,
                                 t.product_name AS 표준제품명,
                                 COALESCE(t.lot, '-') AS 제조번호,
                                 COALESCE(t.exp_date, '-') AS 유통기한,
                                 t.qty AS 수량
                          FROM transactions t
                          WHERE t.tx_type='입고' AND substr(t.created_at,1,10)=? ORDER BY t.id""", (ds,))
        if inbound_raw.empty: st.info("입고 업무일지 데이터가 없습니다.")
        else:
            inbound_raw["매입처"] = inbound_raw["메모"].apply(_extract_inbound_source_from_memo)
            inbound_raw["적치위치"] = inbound_raw["적치위치"].astype(str).replace("", "-")
            inbound_raw["제조번호"] = inbound_raw["제조번호"].astype(str).replace("", "-")
            inbound_raw["유통기한"] = inbound_raw["유통기한"].apply(display_date_only)
            inbound_raw["수량"] = pd.to_numeric(inbound_raw["수량"], errors="coerce").fillna(0).astype(int)
            inbound_raw["내역"] = inbound_raw["표준제품명"].astype(str) + " * " + inbound_raw["수량"].astype(str)
            inbound = inbound_raw[["매입처", "적치위치", "내역", "제조번호", "유통기한"]]
            tsv = inbound.to_csv(sep='\t', index=False, header=False)
            st.text_area("드래그해서 복사", value=tsv, height=140, key="worklog_in_tsv")

        st.markdown("### 이동")
        moves = q("""SELECT product_name || '*' || qty AS 이동내역, COALESCE(from_location,'') || ' → ' || COALESCE(to_location,'') AS 이동위치
                     FROM transactions WHERE tx_type='이동' AND substr(created_at,1,10)=? ORDER BY id""", (ds,))
        if moves.empty: st.info("이동 업무일지 데이터가 없습니다.")
        else:
            tsv = moves.to_csv(sep='\t', index=False, header=False)
            st.text_area("드래그해서 복사", value=tsv, height=120, key="worklog_move_tsv")
