from datetime import date

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


def _daily_outbound_check_rows(items: pd.DataFrame) -> pd.DataFrame:
    """오늘 출고 체크 표를 고객별 행 + 제품별 합계 표시 형태로 만든다."""
    rows = []
    if items.empty:
        return pd.DataFrame(columns=["매출처", "제품명", "제조번호", "유통기한", "수량", "총 출고수량", "최종재고"])

    work = items.copy()
    work["매출처"] = work["매출처"].fillna("").astype(str).replace("", "-")
    work["표준제품명"] = work["표준제품명"].fillna("-").astype(str)
    work["제조번호"] = work["제조번호"].fillna("-").astype(str).replace("", "-")
    work["유통기한"] = work["유통기한"].fillna("-").astype(str).replace("", "-")
    work["출고수량"] = pd.to_numeric(work["출고수량"], errors="coerce").fillna(0).astype(int)
    work["현재수량"] = pd.to_numeric(work["현재수량"], errors="coerce").fillna(0).astype(int)

    for (product, lot, exp), g in work.groupby(["표준제품명", "제조번호", "유통기한"], sort=True):
        customer_qty = (
            g.groupby("매출처", as_index=False)["출고수량"]
            .sum()
            .sort_values(["매출처"])
            .reset_index(drop=True)
        )
        total_qty = int(customer_qty["출고수량"].sum())
        if "재고ID" in g.columns:
            stock_base = g.drop_duplicates(subset=["재고ID"])["현재수량"] if g["재고ID"].notna().any() else g["현재수량"]
        else:
            stock_base = g["현재수량"]
        final_stock = int(pd.to_numeric(stock_base, errors="coerce").fillna(0).sum())

        for idx, r in customer_qty.iterrows():
            rows.append({
                "매출처": r["매출처"],
                "제품명": product,
                "제조번호": lot,
                "유통기한": exp,
                "수량": int(r["출고수량"] or 0),
                "총 출고수량": total_qty if idx == 0 else "",
                "최종재고": final_stock if idx == 0 else "",
            })
    return pd.DataFrame(rows, columns=["매출처", "제품명", "제조번호", "유통기한", "수량", "총 출고수량", "최종재고"])


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

            checklist = _daily_outbound_check_rows(items)
            st.dataframe(
                checklist,
                hide_index=True,
                use_container_width=True,
                column_config={
                    "매출처": st.column_config.TextColumn(width="medium"),
                    "제품명": st.column_config.TextColumn(width="large"),
                    "제조번호": st.column_config.TextColumn(width="medium"),
                    "유통기한": st.column_config.TextColumn(width="small"),
                    "수량": st.column_config.NumberColumn(width="small"),
                    "총 출고수량": st.column_config.TextColumn(width="small"),
                    "최종재고": st.column_config.TextColumn(width="small"),
                },
            )
            st.download_button(
                "마감 체크리스트 엑셀 다운로드",
                data=dataframe_to_excel_bytes(checklist, "마감체크"),
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
