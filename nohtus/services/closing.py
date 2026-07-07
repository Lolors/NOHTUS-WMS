"""Service helpers."""
from __future__ import annotations

from datetime import date
from io import BytesIO
import re

import pandas as pd
import streamlit as st

from nohtus.db import q


ERP_COMPARE_COMPANIES = ("노투스팜", "NOH", "노투스")
ERP_COMPARE_COLUMNS = {
    "노투스팜": {"header": 0, "name": "제품명", "qty": "현재고수량"},
    "NOH": {"header": 0, "name": "제품명", "qty": "현재고수량"},
    "노투스": {"header": 7, "name": "품목명/규격", "qty": "현재재고"},
}
ERP_MAPPING_COLUMNS = {
    "노투스팜": "erp_nohtuspharm_name",
    "NOH": "erp_noh_name",
    "노투스": "erp_nohtus_name",
}


def _infer_customer_from_title(title, customers_df=None):
    """출고지시서 제목에서 거래처명을 추정한다.
    제목 규칙: [출고처] [첫 제품명] 외 x품목.
    거래처 관리에 등록된 이름 중 title 시작과 일치하는 가장 긴 이름을 우선 사용한다.
    """
    title = str(title or "").strip()
    if not title:
        return ("", "")
    if customers_df is None:
        customers_df = q("SELECT customer_name, manager FROM customers ORDER BY LENGTH(customer_name) DESC")
    if not customers_df.empty:
        for r in customers_df.itertuples():
            name = str(getattr(r, "customer_name", "") or "").strip()
            if name and title.startswith(name):
                return (name, str(getattr(r, "manager", "") or ""))
    return (title.split()[0] if title.split() else title, "")


def _extract_inbound_source_from_memo(memo):
    """입고 이력 memo에서 입고처만 추출한다.
    저장 형식 예: '매입처: 거래처명 / 기타메모'
    """
    text = str(memo or "").strip()
    if not text or text == "입고 등록":
        return ""
    prefixes = ["매입처:", "입고처:"]
    for prefix in prefixes:
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
            if " / " in text:
                text = text.split(" / ", 1)[0].strip()
            break
    return text


def dataframe_to_excel_bytes(df, sheet_name="Sheet1"):
    """DataFrame을 엑셀 bytes로 변환한다.
    openpyxl이 허용하지 않는 제어문자/특수 공백은 저장 전에 전부 제거한다.
    """
    bio = BytesIO()
    safe_df = df.copy() if df is not None else pd.DataFrame()
    safe_sheet = clean_excel_text(sheet_name)[:31] or "Sheet1"
    safe_df.columns = [clean_excel_text(c) for c in safe_df.columns]
    for col in safe_df.columns:
        if safe_df[col].dtype == object:
            safe_df[col] = safe_df[col].apply(lambda v: clean_excel_text(v) if v is not None else "")
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        safe_df.to_excel(writer, index=False, sheet_name=safe_sheet)
        ws = writer.book[safe_sheet]
        from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
        thin = Side(style="thin", color="000000")
        border = Border(left=thin, right=thin, top=thin, bottom=thin)
        header_fill = PatternFill("solid", fgColor="E5E7EB")
        for col in ws.columns:
            max_len = 10
            letter = col[0].column_letter
            for cell in col:
                cell.border = border
                cell.alignment = Alignment(vertical="center", wrap_text=True)
                if cell.row == 1:
                    cell.font = Font(bold=True)
                    cell.fill = header_fill
                max_len = max(max_len, len(str(cell.value or "")) + 2)
            ws.column_dimensions[letter].width = min(max_len, 42)
        if safe_sheet == "마감체크":
            ws.column_dimensions["C"].width = 14
            ws.column_dimensions["D"].width = 50
            current_fill = PatternFill("solid", fgColor="DDEBF7")
            header_map = {str(ws.cell(row=1, column=i).value or "").strip(): i for i in range(1, ws.max_column + 1)}
            cur_col = header_map.get("현재수량")
            if cur_col:
                for rr in range(1, ws.max_row + 1):
                    ws.cell(row=rr, column=cur_col).fill = current_fill
        ws.freeze_panes = "A2"
        if safe_df.shape[1] > 0:
            ws.auto_filter.ref = ws.dimensions
    bio.seek(0)
    return bio.getvalue()


def page_erp_stock_compare():
    st.title("ERP 재고 비교")
    st.caption("WMS 재고와 ERP 현재고를 사업장별 ERP 제품명 기준으로 비교합니다. 제조번호와 유통기한은 무시하고 총수량만 비교하며, 비자료는 제외합니다.")

    uploaded_files = {}
    cols = st.columns(3, gap="large")
    for col, company in zip(cols, ERP_COMPARE_COMPANIES):
        spec = ERP_COMPARE_COLUMNS[company]
        with col:
            st.markdown(f"### {company}")
            if company == "노투스":
                st.caption(f"8행 헤더 · 제품명: {spec['name']} · 수량: {spec['qty']}")
            else:
                st.caption(f"제품명: {spec['name']} · 수량: {spec['qty']}")
            uploaded_files[company] = st.file_uploader(
                f"{company} ERP 현재고 엑셀",
                type=["xlsx", "xls"],
                key=f"erp_compare_upload_{company}",
            )

    if not any(uploaded_files.values()):
        st.info("노투스팜 / NOH / 노투스 ERP 현재고 엑셀을 업로드하세요.")
        return

    _, run_col, _ = st.columns([3, 2, 3], gap="large")
    with run_col:
        run_compare = st.button("ERP 재고 비교 실행", type="primary", use_container_width=True)

    if run_compare:
        erp_sum, erp_source_rows = read_and_sum_erp_current_stock(uploaded_files)
        wms_sum = load_wms_stock_by_erp_name()
        result = compare_erp_and_wms_stock(erp_sum, wms_sum)

        st.session_state["erp_compare_result"] = result.to_dict("records")
        st.session_state["erp_compare_summary"] = {
            "erp_source_rows": erp_source_rows,
            "erp_products": len(erp_sum),
            "wms_products": len(wms_sum),
            "diff_products": int((result["차이"] != 0).sum()) if not result.empty else 0,
        }

    if "erp_compare_summary" not in st.session_state:
        return

    summary = st.session_state["erp_compare_summary"]
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("ERP 원본 행", f"{summary['erp_source_rows']:,}건")
    m2.metric("ERP 제품 합산", f"{summary['erp_products']:,}건")
    m3.metric("WMS 제품 합산", f"{summary['wms_products']:,}건")
    m4.metric("차이 항목", f"{summary['diff_products']:,}건")

    result = pd.DataFrame(st.session_state.get("erp_compare_result", []))
    if result.empty:
        st.info("비교할 재고가 없습니다.")
        return

    st.markdown("### 재고 비교 결과")
    only_diff = st.checkbox("차이 있는 항목만 보기", value=True, key="erp_compare_only_diff")
    shown = result[result["차이"] != 0] if only_diff else result
    st.dataframe(shown, use_container_width=True, hide_index=True)
    st.download_button(
        "비교 결과 엑셀 다운로드",
        data=dataframe_to_excel_bytes(result, "ERP_WMS_비교"),
        file_name=f"NOHTUS_ERP_WMS_비교_{date.today().strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )


def read_and_sum_erp_current_stock(uploaded_files):
    """업로드된 ERP 현재고 파일을 사업장 + ERP제품명 기준으로 합산한다."""
    rows = []
    source_rows = 0
    for company, uploaded in uploaded_files.items():
        if uploaded is None:
            continue
        raw = read_erp_current_stock_file(uploaded, company)
        if raw is None or raw.empty:
            continue
        source_rows += len(raw)
        rows.append(raw)

    if not rows:
        return pd.DataFrame(columns=["사업장", "ERP제품명", "ERP수량"]), 0

    erp = pd.concat(rows, ignore_index=True)
    erp = erp.groupby(["사업장", "ERP제품명"], as_index=False)["ERP수량"].sum()
    return erp.sort_values(["사업장", "ERP제품명"]), source_rows


def read_erp_current_stock_file(uploaded, company):
    """ERP 현재고 엑셀 1개를 읽어 비교용 컬럼만 반환한다."""
    spec = ERP_COMPARE_COLUMNS[company]
    try:
        df = pd.read_excel(uploaded, header=spec["header"])
    except Exception as e:
        st.error(f"{company} 엑셀 읽기 실패: {e}")
        return None

    if df.empty:
        st.warning(f"{company} 엑셀에 데이터가 없습니다.")
        return None

    df.columns = [clean_excel_text(c) for c in df.columns]
    name_col = spec["name"]
    qty_col = spec["qty"]
    if name_col not in df.columns or qty_col not in df.columns:
        st.error(f"{company} ERP 파일에서 필요한 컬럼을 찾을 수 없습니다.")
        st.caption("노투스팜/NOH: 제품명, 현재고수량 · 노투스: 8행 헤더의 품목명/규격, 현재재고")
        return None

    out = pd.DataFrame({
        "사업장": company,
        "ERP제품명": df[name_col].apply(clean_excel_text),
        "ERP수량": pd.to_numeric(df[qty_col], errors="coerce").fillna(0).astype(int),
    })
    out = out[~out["ERP제품명"].apply(is_ignored_erp_product_name)]
    out = out[out["ERP수량"] != 0]
    return out


def load_wms_stock_by_erp_name():
    """WMS inventory 재고를 사업장별 ERP제품명 기준으로 합산한다."""
    sql = """
        SELECT
            i.company AS 사업장,
            COALESCE(NULLIF(TRIM(
                CASE i.company
                    WHEN '노투스팜' THEN p.erp_nohtuspharm_name
                    WHEN 'NOH' THEN p.erp_noh_name
                    WHEN '노투스' THEN p.erp_nohtus_name
                    ELSE ''
                END
            ), ''), i.product_name) AS ERP제품명,
            SUM(i.qty) AS WMS수량
        FROM inventory i
        LEFT JOIN products p
          ON p.standard_name = i.product_name
        WHERE i.qty <> 0
          AND i.company IN ('노투스팜', 'NOH', '노투스')
        GROUP BY i.company, ERP제품명
    """
    wms = q(sql)
    if wms.empty:
        return pd.DataFrame(columns=["사업장", "ERP제품명", "WMS수량"])

    wms["ERP제품명"] = wms["ERP제품명"].apply(clean_excel_text)
    wms["WMS수량"] = pd.to_numeric(wms["WMS수량"], errors="coerce").fillna(0).astype(int)
    wms = wms[~wms["ERP제품명"].apply(is_ignored_erp_product_name)]
    wms = wms[wms["WMS수량"] != 0]
    return wms.groupby(["사업장", "ERP제품명"], as_index=False)["WMS수량"].sum().sort_values(["사업장", "ERP제품명"])


def compare_erp_and_wms_stock(erp_sum, wms_sum):
    """사업장 + ERP제품명이 같은 행끼리 ERP수량과 WMS수량을 비교한다."""
    result = pd.merge(erp_sum, wms_sum, how="outer", on=["사업장", "ERP제품명"])
    if result.empty:
        return pd.DataFrame(columns=["사업장", "ERP제품명", "ERP수량", "WMS수량", "차이"])

    result["ERP수량"] = pd.to_numeric(result["ERP수량"], errors="coerce").fillna(0).astype(int)
    result["WMS수량"] = pd.to_numeric(result["WMS수량"], errors="coerce").fillna(0).astype(int)
    result["차이"] = result["WMS수량"] - result["ERP수량"]
    return result[["사업장", "ERP제품명", "ERP수량", "WMS수량", "차이"]].sort_values(["사업장", "ERP제품명"])


def clean_excel_text(value):
    """openpyxl이 저장하지 못하는 제어문자와 특수 공백을 제거한다."""
    if value is None:
        return ""
    text = str(value)
    try:
        from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
        text = ILLEGAL_CHARACTERS_RE.sub("", text)
    except Exception:
        text = re.sub("[\\x00-\\x08\\x0B-\\x0C\\x0E-\\x1F]", "", text)
    text = re.sub("[\\x00-\\x1F\\x7F-\\x9F\\u200b\\u200c\\u200d\\ufeff]", "", text)
    text = text.replace("\xa0", " ")
    return text.strip()


def is_ignored_erp_product_name(value):
    key = re.sub(r"\s+", "", clean_excel_text(value)).replace("[", "").replace("]", "")
    return not key or key in {"합계", "배송비"} or "합계" in key or "배송비" in key
