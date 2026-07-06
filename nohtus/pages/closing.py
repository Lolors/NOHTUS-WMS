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


def _today_outbound_final_stock_map(items):
    if items.empty:
        return {}
    keys = items[["표준제품명", "제조번호", "유통기한"]].drop_duplicates()
    result = {}
    for r in keys.itertuples(index=False):
        product = str(getattr(r, "표준제품명") or "")
        lot = str(getattr(r, "제조번호") or "-")
        exp = str(getattr(r, "유통기한") or "-")
        df = q(
            """
            SELECT COALESCE(SUM(qty), 0) AS qty
            FROM inventory
            WHERE product_name=?
              AND COALESCE(lot, '-')=?
              AND COALESCE(exp_date, '-')=?
            """,
            (product, lot, exp),
        )
        result[(product, lot, exp)] = int(df.iloc[0]["qty"] or 0) if not df.empty else 0
    return result


def _today_outbound_display_df(items):
    group_cols = ["표준제품명", "제조번호", "유통기한"]
    final_map = _today_outbound_final_stock_map(items)
    rows = []
    for key, grp in items.groupby(group_cols, sort=False, dropna=False):
        product, lot, exp = key
        total_qty = int(grp["출고수량"].sum())
        final_qty = final_map.get((product, lot, exp), 0)
        for i, rr in enumerate(grp.itertuples(index=False)):
            rows.append({
                "제품명": product if i == 0 else "",
                "제조번호": lot if i == 0 else "",
                "유통기한": exp if i == 0 else "",
                "매출처": getattr(rr, "매출처", ""),
                "수량": int(getattr(rr, "출고수량", 0) or 0),
                "총 출고수량": total_qty if i == 0 else "",
                "최종재고": final_qty if i == 0 else "",
            })
    return pd.DataFrame(rows, columns=["제품명", "제조번호", "유통기한", "매출처", "수량", "총 출고수량", "최종재고"])


def _render_today_outbound_html(items):
    group_cols = ["표준제품명", "제조번호", "유통기한"]
    final_map = _today_outbound_final_stock_map(items)
    html = [
        "<style>",
        ".today-out-table{width:100%;border-collapse:collapse;background:white;border:1px solid #e5e7eb;font-size:14px;}",
        ".today-out-table th{background:#f1f5f9;color:#111827;font-weight:800;border:1px solid #e5e7eb;padding:8px;text-align:center;}",
        ".today-out-table td{border:1px solid #e5e7eb;padding:8px;vertical-align:middle;color:#111827;}",
        ".today-out-table td.num{text-align:right;font-weight:700;}",
        "</style>",
        "<table class='today-out-table'>",
        "<thead><tr><th>제품명</th><th>제조번호</th><th>유통기한</th><th>매출처</th><th>수량</th><th>총 출고수량</th><th>최종재고</th></tr></thead><tbody>",
    ]
    for key, grp in items.groupby(group_cols, sort=False, dropna=False):
        product, lot, exp = key
        total_qty = int(grp["출고수량"].sum())
        final_qty = final_map.get((product, lot, exp), 0)
        rowspan = len(grp)
        for i, rr in enumerate(grp.itertuples(index=False)):
            html.append("<tr>")
            if i == 0:
                html.append(f"<td rowspan='{rowspan}'>{escape(str(product))}</td>")
                html.append(f"<td rowspan='{rowspan}'>{escape(str(lot))}</td>")
                html.append(f"<td rowspan='{rowspan}'>{escape(str(exp))}</td>")
            html.append(f"<td>{escape(str(getattr(rr, '매출처', '') or '-'))}</td>")
            html.append(f"<td class='num'>{int(getattr(rr, '출고수량', 0) or 0):,}</td>")
            if i == 0:
                html.append(f"<td class='num' rowspan='{rowspan}'>{total_qty:,}</td>")
                html.append(f"<td class='num' rowspan='{rowspan}'>{final_qty:,}</td>")
            html.append("</tr>")
    html.append("</tbody></table>")
    st.markdown("".join(html), unsafe_allow_html=True)


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
        items = q("""SELECT COALESCE(o.title, '') AS 출고지시서제목,
                            i.inventory_id AS 재고ID,
                            i.product_name AS 표준제품명,
                            COALESCE(i.lot, '-') AS 제조번호,
                            COALESCE(i.exp_date, '-') AS 유통기한,
                            i.qty AS 출고수량
                     FROM outbound_orders o
                     JOIN outbound_order_items i ON o.id=i.order_id
                     WHERE o.order_date=? AND IFNULL(o.status,'')<>'취소됨'
                     ORDER BY i.product_name, i.lot, i.exp_date, o.id, i.id""", (ds,))
        if items.empty:
            st.info("해당 날짜의 출고지시가 없습니다.")
        else:
            items["유통기한"] = items["유통기한"].apply(display_date_only)
            items["출고수량"] = pd.to_numeric(items["출고수량"], errors="coerce").fillna(0).astype(int)
            try:
                customers_for_close = q("SELECT customer_name, manager FROM customers ORDER BY LENGTH(customer_name) DESC")
                items["매출처"] = items["출고지시서제목"].apply(lambda x: _infer_customer_from_title(x, customers_for_close)[0])
            except Exception:
                items["매출처"] = ""
            _render_today_outbound_html(items)
            out_df = _today_outbound_display_df(items)
            st.download_button("마감 체크리스트 엑셀 다운로드", data=dataframe_to_excel_bytes(out_df, "마감체크"), file_name=f"NOHTUS_마감체크_{ds}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
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
