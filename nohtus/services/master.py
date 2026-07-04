"""Service helpers."""

from __future__ import annotations


def match_erp_name(company, erp_name):
    """ERP명칭을 표준제품명으로 변환한다. 1건이면 자동, 여러 후보면 확인 필요."""
    erp_name = (erp_name or "").strip()
    if not erp_name:
        return {"status": "fail", "candidates": [], "message": "ERP명칭이 비어 있습니다."}
    col = get_erp_column(company)
    candidates = []
    if col:
        df = q(f"SELECT standard_name FROM products WHERE TRIM(COALESCE({col}, '')) = ?", (erp_name,))
        candidates.extend(df["standard_name"].dropna().astype(str).tolist())
    cand_df = q("SELECT candidate_product FROM erp_ambiguous_candidates WHERE erp_company=? AND erp_name=? ORDER BY candidate_product", (company, erp_name))
    candidates.extend(cand_df["candidate_product"].dropna().astype(str).tolist())
    candidates = sorted(set([c for c in candidates if c]))
    if len(candidates) == 1:
        return {"status": "auto", "candidates": candidates, "message": f"자동 매칭: {candidates[0]}"}
    if len(candidates) > 1:
        return {"status": "ambiguous", "candidates": candidates, "message": "확인 필요 품목입니다."}
    return {"status": "fail", "candidates": [], "message": "매칭 실패: 제품마스터 또는 확인필요 후보에 등록하세요."}


def customer_export_excel_bytes():
    df = q("SELECT customer_code AS 거래처코드, customer_name AS 거래처명, company AS 사업장, customer_type AS 유형, manager AS 담당자, phone AS 연락처, address AS 주소, memo AS 메모 FROM customers ORDER BY customer_name, company")
    return dataframe_to_excel_bytes(df, "거래처관리")


def import_customer_master_excel(uploaded_file):
    df = pd.read_excel(uploaded_file, dtype=str).fillna("")
    rename = {
        "거래처코드":"customer_code", "코드":"customer_code",
        "거래처명":"customer_name", "거래처":"customer_name", "상호":"customer_name",
        "사업장":"company", "법인":"company",
        "유형":"customer_type", "거래처유형":"customer_type",
        "담당자":"manager", "담당":"manager",
        "연락처":"phone", "전화번호":"phone", "핸드폰":"phone",
        "주소":"address", "납품처":"address", "배송지":"address",
        "메모":"memo", "비고":"memo",
    }
    df = df.rename(columns={c: rename.get(str(c).strip(), c) for c in df.columns})
    if "customer_name" not in df.columns:
        raise ValueError("엑셀에 '거래처명' 컬럼이 필요합니다.")
    for c in ["customer_code", "company", "customer_type", "manager", "phone", "address", "memo"]:
        if c not in df.columns:
            df[c] = ""
    updated = inserted = skipped = 0
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with connect() as con:
        cur = con.cursor()
        for _, r in df.iterrows():
            name = "" if pd.isna(r.get("customer_name")) else str(r.get("customer_name")).strip()
            code = "" if pd.isna(r.get("customer_code")) else str(r.get("customer_code")).strip()
            if not name:
                skipped += 1
                continue
            vals = []
            for c in ["company", "customer_type", "manager", "phone", "address", "memo"]:
                vals.append("" if pd.isna(r.get(c)) else str(r.get(c)).strip())
            company = vals[0]

            # 거래처명만으로 중복 판단하면 같은 매출처가 노투스팜/NOH 등 여러 사업장에
            # 존재할 때 한쪽 행이 다른 행을 덮어쓴다.
            # 따라서 중복 기준은 우선 거래처코드+사업장, 없으면 거래처명+사업장으로 본다.
            existing = None
            if code and company:
                existing = cur.execute("SELECT id FROM customers WHERE customer_code=? AND IFNULL(company,'')=?", (code, company)).fetchone()
            if not existing and code and not company:
                existing = cur.execute("SELECT id FROM customers WHERE customer_code=? AND IFNULL(company,'')=''", (code,)).fetchone()
            if not existing and company:
                existing = cur.execute("SELECT id FROM customers WHERE customer_name=? AND IFNULL(company,'')=?", (name, company)).fetchone()
            if not existing and not company:
                existing = cur.execute("SELECT id FROM customers WHERE customer_name=? AND IFNULL(company,'')=''", (name,)).fetchone()

            if existing:
                cur.execute("UPDATE customers SET customer_code=?, customer_name=?, company=?, customer_type=?, manager=?, phone=?, address=?, memo=?, updated_at=? WHERE id=?", (code, name, vals[0], vals[1], vals[2], vals[3], vals[4], vals[5], now, int(existing[0])))
                updated += 1
            else:
                cur.execute("INSERT INTO customers(customer_code, customer_name, company, customer_type, manager, phone, address, memo, updated_at) VALUES(?,?,?,?,?,?,?,?,?)", (code, name, vals[0], vals[1], vals[2], vals[3], vals[4], vals[5], now))
                inserted += 1
        con.commit()
    return updated, inserted, skipped


def render_inventory_metadata_editor():
    st.markdown("---")
    st.markdown("### 재고정보 수정")
    st.caption("기존 재고 정보 자체가 잘못된 경우 제조번호/유통기한만 정정합니다. 수량은 변경하지 않습니다.")

    term = st.text_input("재고 검색", placeholder="제품명, ERP명, 제조번호, 유통기한, 로케이션 일부 입력", key="inv_meta_edit_term")
    where = "WHERE 1=1"
    params = []
    if term.strip():
        like = f"%{term.strip()}%"
        where += " AND (product_name LIKE ? OR IFNULL(warehouse_name,'') LIKE ? OR IFNULL(lot,'') LIKE ? OR IFNULL(exp_date,'') LIKE ? OR location LIKE ?)"
        params.extend([like, like, like, like, like])
    inv = q(f"""
        SELECT id, company, product_name, warehouse_name, lot, exp_date, location, qty
        FROM inventory
        {where}
        ORDER BY product_name, company, location, lot, exp_date
        LIMIT 300
    """, tuple(params))
    if inv.empty:
        st.info("수정할 재고가 없습니다.")
        return

    labels = []
    for r in inv.itertuples(index=False):
        wh = getattr(r, "warehouse_name") or "-"
        labels.append(
            f"#{int(getattr(r, 'id'))} / {getattr(r, 'company')} / {getattr(r, 'location')} / "
            f"{getattr(r, 'product_name')} / {wh} / LOT:{getattr(r, 'lot') or '-'} / "
            f"EXP:{display_date_only(getattr(r, 'exp_date') or '-')} / {int(getattr(r, 'qty') or 0)}EA"
        )
    selected = st.selectbox("수정할 재고 선택", labels, key="inv_meta_edit_select")
    row = inv.iloc[labels.index(selected)]

    with st.form("inv_meta_edit_form"):
        c1, c2 = st.columns(2)
        with c1:
            new_lot = st.text_input("제조번호/LOT", value=str(row.get("lot") or "-"))
        with c2:
            new_exp = st.text_input("유통기한", value=str(row.get("exp_date") or "-"), placeholder="예: 28/3/2, 2028-03-02")
        edit_memo = st.text_input("수정 사유/메모", value="")
        submitted = st.form_submit_button("재고정보 수정 저장", type="primary", use_container_width=True)

    if submitted:
        try:
            update_inventory_metadata(int(row.get("id")), new_lot, new_exp, edit_memo)
            st.success("재고 제조번호/유통기한 수정 완료")
            st.rerun()
        except Exception as e:
            st.error(str(e))


def apply_standard_name_change(old_name, new_name):
    """제품 매칭표에서 표준제품명이 바뀌면 이미 올라간 재고/이력에도 즉시 반영한다."""
    old_name = (old_name or "").strip()
    new_name = (new_name or "").strip()
    if not old_name or not new_name or old_name == new_name:
        return
    with connect() as con:
        cur = con.cursor()
        for table, col in [
            ("inventory", "product_name"),
            ("transactions", "product_name"),
            ("outbound_order_items", "product_name"),
            ("erp_ambiguous_candidates", "candidate_product"),
        ]:
            try:
                cur.execute(f"UPDATE {table} SET {col}=? WHERE {col}=?", (new_name, old_name))
            except Exception:
                pass
        con.commit()


def approve_mapping_conflict(company, source_name):
    company = (company or "").strip()
    source_name = (source_name or "").strip()
    if not company or not source_name:
        return
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    exec_sql("""INSERT OR REPLACE INTO product_match_conflict_approvals(company, source_name, approved_at)
                VALUES(?,?,?)""", (company, source_name, now))


def delete_product(product_id):
    """제품 매칭표에서 제품을 삭제한다. 이미 재고/이력/출고지시에 사용된 제품이면 삭제하지 않는다."""
    with connect() as con:
        cur = con.cursor()
        row = cur.execute("SELECT standard_name FROM products WHERE id=?", (int(product_id),)).fetchone()
        if not row:
            raise ValueError("삭제할 제품을 찾을 수 없습니다.")
        name = row[0]
        used = 0
        for table, col in [("inventory", "product_name"), ("transactions", "product_name"), ("outbound_order_items", "product_name")]:
            try:
                cnt = cur.execute(f"SELECT COUNT(*) FROM {table} WHERE {col}=?", (name,)).fetchone()[0]
                used += int(cnt or 0)
            except Exception:
                pass
        if used > 0:
            raise ValueError(f"이미 재고/이력/출고지시에 사용된 제품이라 삭제할 수 없습니다. 사용 건수: {used}건")
        cur.execute("DELETE FROM erp_ambiguous_candidates WHERE candidate_product=?", (name,))
        cur.execute("DELETE FROM products WHERE id=?", (int(product_id),))
        con.commit()


def find_mapping_conflicts_from_inventory():
    """현재 재고의 ERP명/비자료명이 제품매칭표에서 다른 표준제품명에도 연결된 경우를 찾는다.
    사용자가 이미 OK한 원본명은 다시 묻지 않는다.
    """
    inv = q("""
        SELECT company, product_name, COALESCE(warehouse_name, '') AS source_name,
               SUM(qty) AS qty, GROUP_CONCAT(DISTINCT location) AS locations
        FROM inventory
        WHERE TRIM(COALESCE(company,''))<>''
          AND TRIM(COALESCE(product_name,''))<>''
          
        GROUP BY company, product_name, COALESCE(warehouse_name, '')
        ORDER BY company, source_name, product_name
    """)
    if inv.empty:
        return pd.DataFrame()
    rows = []
    for r in inv.itertuples():
        company = str(r.company or "").strip()
        source_name = str(r.source_name or "").strip()
        current_standard = str(r.product_name or "").strip()
        if not source_name or not current_standard or source_name == "-":
            continue
        col, label = mapping_source_column_for_company(company)
        if not col:
            continue
        if is_mapping_conflict_approved(company, source_name):
            continue
        mapped = q(f"""SELECT standard_name FROM products
                       WHERE TRIM(COALESCE({col}, '')) = ?
                       ORDER BY standard_name""", (source_name,))
        mapped_names = sorted({str(x).strip() for x in mapped.get("standard_name", []) if str(x).strip()}) if not mapped.empty else []
        other_names = [x for x in mapped_names if x != current_standard]
        if other_names:
            rows.append({
                "사업장": company,
                "원본명 구분": label,
                "ERP명/비자료명": source_name,
                "재고 DB 표준제품명": current_standard,
                "제품매칭표 기존 표준제품명": " / ".join(mapped_names),
                "충돌 가능 내용": f"재고 DB는 '{current_standard}'로 쓰고 있지만 제품매칭표에는 '{source_name}'이(가) 다른 표준제품명에도 등록되어 있습니다.",
                "현재재고수량": int(r.qty or 0),
                "재고위치": str(r.locations or ""),
            })
    return pd.DataFrame(rows)
