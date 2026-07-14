import hashlib
import re
from datetime import date, datetime

import pandas as pd
import streamlit as st

from nohtus.config import COMPANIES
from nohtus.db import connect, q


PURCHASE_COMPANIES = [c for c in COMPANIES if c in ["노투스팜", "노투스", "NOH"]]
PRODUCT_COLUMNS_BY_COMPANY = {
    "노투스팜": "erp_nohtuspharm_name",
    "노투스": "erp_nohtus_name",
    "NOH": "erp_noh_name",
}


def _clean_text(value):
    if pd.isna(value):
        return ""
    return str(value).strip()


def _normalize_header(value):
    return str(value).replace(" ", "").strip()


def _normalize_money(value):
    text = _clean_text(value).replace(",", "").replace("원", "")
    if text in ["", "-", "nan", "None"]:
        return None
    return pd.to_numeric(text, errors="coerce")


def _normalize_date(value):
    if pd.isna(value) or str(value).strip() == "":
        return ""

    text = _clean_text(value)
    if text.endswith(".0"):
        text = text[:-2]

    digits = re.sub(r"[^0-9]", "", text)
    if len(digits) == 8 and digits[:2] in ["19", "20"]:
        try:
            return datetime.strptime(digits, "%Y%m%d").strftime("%Y-%m-%d")
        except ValueError:
            pass

    short_match = re.fullmatch(r"(\d{2})[.\-/](\d{1,2})[.\-/](\d{1,2})", text)
    if short_match:
        yy, mm, dd = short_match.groups()
        try:
            return date(2000 + int(yy), int(mm), int(dd)).strftime("%Y-%m-%d")
        except ValueError:
            pass

    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return ""
    return parsed.strftime("%Y-%m-%d")


def _read_purchase_excel(uploaded_file):
    sheets = pd.read_excel(uploaded_file, sheet_name=None)
    frames = []
    for sheet_name, frame in sheets.items():
        if frame is None or frame.empty:
            continue
        frame = frame.copy()
        frame.columns = [_normalize_header(c) for c in frame.columns]
        frame["업로드시트"] = sheet_name
        frames.append(frame)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def _load_product_match_map(company):
    erp_col = PRODUCT_COLUMNS_BY_COMPANY.get(company)
    if not erp_col:
        return {}

    products = q(f"""
        SELECT standard_name, {erp_col} AS erp_name, aliases
        FROM products
        ORDER BY standard_name
    """)

    match_map = {}
    for row in products.itertuples(index=False):
        standard = _clean_text(row.standard_name)
        if not standard:
            continue

        names = [standard, _clean_text(row.erp_name)]
        aliases = _clean_text(row.aliases)
        if aliases:
            names.extend([a.strip() for a in aliases.replace("\n", ",").split(",")])

        for name in names:
            if name:
                match_map[name] = standard
                match_map[name.replace(" ", "")] = standard
    return match_map


def _standard_name_for(erp_product_name, match_map):
    name = _clean_text(erp_product_name)
    return match_map.get(name, match_map.get(name.replace(" ", ""), ""))


def _duplicate_key(*parts):
    raw = "|".join(_clean_text(p) for p in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _import_purchase_history(uploaded_file, company):
    source = getattr(uploaded_file, "name", "")
    raw = _read_purchase_excel(uploaded_file)
    if raw.empty:
        return {"total": 0, "inserted": 0, "duplicates": 0, "skipped": 0, "matched": 0, "unmatched": 0}

    required = ["매입일자", "거래처명", "제품명", "수량", "실단가"]
    missing = [col for col in required if col not in raw.columns]
    if missing:
        raise ValueError(f"필수 컬럼이 없습니다: {', '.join(missing)}")

    match_map = _load_product_match_map(company)
    inserted = duplicates = skipped = matched = unmatched = 0

    with connect() as con:
        cur = con.cursor()
        for row in raw.itertuples(index=False):
            item = row._asdict()

            purchase_date = _normalize_date(item.get("매입일자"))
            supplier = _clean_text(item.get("거래처명"))
            erp_product = _clean_text(item.get("제품명"))
            specification = _clean_text(item.get("규격"))
            quantity = pd.to_numeric(str(item.get("수량")).replace(",", ""), errors="coerce")
            unit_price = _normalize_money(item.get("실단가"))
            note = _clean_text(item.get("비고"))

            if not purchase_date or not supplier or not erp_product or pd.isna(quantity) or pd.isna(unit_price):
                skipped += 1
                continue

            standard_name = _standard_name_for(erp_product, match_map)
            if standard_name:
                matched += 1
            else:
                unmatched += 1

            key = _duplicate_key(company, purchase_date, supplier, erp_product, specification, quantity, unit_price, note)
            cur.execute("""
                INSERT OR IGNORE INTO purchase_history(
                    business_name, purchase_date, supplier_name, erp_product_name,
                    specification, quantity, unit_price, note, standard_product_name,
                    source_file, imported_at, duplicate_key
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                company,
                purchase_date,
                supplier,
                erp_product,
                specification,
                float(quantity),
                float(unit_price),
                note,
                standard_name,
                source,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                key,
            ))
            if cur.rowcount:
                inserted += 1
            else:
                duplicates += 1
        con.commit()

    return {
        "total": len(raw),
        "inserted": inserted,
        "duplicates": duplicates,
        "skipped": skipped,
        "matched": matched,
        "unmatched": unmatched,
    }


def _product_options():
    df = q("SELECT standard_name FROM products ORDER BY standard_name")
    if df.empty:
        return []
    return [str(v) for v in df["standard_name"].dropna().tolist()]


def _erp_names_for_standard(standard_name):
    df = q("""
        SELECT standard_name, erp_nohtuspharm_name, erp_nohtus_name, erp_noh_name
        FROM products
        WHERE standard_name=?
    """, (standard_name,))
    if df.empty:
        return []
    row = df.iloc[0]
    names = [row.get("standard_name"), row.get("erp_nohtuspharm_name"), row.get("erp_nohtus_name"), row.get("erp_noh_name")]
    cleaned = []
    for name in names:
        value = _clean_text(name)
        if value and value not in cleaned:
            cleaned.append(value)
    return cleaned


def _query_purchase_rows(item_no, standard_name, start_date, end_date):
    erp_names = _erp_names_for_standard(standard_name)
    placeholders = ",".join(["?"] * len(erp_names))
    params = [standard_name]
    where = "standard_product_name = ?"

    if erp_names:
        where = f"({where} OR erp_product_name IN ({placeholders}))"
        params.extend(erp_names)

    params.extend([start_date, end_date])
    df = q(f"""
        SELECT
            business_name,
            purchase_date,
            supplier_name,
            specification,
            quantity,
            unit_price,
            note
        FROM purchase_history
        WHERE {where}
          AND purchase_date BETWEEN ? AND ?
        ORDER BY purchase_date DESC, business_name, supplier_name
    """, params)

    if df.empty:
        return df

    df.insert(0, "표준제품명", standard_name)
    df.insert(0, "품목", item_no)
    return df


def _render_import_box():
    with st.expander("매입가 엑셀 업로드", expanded=False):
        st.caption("업로드 시 '제  품  명' 컬럼은 공백을 제거해 '제품명'으로 읽습니다.")
        company = st.selectbox("업로드 사업장", PURCHASE_COMPANIES, key="purchase_import_company")
        uploaded = st.file_uploader("매입내역 엑셀 업로드", type=["xlsx"], key="purchase_history_upload")
        if uploaded is not None and st.button("DB에 업로드", type="primary", use_container_width=True):
            try:
                result = _import_purchase_history(uploaded, company)
                st.success("매입내역 업로드 완료")
                st.markdown(f"""
                - 전체 행 : **{result['total']}건**
                - 신규 저장 : **{result['inserted']}건**
                - 중복 제외 : **{result['duplicates']}건**
                - 필수값 누락 제외 : **{result['skipped']}건**
                - 제품매칭 성공 : **{result['matched']}건**
                - 제품매칭 실패 : **{result['unmatched']}건**
                """)
            except Exception as exc:
                st.error(f"업로드 실패: {exc}")


def _ensure_query_items():
    if "purchase_query_items" not in st.session_state:
        st.session_state["purchase_query_items"] = [""]


def _render_query_items(options):
    _ensure_query_items()

    add_col, clear_col = st.columns([2, 2])
    with add_col:
        if st.button("＋ 품목 추가", use_container_width=True):
            st.session_state["purchase_query_items"].append("")
            st.rerun()
    with clear_col:
        if st.button("전체 초기화", use_container_width=True):
            st.session_state["purchase_query_items"] = [""]
            st.rerun()

    selected = []
    for idx, current in enumerate(st.session_state["purchase_query_items"]):
        c1, c2 = st.columns([8, 2])
        with c1:
            option_list = [""] + options
            index = option_list.index(current) if current in option_list else 0
            value = st.selectbox(
                f"{idx + 1}번 품목",
                option_list,
                index=index,
                key=f"purchase_query_item_{idx}",
                format_func=lambda x: "제품을 선택하세요" if x == "" else x,
            )
            st.session_state["purchase_query_items"][idx] = value
            if value:
                selected.append((idx + 1, value))
        with c2:
            st.write("")
            if len(st.session_state["purchase_query_items"]) > 1 and st.button("삭제", key=f"purchase_query_delete_{idx}", use_container_width=True):
                st.session_state["purchase_query_items"].pop(idx)
                st.rerun()

    return selected


def page_purchase_history():
    st.title("매입가 조회")
    st.caption("표준제품명을 선택하면 노투스팜·노투스·NOH ERP명까지 함께 찾아 과거 매입가를 조회합니다.")

    _render_import_box()

    options = _product_options()
    if not options:
        st.info("제품 매칭표에 등록된 제품이 없습니다. 먼저 제품 매칭표를 업로드해 주세요.")
        return

    st.markdown("### 조회 품목")
    d1, d2 = st.columns(2)
    with d1:
        start = st.date_input("시작일", value=date(2020, 1, 1), key="purchase_start_date")
    with d2:
        end = st.date_input("종료일", value=date.today(), key="purchase_end_date")

    selected = _render_query_items(options)

    if st.button("매입가 조회", type="primary", use_container_width=True):
        if not selected:
            st.warning("조회할 품목을 1개 이상 선택해 주세요.")
            return

        frames = []
        for item_no, standard_name in selected:
            rows = _query_purchase_rows(item_no, standard_name, str(start), str(end))
            if not rows.empty:
                frames.append(rows)

        if not frames:
            st.info("조회 결과가 없습니다.")
            return

        result = pd.concat(frames, ignore_index=True)
        result = result.rename(columns={
            "business_name": "사업장",
            "purchase_date": "매입일자",
            "supplier_name": "거래처명",
            "specification": "규격",
            "quantity": "수량",
            "unit_price": "실단가",
            "note": "비고",
        })

        display_cols = ["품목", "표준제품명", "사업장", "매입일자", "거래처명", "규격", "수량", "실단가", "비고"]
        result = result[[col for col in display_cols if col in result.columns]]

        st.markdown("### 조회 결과")
        st.caption("결과표에는 ERP 제품명을 표시하지 않고 표준제품명만 표시합니다.")
        st.dataframe(result, use_container_width=True)
