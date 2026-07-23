from datetime import date, datetime

import pandas as pd
import streamlit as st

from nohtus.db import connect, q
from nohtus.services.master import customer_export_excel_bytes, import_customer_master_excel


def _normalize_customer_name(value):
    return str(value or "").strip()


def _ensure_customer_last_sales_table():
    with connect() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS customer_last_sales(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_name TEXT NOT NULL,
                company TEXT NOT NULL DEFAULT '',
                last_sale_date TEXT NOT NULL,
                source_company TEXT,
                updated_at TEXT,
                UNIQUE(customer_name, company)
            )
            """
        )
        con.commit()


def _parse_sales_excel(uploaded_file, *, company, header_row, date_col, customer_col):
    """매출 엑셀에서 거래처별 최근 거래일을 추출한다."""
    if uploaded_file is None:
        return pd.DataFrame(columns=["customer_name", "company", "last_sale_date"])

    df = pd.read_excel(uploaded_file, header=header_row, dtype=object)
    df.columns = [str(c).strip() for c in df.columns]
    if date_col not in df.columns or customer_col not in df.columns:
        raise ValueError(
            f"{company} 매출 파일에서 '{date_col}', '{customer_col}' 컬럼을 찾을 수 없습니다. "
            f"현재 컬럼: {', '.join(df.columns)}"
        )

    work = df[[date_col, customer_col]].copy()
    work[customer_col] = work[customer_col].apply(_normalize_customer_name)
    work = work[work[customer_col] != ""]
    work[date_col] = pd.to_datetime(work[date_col], errors="coerce")
    work = work.dropna(subset=[date_col])
    if work.empty:
        return pd.DataFrame(columns=["customer_name", "company", "last_sale_date"])

    result = (
        work.groupby(customer_col, as_index=False)[date_col]
        .max()
        .rename(columns={customer_col: "customer_name", date_col: "last_sale_date"})
    )
    result["company"] = company
    result["last_sale_date"] = result["last_sale_date"].dt.strftime("%Y-%m-%d")
    return result[["customer_name", "company", "last_sale_date"]]


def _upsert_customer_last_sales(rows_df):
    _ensure_customer_last_sales_table()
    if rows_df is None or rows_df.empty:
        return 0

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    count = 0
    with connect() as con:
        cur = con.cursor()
        for row in rows_df.itertuples(index=False):
            customer_name = _normalize_customer_name(getattr(row, "customer_name", ""))
            company = str(getattr(row, "company", "") or "").strip()
            last_sale_date = str(getattr(row, "last_sale_date", "") or "").strip()
            if not customer_name or not last_sale_date:
                continue

            old = cur.execute(
                "SELECT id, last_sale_date FROM customer_last_sales WHERE customer_name=? AND company=?",
                (customer_name, company),
            ).fetchone()
            if old:
                old_date = str(old[1] or "")
                final_date = max(old_date, last_sale_date) if old_date else last_sale_date
                cur.execute(
                    """
                    UPDATE customer_last_sales
                    SET last_sale_date=?, source_company=?, updated_at=?
                    WHERE id=?
                    """,
                    (final_date, company, now, int(old[0])),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO customer_last_sales(
                        customer_name, company, last_sale_date, source_company, updated_at
                    ) VALUES(?,?,?,?,?)
                    """,
                    (customer_name, company, last_sale_date, company, now),
                )
            count += 1
        con.commit()
    return count


def _render_three_company_last_sale_importer():
    st.markdown("#### 최근거래일 갱신")
    st.caption("노투스팜은 매출일자, NOH는 명세서일자, 노투스는 8행 거래일자 기준으로 거래처별 마지막 거래일만 저장합니다.")
    u1, u2, u3 = st.columns(3, gap="small")
    with u1:
        np_file = st.file_uploader("노투스팜 매출 파일", type=["xls", "xlsx"], key="last_sale_np_file")
    with u2:
        noh_file = st.file_uploader("NOH 매출 파일", type=["xls", "xlsx"], key="last_sale_noh_file")
    with u3:
        nt_file = st.file_uploader("노투스 매출 파일", type=["xls", "xlsx"], key="last_sale_nt_file")

    if st.button("최근거래일 갱신", use_container_width=True, key="last_sale_import_btn"):
        try:
            frames = []
            if np_file is not None:
                frames.append(_parse_sales_excel(np_file, company="노투스팜", header_row=0, date_col="매출일자", customer_col="거래처명"))
            if noh_file is not None:
                frames.append(_parse_sales_excel(noh_file, company="NOH", header_row=0, date_col="명세서일자", customer_col="거래처명"))
            if nt_file is not None:
                frames.append(_parse_sales_excel(nt_file, company="노투스", header_row=7, date_col="거래일자", customer_col="거래처명"))
            if not frames:
                st.warning("갱신할 매출 파일을 업로드하세요.")
            else:
                merged = pd.concat(frames, ignore_index=True)
                count = _upsert_customer_last_sales(merged)
                st.success(f"최근거래일 갱신 완료: {count}개 거래처 반영")
                st.rerun()
        except Exception as e:
            st.error(str(e))


def page_customer_master():
    st.title("거래처 관리")
    st.caption("거래처 엑셀을 업로드하면 출고지시와 업무일지에서 매출처/담당자 정보를 재사용할 수 있습니다.")

    c1, c2, c3 = st.columns([1.5, 2, 6.5], gap="large")
    with c1:
        st.download_button(
            "등록된 거래처 내려받기",
            data=customer_export_excel_bytes(),
            file_name=f"NOHTUS_등록거래처_{date.today().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
    with c2:
        up = st.file_uploader("거래처 관리 엑셀 업로드", type=["xlsx"], key="customer_master_upload")
        if up is not None and st.button("거래처 관리 업데이트", type="primary", use_container_width=True):
            try:
                updated, inserted, skipped = import_customer_master_excel(up)
                st.success(f"업데이트 완료: 수정 {updated}건 / 추가 {inserted}건 / 건너뜀 {skipped}건")
                st.rerun()
            except Exception as e:
                st.error(f"업로드 실패: {e}")
    with c3:
        _render_three_company_last_sale_importer()

    df = q("SELECT customer_code AS 거래처코드, customer_name AS 거래처명, company AS 사업장, customer_type AS 유형, manager AS 담당자, phone AS 연락처, address AS 주소, memo AS 메모 FROM customers ORDER BY customer_name, company")
    st.markdown("### 등록된 거래처")
    if df.empty:
        st.info("등록된 거래처가 없습니다.")
    else:
        term = st.text_input("거래처 검색", placeholder="거래처명/담당자/주소 일부 입력")
        if term.strip():
            low = term.strip().lower()
            mask = False
            for col in df.columns:
                mask = mask | df[col].fillna("").astype(str).str.lower().str.contains(low, regex=False)
            df = df[mask]
        st.dataframe(df, use_container_width=True, hide_index=True)
