import pandas as pd
import streamlit as st

from nohtus.dates import display_date_only
from nohtus.db import connect, q


_SHIPPABLE_COL = "is_shippable"


def _ensure_inventory_shippable_column():
    with connect() as con:
        cur = con.cursor()
        cols = {r[1] for r in cur.execute("PRAGMA table_info(inventory)").fetchall()}
        if _SHIPPABLE_COL not in cols:
            cur.execute(f"ALTER TABLE inventory ADD COLUMN {_SHIPPABLE_COL} INTEGER NOT NULL DEFAULT 1")
        con.commit()


def _load_inventory(product_term: str, company_filter: str, status_filter: str):
    _ensure_inventory_shippable_column()
    where = ["qty > 0"]
    params = []

    product_term = str(product_term or "").strip()
    if product_term:
        like = f"%{product_term}%"
        where.append("(product_name LIKE ? OR COALESCE(warehouse_name,'') LIKE ? OR COALESCE(lot,'') LIKE ? OR COALESCE(location,'') LIKE ?)")
        params.extend([like, like, like, like])

    company_filter = str(company_filter or "전체").strip()
    if company_filter != "전체":
        where.append("company = ?")
        params.append(company_filter)

    status_filter = str(status_filter or "전체").strip()
    if status_filter == "출고가능":
        where.append("COALESCE(is_shippable, 1) = 1")
    elif status_filter == "출고제외":
        where.append("COALESCE(is_shippable, 1) = 0")

    sql = f"""
        SELECT
            id,
            COALESCE(is_shippable, 1) AS is_shippable,
            company,
            product_name,
            warehouse_name,
            lot,
            exp_date,
            location,
            qty
        FROM inventory
        WHERE {' AND '.join(where)}
        ORDER BY company, product_name, location, lot, exp_date, id
        LIMIT 500
    """
    return q(sql, tuple(params))


def _company_options():
    df = q("SELECT DISTINCT company FROM inventory WHERE TRIM(COALESCE(company,''))<>'' ORDER BY company")
    values = [] if df.empty else df["company"].dropna().astype(str).tolist()
    return ["전체"] + values


def page_shippable_inventory():
    _ensure_inventory_shippable_column()
    st.title("출고가능 관리")
    st.caption("admin 전용 메뉴입니다. 체크를 끄면 해당 재고 행은 재고 조회에는 남지만 출고지시 후보/추천에서는 제외됩니다.")

    c1, c2, c3 = st.columns([2.2, 1, 1], gap="small")
    with c1:
        product_term = st.text_input("검색", placeholder="제품명/ERP명/LOT/로케이션", key="ship_inv_term")
    with c2:
        company_filter = st.selectbox("사업장", _company_options(), key="ship_inv_company")
    with c3:
        status_filter = st.selectbox("상태", ["전체", "출고가능", "출고제외"], key="ship_inv_status")

    stock_df = _load_inventory(product_term, company_filter, status_filter)
    if stock_df.empty:
        st.info("표시할 재고가 없습니다.")
        return

    work = stock_df.copy().reset_index(drop=True)
    work["is_shippable"] = work["is_shippable"].fillna(1).astype(int).astype(bool)
    work["exp_date"] = work["exp_date"].apply(display_date_only)
    work = work.rename(
        columns={
            "id": "ID",
            "is_shippable": "출고가능",
            "company": "사업장",
            "product_name": "표준제품명",
            "warehouse_name": "ERP명",
            "lot": "LOT",
            "exp_date": "유통기한",
            "location": "로케이션",
            "qty": "수량",
        }
    )

    st.caption(f"최대 500행까지 표시합니다. 현재 표시: {len(work)}행")
    edited = st.data_editor(
        work[["ID", "출고가능", "사업장", "로케이션", "표준제품명", "ERP명", "LOT", "유통기한", "수량"]],
        hide_index=True,
        use_container_width=True,
        num_rows="fixed",
        disabled=["ID", "사업장", "로케이션", "표준제품명", "ERP명", "LOT", "유통기한", "수량"],
        column_config={
            "ID": st.column_config.NumberColumn("ID", disabled=True, width="small"),
            "출고가능": st.column_config.CheckboxColumn("출고가능"),
        },
        key="ship_inv_editor",
    )

    b1, b2 = st.columns([1, 3], gap="small")
    with b1:
        save = st.button("출고가능 설정 저장", type="primary", use_container_width=True)
    with b2:
        excluded = int((~work["출고가능"].astype(bool)).sum())
        st.caption(f"현재 화면 기준 출고제외: {excluded}행")

    if not save:
        return

    updates = []
    edited = edited.reset_index(drop=True)
    for pos, row in edited.iterrows():
        try:
            inv_id = int(row.get("ID"))
        except Exception:
            if pos >= len(work):
                continue
            inv_id = int(work.iloc[pos].get("ID"))
        new_value = 1 if bool(row.get("출고가능", True)) else 0
        old_value = 1 if pos >= len(work) else (1 if bool(work.iloc[pos].get("출고가능", True)) else 0)
        if new_value != old_value:
            updates.append((new_value, inv_id))

    if not updates:
        st.info("변경된 출고가능 설정이 없습니다.")
        return

    with connect() as con:
        con.executemany("UPDATE inventory SET is_shippable=? WHERE id=?", updates)
        con.commit()
    st.success(f"출고가능 설정을 {len(updates)}개 행에 반영했습니다.")
    st.rerun()
