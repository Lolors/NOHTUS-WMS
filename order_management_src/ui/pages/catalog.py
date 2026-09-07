"""Catalog and master-data pages for version 1.0.0."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pandas as pd

from db_migration import normalize_product_code

PRODUCT_COLUMNS = ["제품코드", "제품명", "규격", "포장단위"]
ALIAS_COLUMNS = ["거래처명", "별칭", "제품코드"]
VENDOR_COLUMNS = ["거래처코드", "거래처명", "담당자", "연락처", "이메일", "배송지"]


def _normalize_products(df: pd.DataFrame | None) -> pd.DataFrame:
    source = pd.DataFrame() if df is None else df.copy()
    source = source.fillna("")
    if "제품명" not in source.columns:
        source["제품명"] = source.get("정식제품명", "")
    if "포장단위" not in source.columns:
        source["포장단위"] = source.get("단위", "")
    for column in PRODUCT_COLUMNS:
        if column not in source.columns:
            source[column] = ""
        source[column] = source[column].astype(str).str.strip()
    source["제품코드"] = source["제품코드"].map(normalize_product_code)
    source = source[(source["제품코드"] != "") & (source["제품명"] != "")]
    return source[PRODUCT_COLUMNS].drop_duplicates("제품코드", keep="last").reset_index(drop=True)


def _normalize_aliases(df: pd.DataFrame | None) -> pd.DataFrame:
    source = pd.DataFrame() if df is None else df.copy()
    clean = pd.DataFrame(index=source.index)
    for column in ALIAS_COLUMNS:
        value = source[column] if column in source.columns else ""
        if isinstance(value, pd.DataFrame):
            value = value.iloc[:, 0]
        clean[column] = value
    clean = clean.fillna("")
    for column in ALIAS_COLUMNS:
        clean[column] = clean[column].astype(str).str.strip()
    clean["제품코드"] = clean["제품코드"].map(normalize_product_code)
    clean.loc[clean["거래처명"] == "", "거래처명"] = "전체"
    clean = clean[(clean["별칭"] != "") & (clean["제품코드"] != "")]
    return clean[ALIAS_COLUMNS].drop_duplicates(ALIAS_COLUMNS, keep="last").reset_index(drop=True)


def _normalize_vendors(df: pd.DataFrame | None) -> pd.DataFrame:
    source = pd.DataFrame() if df is None else df.copy().fillna("")
    for column in VENDOR_COLUMNS:
        if column not in source.columns:
            source[column] = ""
        source[column] = source[column].astype(str).str.strip()
    source = source[source["거래처명"] != ""]
    return source[VENDOR_COLUMNS].drop_duplicates("거래처명", keep="last").reset_index(drop=True)


def _next_vendor_code(codes: list[str]) -> str:
    numbers: list[int] = []
    for code in codes:
        text = str(code or "").strip().upper()
        if text.startswith("V") and text[1:].isdigit():
            numbers.append(int(text[1:]))
    return f"V{(max(numbers) + 1 if numbers else 1):03d}"


def _product_excel_bytes(products: pd.DataFrame) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        products.to_excel(writer, index=False, sheet_name="제품목록")
        sheet = writer.book["제품목록"]
        for column, width in {"A": 18, "B": 36, "C": 20, "D": 18}.items():
            sheet.column_dimensions[column].width = width
    output.seek(0)
    return output.getvalue()


def _read_product_upload(uploaded_file) -> pd.DataFrame:
    suffix = Path(uploaded_file.name).suffix.lower()
    if suffix == ".csv":
        raw = pd.read_csv(uploaded_file, dtype=str, keep_default_na=False)
    elif suffix in {".xlsx", ".xls"}:
        raw = pd.read_excel(uploaded_file, dtype=str, keep_default_na=False)
    else:
        raise ValueError("CSV 또는 Excel 파일만 업로드할 수 있습니다.")
    missing = [column for column in PRODUCT_COLUMNS if column not in raw.columns]
    if missing:
        raise ValueError("필수 컬럼이 없습니다: " + ", ".join(missing))
    clean = _normalize_products(raw)
    if clean["제품코드"].duplicated().any():
        duplicated = clean.loc[clean["제품코드"].duplicated(), "제품코드"].drop_duplicates().tolist()
        raise ValueError("중복 제품코드가 있습니다: " + ", ".join(duplicated[:10]))
    return clean


def vendors(core_app, data) -> None:
    st = core_app.st
    current = _normalize_vendors(data["vendors"])
    st.markdown("## 거래처 관리")
    st.caption("거래처명, 담당자, 연락처, 납품처 주소를 관리합니다.")

    with st.container(border=True):
        st.markdown("### 신규 거래처 추가")
        left, right = st.columns(2)
        with left:
            name = st.text_input("거래처명", key="catalog_vendor_name")
            address = st.text_input("납품처 주소", key="catalog_vendor_address")
        with right:
            manager = st.text_input("담당자", key="catalog_vendor_manager")
            phone = st.text_input("연락처", key="catalog_vendor_phone")
        if st.button("거래처 추가", type="primary", use_container_width=True, key="catalog_vendor_add"):
            if not name.strip():
                st.warning("거래처명을 입력하세요.")
            elif name.strip() in current["거래처명"].tolist():
                st.warning("이미 등록된 거래처입니다.")
            else:
                new_row = pd.DataFrame([{
                    "거래처코드": _next_vendor_code(current["거래처코드"].tolist()),
                    "거래처명": name.strip(),
                    "담당자": manager.strip(),
                    "연락처": phone.strip(),
                    "이메일": "",
                    "배송지": address.strip(),
                }])
                core_app.save_vendors(pd.concat([current, new_row], ignore_index=True))
                st.success("거래처를 추가했습니다.")
                st.rerun()

    st.markdown("### 거래처 목록 수정")
    if current.empty:
        st.info("등록된 거래처가 없습니다.")
        return
    view = current.copy()
    view.insert(0, "삭제", False)
    edited = st.data_editor(
        view[["삭제", "거래처코드", "거래처명", "담당자", "연락처", "배송지"]],
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic",
        disabled=["거래처코드"],
        column_config={
            "삭제": st.column_config.CheckboxColumn("삭제"),
            "배송지": st.column_config.TextColumn("납품처 주소"),
        },
        key="catalog_vendor_editor",
    )
    save_col, delete_col = st.columns(2)
    with save_col:
        if st.button("거래처 수정 저장", use_container_width=True, key="catalog_vendor_save"):
            clean = edited.drop(columns=["삭제"]).copy()
            clean["이메일"] = ""
            core_app.save_vendors(_normalize_vendors(clean))
            st.success("거래처 정보를 저장했습니다.")
            st.rerun()
    with delete_col:
        if st.button("선택 거래처 삭제", use_container_width=True, key="catalog_vendor_delete"):
            clean = edited.loc[edited["삭제"] != True].drop(columns=["삭제"]).copy()
            clean["이메일"] = ""
            core_app.save_vendors(_normalize_vendors(clean))
            st.success("선택한 거래처를 삭제했습니다.")
            st.rerun()


def products(core_app, data) -> None:
    st = core_app.st
    current = _normalize_products(data["products"])
    st.markdown("## 제품 관리")
    st.caption("제품코드, 제품명, 규격, 포장단위를 관리합니다.")

    with st.container(border=True):
        st.markdown("### 신규 제품 추가")
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            code = st.text_input("제품코드", key="catalog_product_code")
        with c2:
            name = st.text_input("제품명", key="catalog_product_name")
        with c3:
            specification = st.text_input("규격", key="catalog_product_specification")
        with c4:
            packaging = st.text_input("포장단위", key="catalog_product_packaging")
        if st.button("제품 추가", type="primary", use_container_width=True, key="catalog_product_add"):
            normalized_code = normalize_product_code(code)
            if not normalized_code:
                st.warning("제품코드를 입력하세요.")
            elif not name.strip():
                st.warning("제품명을 입력하세요.")
            elif normalized_code in current["제품코드"].tolist():
                st.warning("이미 존재하는 제품코드입니다.")
            else:
                row = pd.DataFrame([{
                    "제품코드": normalized_code,
                    "제품명": name.strip(),
                    "규격": specification.strip(),
                    "포장단위": packaging.strip(),
                }])
                core_app.save_products(pd.concat([current, row], ignore_index=True))
                st.success("제품을 추가했습니다.")
                st.rerun()

    with st.container(border=True):
        st.markdown("### 엑셀로 제품 목록 일괄 등록/수정")
        template = pd.DataFrame(columns=PRODUCT_COLUMNS)
        left, right = st.columns(2)
        with left:
            st.download_button(
                "빈 양식 다운로드",
                _product_excel_bytes(template),
                file_name="제품목록_업로드양식.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        with right:
            st.download_button(
                "현재 제품목록 다운로드",
                _product_excel_bytes(current),
                file_name="현재_제품목록.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        uploaded = st.file_uploader("제품목록 파일", type=["xlsx", "xls", "csv"], key="catalog_product_upload")
        if uploaded is not None:
            try:
                uploaded_products = _read_product_upload(uploaded)
                st.dataframe(uploaded_products.head(50), use_container_width=True, hide_index=True)
                st.caption(f"총 {len(uploaded_products):,}개 제품")
                if st.button("업로드한 제품목록으로 교체", type="primary", use_container_width=True):
                    core_app.save_products(uploaded_products)
                    st.success("제품목록을 교체했습니다. 기존 별칭은 제품코드 기준으로 유지됩니다.")
                    st.rerun()
            except Exception as exc:
                st.error(str(exc))

    st.markdown("### 제품 목록 수정")
    if current.empty:
        st.info("등록된 제품이 없습니다.")
        return
    view = current.copy()
    view.insert(0, "삭제", False)
    edited = st.data_editor(
        view[["삭제"] + PRODUCT_COLUMNS],
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic",
        disabled=["제품코드"],
        column_config={"삭제": st.column_config.CheckboxColumn("삭제")},
        key="catalog_product_editor",
    )
    save_col, delete_col = st.columns(2)
    with save_col:
        if st.button("제품 수정 저장", use_container_width=True, key="catalog_product_save"):
            core_app.save_products(_normalize_products(edited.drop(columns=["삭제"])))
            st.success("제품 정보를 저장했습니다.")
            st.rerun()
    with delete_col:
        if st.button("선택 제품 삭제", use_container_width=True, key="catalog_product_delete"):
            remaining = edited.loc[edited["삭제"] != True].drop(columns=["삭제"])
            core_app.save_products(_normalize_products(remaining))
            st.success("선택한 제품을 삭제했습니다. 별칭 연결정보는 보존됩니다.")
            st.rerun()


def aliases(core_app, data) -> None:
    st = core_app.st
    vendors_df = _normalize_vendors(data["vendors"])
    products_df = _normalize_products(data["products"])
    aliases_df = _normalize_aliases(data["aliases"])

    st.markdown("## 별칭 관리")
    st.caption("거래처가 사용하는 별칭을 정식 제품코드와 연결합니다.")

    if products_df.empty:
        st.warning("먼저 제품을 등록하세요.")
        return

    vendor_options = ["전체"] + vendors_df["거래처명"].astype(str).tolist()
    product_options = products_df["제품코드"].astype(str).tolist()
    product_label = products_df.set_index("제품코드").apply(
        lambda row: f'{row.get("제품명", "")} / {row.get("규격", "")} / {row.name}', axis=1
    ).to_dict()

    with st.container(border=True):
        st.markdown("### 별칭 추가")
        c1, c2, c3 = st.columns([1.2, 2, 2.4])
        vendor_name = c1.selectbox("거래처", vendor_options, key="catalog_alias_vendor")
        alias = c2.text_input("별칭", key="catalog_alias_name")
        code = c3.selectbox(
            "정식 제품",
            product_options,
            format_func=lambda value: product_label.get(value, value),
            key="catalog_alias_product",
        )
        if st.button("별칭 추가", type="primary", use_container_width=True, key="catalog_alias_add"):
            if not alias.strip():
                st.warning("별칭을 입력하세요.")
            else:
                new_row = pd.DataFrame([{
                    "거래처명": vendor_name,
                    "별칭": alias.strip(),
                    "제품코드": code,
                }])
                saved = _normalize_aliases(pd.concat([aliases_df, new_row], ignore_index=True))
                core_app.save_aliases(saved)
                st.success("별칭을 추가했습니다.")
                st.rerun()

    st.markdown("### 별칭 목록 수정")
    if aliases_df.empty:
        st.info("등록된 별칭이 없습니다.")
        return
    view = aliases_df.copy()
    view.insert(0, "삭제", False)
    edited = st.data_editor(
        view[["삭제"] + ALIAS_COLUMNS],
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic",
        column_config={
            "삭제": st.column_config.CheckboxColumn("삭제"),
            "거래처명": st.column_config.SelectboxColumn("거래처", options=vendor_options),
            "제품코드": st.column_config.SelectboxColumn(
                "정식 제품",
                options=product_options,
                format_func=lambda value: product_label.get(value, value),
            ),
        },
        key="catalog_alias_editor",
    )
    save_col, delete_col = st.columns(2)
    with save_col:
        if st.button("별칭 수정 저장", use_container_width=True, key="catalog_alias_save"):
            core_app.save_aliases(_normalize_aliases(edited.drop(columns=["삭제"])))
            st.success("별칭 정보를 저장했습니다.")
            st.rerun()
    with delete_col:
        if st.button("선택 별칭 삭제", use_container_width=True, key="catalog_alias_delete"):
            remaining = edited.loc[edited["삭제"] != True].drop(columns=["삭제"])
            core_app.save_aliases(_normalize_aliases(remaining))
            st.success("선택한 별칭을 삭제했습니다.")
            st.rerun()
