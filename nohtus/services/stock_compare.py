"""ERP 및 외부창고 실사재고와 WMS 재고를 비교하는 서비스."""
from __future__ import annotations

from io import BytesIO
import re

import pandas as pd

from nohtus.db import q
from nohtus.dates import normalize_exp_date


ERP_COLUMNS = ["사업장", "표준제품명", "ERP제품명", "WMS수량", "ERP수량", "차이", "상태"]
GM_COLUMNS = ["표준제품명", "유통기한", "WMS수량", "실사수량", "차이", "상태"]
ISSUE_COLUMNS = ["구분", "사업장", "표준제품명", "유통기한", "WMS수량", "비교수량", "차이", "문제"]


def compare_stock_files(nohtuspharm_file=None, noh_file=None, nohtus_file=None, gmmedic_file=None):
    """업로드된 ERP/실사 파일을 WMS 현재재고와 비교한다."""
    erp_parts = []
    import_issues = []

    for company, uploaded, parser in [
        ("노투스팜", nohtuspharm_file, _read_standard_erp),
        ("NOH", noh_file, _read_standard_erp),
        ("노투스", nohtus_file, _read_nohtus_erp),
    ]:
        if uploaded is None:
            continue
        raw = parser(uploaded)
        mapped, issues = _map_erp_products(raw, company)
        erp_parts.append(mapped)
        import_issues.extend(issues)

    erp_source = pd.concat(erp_parts, ignore_index=True) if erp_parts else pd.DataFrame(
        columns=["사업장", "표준제품명", "ERP제품명", "ERP수량"]
    )
    erp_result = _compare_erp(erp_source)

    gm_result = pd.DataFrame(columns=GM_COLUMNS)
    if gmmedic_file is not None:
        gm_raw = _read_gmmedic(gmmedic_file)
        gm_mapped, gm_issues = _map_gmmedic_products(gm_raw)
        import_issues.extend(gm_issues)
        gm_result = _compare_gmmedic(gm_mapped)

    problems = _build_problem_list(erp_result, gm_result, import_issues)
    return {
        "erp": erp_result,
        "gmmedic": gm_result,
        "problems": problems,
        "excel": comparison_excel_bytes(erp_result, gm_result, problems),
    }


def _read_excel_first_sheet(uploaded_file, **kwargs):
    """구형 xls의 깨진 워크시트 이름을 우회해 첫 번째 시트만 안전하게 읽는다."""
    try:
        return pd.read_excel(uploaded_file, sheet_name=0, **kwargs)
    except ValueError as exc:
        message = str(exc)
        if "cannot be used in worksheets" not in message:
            raise
        uploaded_file.seek(0)
        try:
            import xlrd
        except ImportError as import_exc:
            raise ValueError("구형 .xls 파일을 읽으려면 xlrd가 필요합니다. 파일을 .xlsx로 저장한 뒤 다시 업로드해 주세요.") from import_exc
        book = xlrd.open_workbook(file_contents=uploaded_file.read(), ignore_workbook_corruption=True)
        sheet = book.sheet_by_index(0)
        rows = [sheet.row_values(i) for i in range(sheet.nrows)]
        return pd.DataFrame(rows)


def _read_standard_erp(uploaded_file):
    df = _read_excel_first_sheet(uploaded_file, dtype=object)
    df.columns = [_clean_header(c) for c in df.columns]
    _require_columns(df, ["제품명", "현재고수량"])
    out = df[["제품명", "현재고수량"]].copy()
    out.columns = ["ERP제품명", "ERP수량"]
    return _clean_quantity_rows(out)


def _read_nohtus_erp(uploaded_file):
    df = _read_excel_first_sheet(uploaded_file, header=7, dtype=object)
    df.columns = [_clean_header(c) for c in df.columns]
    _require_columns(df, ["품목명/규격", "현재재고"])
    out = df[["품목명/규격", "현재재고"]].copy()
    out.columns = ["ERP제품명", "ERP수량"]
    return _clean_quantity_rows(out)


def _read_gmmedic(uploaded_file):
    preview = _read_excel_first_sheet(uploaded_file, header=None, dtype=object, nrows=20)
    header_row = None
    for idx, row in preview.iterrows():
        values = {_clean_header(v) for v in row.tolist() if str(v).strip() and str(v).lower() != "nan"}
        if {"제품명", "유효기한", "재고"}.issubset(values):
            header_row = int(idx)
            break
    if header_row is None:
        raise ValueError("지엠메딕 파일에서 '제품명 / 유효기한 / 재고' 헤더를 찾지 못했습니다.")

    uploaded_file.seek(0)
    df = _read_excel_first_sheet(uploaded_file, header=header_row, dtype=object)
    df.columns = [_clean_header(c) for c in df.columns]
    _require_columns(df, ["제품명", "유효기한", "재고"])
    df["제품명"] = df["제품명"].ffill()
    if "코드" in df.columns:
        df["코드"] = df["코드"].ffill()

    out = df[["제품명", "유효기한", "재고"]].copy()
    out.columns = ["실사제품명", "유통기한", "실사수량"]
    out["실사제품명"] = out["실사제품명"].fillna("").astype(str).str.strip()
    out["유통기한"] = out["유통기한"].apply(_normalize_expiry)
    out["실사수량"] = out["실사수량"].apply(_to_number)
    out = out[(out["실사제품명"] != "") & out["실사수량"].notna()].copy()
    out["실사수량"] = out["실사수량"].astype(int)
    return out


def _map_erp_products(raw, company):
    name_map = _product_name_map(company)
    rows = []
    issues = []
    for r in raw.itertuples(index=False):
        erp_name = str(r.ERP제품명 or "").strip()
        standard = name_map.get(_name_key(erp_name), "")
        if not standard:
            issues.append({
                "구분": "제품매칭", "사업장": company, "표준제품명": erp_name,
                "유통기한": "-", "WMS수량": 0, "비교수량": int(r.ERP수량),
                "차이": -int(r.ERP수량), "문제": f"ERP 제품명 매칭 필요: {erp_name}",
            })
            continue
        rows.append({"사업장": company, "표준제품명": standard, "ERP제품명": erp_name, "ERP수량": int(r.ERP수량)})
    return pd.DataFrame(rows, columns=["사업장", "표준제품명", "ERP제품명", "ERP수량"]), issues


def _map_gmmedic_products(raw):
    name_map = _product_name_map("노투스팜")
    rows = []
    issues = []
    for r in raw.itertuples(index=False):
        raw_name = str(r.실사제품명 or "").strip()
        standard = name_map.get(_name_key(raw_name), "")
        if not standard:
            issues.append({
                "구분": "제품매칭", "사업장": "지엠메딕", "표준제품명": raw_name,
                "유통기한": str(r.유통기한), "WMS수량": 0, "비교수량": int(r.실사수량),
                "차이": -int(r.실사수량), "문제": f"실사 제품명 매칭 필요: {raw_name}",
            })
            continue
        rows.append({"표준제품명": standard, "유통기한": str(r.유통기한), "실사수량": int(r.실사수량)})
    return pd.DataFrame(rows, columns=["표준제품명", "유통기한", "실사수량"]), issues


def _compare_erp(erp_source):
    if erp_source.empty:
        return pd.DataFrame(columns=ERP_COLUMNS)

    erp = erp_source.groupby(["사업장", "표준제품명"], as_index=False).agg(
        ERP제품명=("ERP제품명", lambda s: " / ".join(sorted(set(str(v) for v in s if str(v).strip())))),
        ERP수량=("ERP수량", "sum"),
    )
    wms = q("""
        SELECT company AS 사업장, product_name AS 표준제품명, SUM(qty) AS WMS수량
        FROM inventory
        WHERE company IN ('노투스팜', 'NOH', '노투스')
        GROUP BY company, product_name
    """)
    companies = erp["사업장"].drop_duplicates().tolist()
    if not wms.empty:
        wms = wms[wms["사업장"].isin(companies)].copy()
    merged = pd.merge(wms, erp, how="outer", on=["사업장", "표준제품명"])
    merged["ERP제품명"] = merged["ERP제품명"].fillna("")
    for col in ["WMS수량", "ERP수량"]:
        merged[col] = pd.to_numeric(merged[col], errors="coerce").fillna(0).astype(int)
    merged["차이"] = merged["WMS수량"] - merged["ERP수량"]
    merged["상태"] = merged["차이"].apply(lambda v: "일치" if int(v) == 0 else "불일치")
    return merged[ERP_COLUMNS].sort_values(["사업장", "상태", "표준제품명"], ascending=[True, False, True]).reset_index(drop=True)


def _compare_gmmedic(gm_source):
    gm = gm_source.groupby(["표준제품명", "유통기한"], as_index=False)["실사수량"].sum()
    wms = q("""
        SELECT product_name AS 표준제품명, exp_date AS 유통기한, SUM(qty) AS WMS수량
        FROM inventory
        WHERE company='노투스팜' AND location LIKE '%지엠메딕%'
        GROUP BY product_name, exp_date
    """)
    if not wms.empty:
        wms["유통기한"] = wms["유통기한"].apply(_normalize_expiry)
        wms = wms.groupby(["표준제품명", "유통기한"], as_index=False)["WMS수량"].sum()
    merged = pd.merge(wms, gm, how="outer", on=["표준제품명", "유통기한"])
    for col in ["WMS수량", "실사수량"]:
        merged[col] = pd.to_numeric(merged[col], errors="coerce").fillna(0).astype(int)
    merged["차이"] = merged["WMS수량"] - merged["실사수량"]
    merged["상태"] = merged["차이"].apply(lambda v: "일치" if int(v) == 0 else "불일치")
    return merged[GM_COLUMNS].sort_values(["상태", "표준제품명", "유통기한"], ascending=[False, True, True]).reset_index(drop=True)


def _build_problem_list(erp_result, gm_result, import_issues):
    rows = list(import_issues)
    if not erp_result.empty:
        for r in erp_result[erp_result["상태"] == "불일치"].itertuples(index=False):
            rows.append({
                "구분": "ERP 불일치", "사업장": r.사업장, "표준제품명": r.표준제품명,
                "유통기한": "-", "WMS수량": int(r.WMS수량), "비교수량": int(r.ERP수량),
                "차이": int(r.차이), "문제": "WMS와 ERP 총재고가 다릅니다.",
            })
    if not gm_result.empty:
        for r in gm_result[gm_result["상태"] == "불일치"].itertuples(index=False):
            rows.append({
                "구분": "실사 불일치", "사업장": "지엠메딕", "표준제품명": r.표준제품명,
                "유통기한": r.유통기한, "WMS수량": int(r.WMS수량), "비교수량": int(r.실사수량),
                "차이": int(r.차이), "문제": "WMS와 지엠메딕 실사재고가 다릅니다.",
            })
    return pd.DataFrame(rows, columns=ISSUE_COLUMNS)


def comparison_excel_bytes(erp_result, gm_result, problems):
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        problems.to_excel(writer, index=False, sheet_name="문제목록")
        erp_result.to_excel(writer, index=False, sheet_name="ERP비교")
        gm_result.to_excel(writer, index=False, sheet_name="지엠메딕실사비교")
        for ws in writer.book.worksheets:
            ws.freeze_panes = "A2"
            ws.auto_filter.ref = ws.dimensions
            for column_cells in ws.columns:
                max_len = max(len(str(c.value or "")) for c in column_cells)
                ws.column_dimensions[column_cells[0].column_letter].width = min(max(max_len + 2, 10), 42)
    bio.seek(0)
    return bio.getvalue()


def _product_name_map(company):
    products = q("""
        SELECT standard_name, warehouse_name, erp_nohtuspharm_name, erp_noh_name, erp_nohtus_name, aliases
        FROM products
    """)
    result = {}
    if products.empty:
        return result
    company_col = {"노투스팜": "erp_nohtuspharm_name", "NOH": "erp_noh_name", "노투스": "erp_nohtus_name"}.get(company)
    for r in products.itertuples(index=False):
        standard = str(getattr(r, "standard_name", "") or "").strip()
        names = [standard, str(getattr(r, "warehouse_name", "") or "").strip()]
        if company_col:
            names.append(str(getattr(r, company_col, "") or "").strip())
        aliases = str(getattr(r, "aliases", "") or "")
        names.extend(re.split(r"[,/\n;|]+", aliases))
        for name in names:
            key = _name_key(name)
            if key and key not in result:
                result[key] = standard
    return result


def _clean_quantity_rows(df):
    df["ERP제품명"] = df["ERP제품명"].fillna("").astype(str).str.strip()
    df["ERP수량"] = df["ERP수량"].apply(_to_number)
    df = df[(df["ERP제품명"] != "") & df["ERP수량"].notna()].copy()
    df["ERP수량"] = df["ERP수량"].astype(int)
    return df


def _to_number(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip().replace(",", "")
    if not text or text.lower() == "nan":
        return None
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return None


def _normalize_expiry(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "-"
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    text = str(value).strip()
    if not text or text.lower() == "nan" or text == "-":
        return "-"
    try:
        return normalize_exp_date(text)
    except Exception:
        return text


def _clean_header(value):
    return re.sub(r"\s+", "", str(value or "").strip())


def _name_key(value):
    return re.sub(r"[\s\-_()/\[\]]+", "", str(value or "").strip()).lower()


def _require_columns(df, required):
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"필수 컬럼을 찾지 못했습니다: {', '.join(missing)}")