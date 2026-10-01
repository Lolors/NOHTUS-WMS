"""Stocktake service helpers."""
from __future__ import annotations

from datetime import date, datetime
from io import BytesIO

import pandas as pd

from nohtus.config import COMPANIES
from nohtus.db import connect, q
from nohtus.dates import display_date_only, normalize_exp_date
from nohtus.services.inventory import insert_transaction_log


def _normalize_stocktake_location(value):
    """로케이션 비교용 문자열을 정규화한다."""
    return str(value or "").strip().upper().replace(" ", "").replace("-", "").replace("_", "")


def _normalized_stocktake_location_sql():
    return "REPLACE(REPLACE(REPLACE(UPPER(TRIM(COALESCE(location,''))), ' ', ''), '-', ''), '_', '')"


def _zero_qty_exception_sql():
    """0이어도 실사/기준재고 양식에 남겨야 하는 로케이션 조건."""
    location = _normalized_stocktake_location_sql()
    return f"{location} LIKE 'G1%' OR {location} LIKE 'G2%'"


def current_baseline_stock_excel_bytes(exclude_zero=False):
    """현재 WMS 재고를 기준재고 업로드 양식에 채워서 내려받는다.

    0 수량 제외 옵션을 사용해도 G1, G2 재고는 포함한다.
    """
    where_sql = f"WHERE qty>0 OR {_zero_qty_exception_sql()}" if exclude_zero else ""
    inv = q(
        f"""
        SELECT company, product_name, warehouse_name, lot, exp_date, location, qty
        FROM inventory
        {where_sql}
        ORDER BY company, product_name, lot, exp_date, location
        """
    )
    cols = ["사업장", "ERP제품코드", "ERP제품명", "표준제품명", "LOT/제조번호", "유통기한", "로케이션", "수량"]
    if inv.empty:
        return _baseline_stock_excel_bytes_from_dataframe(pd.DataFrame(columns=cols))

    product_df = q(
        """
        SELECT standard_name, product_code, erp_noh_code,
               erp_nohtuspharm_name, erp_noh_name, erp_nohtus_name, bidata_name
        FROM products
        """
    )
    product_map = {}
    if not product_df.empty:
        for row in product_df.itertuples(index=False):
            product_map[str(getattr(row, "standard_name") or "").strip()] = {
                "product_code": str(getattr(row, "product_code") or "").strip(),
                "erp_noh_code": str(getattr(row, "erp_noh_code") or "").strip(),
                "erp_nohtuspharm_name": str(getattr(row, "erp_nohtuspharm_name") or "").strip(),
                "erp_noh_name": str(getattr(row, "erp_noh_name") or "").strip(),
                "erp_nohtus_name": str(getattr(row, "erp_nohtus_name") or "").strip(),
                "bidata_name": str(getattr(row, "bidata_name") or "").strip(),
            }

    rows = []
    for row in inv.itertuples(index=False):
        company = str(getattr(row, "company") or "").strip()
        standard = str(getattr(row, "product_name") or "").strip()
        warehouse = str(getattr(row, "warehouse_name") or "").strip()
        info = product_map.get(standard, {})
        code = ""
        erp_name = warehouse or standard

        if company == "노투스팜":
            code = info.get("product_code", "")
            erp_name = info.get("erp_nohtuspharm_name", "") or warehouse or standard
        elif company == "NOH":
            code = info.get("erp_noh_code", "")
            erp_name = info.get("erp_noh_name", "") or warehouse or standard
        elif company == "노투스":
            erp_name = info.get("erp_nohtus_name", "") or warehouse or standard
        elif company == "비자료":
            erp_name = info.get("bidata_name", "") or warehouse or standard

        rows.append(
            {
                "사업장": company,
                "ERP제품코드": code,
                "ERP제품명": erp_name,
                "표준제품명": standard,
                "LOT/제조번호": str(getattr(row, "lot") or "-").strip() or "-",
                "유통기한": display_date_only(getattr(row, "exp_date") or "-"),
                "로케이션": str(getattr(row, "location") or "").strip(),
                "수량": int(getattr(row, "qty") or 0),
            }
        )

    return _baseline_stock_excel_bytes_from_dataframe(pd.DataFrame(rows, columns=cols))


def location_series(location):
    """로케이션의 계열(알파벳 구역군)을 반환한다: G/X/T/N, 해당 없으면 빈 문자열."""
    normalized = _normalize_stocktake_location(location)
    if normalized.startswith("G"):
        return "G"
    if normalized.startswith("X"):
        return "X"
    if normalized.startswith("T"):
        return "T"
    from nohtus.config import SPECIAL_LOCATIONS
    if str(location or "").strip() in SPECIAL_LOCATIONS:
        return "N"
    return ""


_TRUE_MATERIAL_VALUES = ("1", "true", "yes", "y", "o", "v", "체크", "부자재")


def _inventory_survey_excel_bytes(df, sheet_name):
    if not df.empty:
        from nohtus.services.stocktake_route import stocktake_route_key

        df = df.assign(_walking_order=df["location"].map(stocktake_route_key)).sort_values(
            ["_walking_order", "location", "company", "product_name", "exp_date"],
            ascending=True, kind="stable", na_position="last",
        ).drop(columns="_walking_order").reset_index(drop=True)
    out = pd.DataFrame()
    out["사업장"] = df["company"] if not df.empty else []
    out["로케이션"] = df["location"] if not df.empty else []
    out["제품명"] = df["product_name"] if not df.empty else []
    out["유통기한"] = df["exp_date"].apply(display_date_only) if not df.empty else []
    out["전산수량"] = df["qty"] if not df.empty else []
    out["실물수량"] = ""

    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        out.to_excel(writer, index=False, sheet_name=sheet_name)
        ws = writer.book[sheet_name]
        # 예시: 노투스팜 / A1-01-01 / 긴 제품명 / 2029-03-20 / 500000.
        # 수량 열은 6자리 숫자와 네 글자 헤더가 모두 들어가도록 맞춘다.
        widths = {"A": 9.5, "B": 9.5, "C": 41.5, "D": 11.5, "E": 9.5, "F": 9.5}
        for col, width in widths.items():
            ws.column_dimensions[col].width = width

        from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

        thin = Side(style="thin", color="000000")
        border = Border(left=thin, right=thin, top=thin, bottom=thin)
        header_fill = PatternFill("solid", fgColor="E5E7EB")
        for row in ws.iter_rows():
            for cell in row:
                cell.border = border
                cell.alignment = Alignment(vertical="center")
                if cell.row == 1:
                    cell.font = Font(bold=True)
                    cell.fill = header_fill

        # 화면에 저장된 랙 묶음을 사용해 단/칸이 달라도 같은 랙은 함께 둔다.
        from nohtus.services.location_map_layout import load_location_map_layout

        rack_by_code = {}
        for item in load_location_map_layout().get("items", []):
            if item.get("kind") == "shape":
                continue
            code = _normalize_stocktake_location(item.get("code"))
            if code:
                rack_by_code[code] = str(item.get("group_id") or code)
        rack_codes = sorted(rack_by_code, key=len, reverse=True)
        from openpyxl.worksheet.pagebreak import Break
        from openpyxl.worksheet.page import PageMargins
        import math
        import unicodedata

        separator = Side(style="medium", color="000000")
        subtle = Side(style="hair", color="D1D5DB")
        white = PatternFill("solid", fgColor="FFFFFF")
        alternate = PatternFill("solid", fgColor="F3F4F6")
        blocks = []
        for values in out.itertuples(index=False, name=None):
            location = str(values[1] or "").strip().upper()
            alphabet = ""
            for character in location:
                if not ("A" <= character <= "Z"):
                    break
                alphabet += character
            normalized = _normalize_stocktake_location(location)
            code = next((code for code in rack_codes if normalized == code or (
                normalized.startswith(code) and normalized[len(code):].isdigit()
            )), None)
            rack = ("rack", rack_by_code[code]) if code else ("alphabet", alphabet)
            line = code or normalized
            key = (alphabet, rack)
            name_width = sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in str(values[2]))
            height = max(30, 15 * math.ceil(name_width / 39) + 6)
            if not blocks or blocks[-1][0] != key:
                blocks.append((key, []))
            blocks[-1][1].append((values, line, height))

        if ws.max_row > 1:
            ws.delete_rows(2, ws.max_row - 1)
        ws.row_dimensions[1].height = 26
        previous_alphabet = None
        page_height = 0
        # A4 세로 인쇄의 여유 있는 높이 안에서 랙 단위로 페이지를 나눈다.
        page_capacity = 660
        for block_index, ((alphabet, _rack), entries) in enumerate(blocks):
            new_area = alphabet != previous_alphabet
            block_height = sum(entry[2] for entry in entries) + (24 if new_area else 0)
            if page_height and page_height + block_height > page_capacity:
                ws.row_breaks.append(Break(id=ws.max_row))
                page_height = 0
            if new_area:
                ws.append([f"{alphabet}구역" if alphabet else "기타 구역"])
                row_number = ws.max_row
                ws.merge_cells(start_row=row_number, start_column=1, end_row=row_number, end_column=6)
                for cell in ws[row_number]:
                    cell.fill = header_fill
                    cell.border = Border(top=separator, bottom=thin)
                ws.cell(row_number, 1).font = Font(bold=True, size=12)
                ws.cell(row_number, 1).alignment = Alignment(vertical="center")
                ws.row_dimensions[row_number].height = 24
                page_height += 24
            previous_line = None
            for entry_index, (values, line, height) in enumerate(entries):
                # 한 페이지보다 큰 랙은 불가피한 경우에만 나눈다.
                if page_height + height > page_capacity and entry_index:
                    ws.row_breaks.append(Break(id=ws.max_row))
                    page_height = 0
                ws.append(list(values))
                row_number = ws.max_row
                top = separator if entry_index == 0 else (thin if line != previous_line else subtle)
                for cell in ws[row_number]:
                    cell.border = Border(left=thin, right=thin, top=top, bottom=subtle)
                    cell.fill = white if cell.column == 6 or block_index % 2 == 0 else alternate
                    cell.alignment = Alignment(vertical="center", wrap_text=True)
                ws.row_dimensions[row_number].height = height
                page_height += height
                previous_line = line
            previous_alphabet = alphabet

        ws.freeze_panes = "C2"
        ws.print_title_rows = "1:1"
        ws.print_options.horizontalCentered = True
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.page_setup.orientation = "portrait"
        ws.page_setup.paperSize = ws.PAPERSIZE_A4
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0
        ws.page_margins = PageMargins(left=0.25, right=0.25, top=0.4, bottom=0.4)
        ws.print_area = f"A1:F{ws.max_row}"
        # 다운로드한 날짜를 고정해 나중에 인쇄해도 실사 기준일을 유지한다.
        from datetime import timedelta, timezone

        survey_date = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d")
        ws.oddHeader.right.text = f"재고실사일: {survey_date}"
        ws.oddHeader.right.size = 9
        ws.oddHeader.right.font = "맑은 고딕,Regular"
        ws.oddHeader.right.color = "595959"
        ws.HeaderFooter.differentOddEven = False
        ws.HeaderFooter.differentFirst = False
        ws.oddFooter.center.text = "&P / &N"
    bio.seek(0)
    return bio.getvalue()


def _material_exclusion_sql():
    """부자재로 분류된 제품을 재고실사 대상에서 항상 제외하는 조건. 부자재는
    별도의 "부자재 재고표"로 뽑기 때문에 기본 재고실사에는 포함하지 않는다."""
    placeholders = ",".join("?" for _ in _TRUE_MATERIAL_VALUES)
    return (
        f"""TRIM(COALESCE(product_name,'')) NOT IN (
            SELECT TRIM(standard_name) FROM products
            WHERE LOWER(TRIM(CAST(COALESCE(is_material, 0) AS TEXT))) IN ({placeholders})
        )""",
        _TRUE_MATERIAL_VALUES,
    )


def full_inventory_excel_bytes(exclude_zero=True, exclude_series=None):
    exclude_series = set(exclude_series or ())
    material_sql, material_params = _material_exclusion_sql()
    conditions = [material_sql]
    if exclude_zero:
        conditions.append("qty<>0")
    where_sql = "WHERE " + " AND ".join(conditions)
    df = q(
        f"""
        SELECT company, location, product_name, exp_date, qty
        FROM inventory
        {where_sql}
        ORDER BY company, location, product_name, exp_date
        """,
        material_params,
    )
    if not df.empty and exclude_series:
        df = df[~df["location"].apply(location_series).isin(exclude_series)]

    return _inventory_survey_excel_bytes(df, "전체재고실사")


def material_inventory_excel_bytes(exclude_zero=True):
    """부자재로 분류된 제품만 모은 재고실사용 엑셀(사업장 포함)."""
    placeholders = ",".join("?" for _ in _TRUE_MATERIAL_VALUES)
    zero_sql = "AND qty<>0" if exclude_zero else ""
    df = q(
        f"""
        SELECT company, location, product_name, exp_date, qty
        FROM inventory
        WHERE TRIM(COALESCE(product_name,'')) IN (
            SELECT TRIM(standard_name) FROM products
            WHERE LOWER(TRIM(CAST(COALESCE(is_material, 0) AS TEXT))) IN ({placeholders})
        )
        {zero_sql}
        ORDER BY company, location, product_name, exp_date
        """,
        _TRUE_MATERIAL_VALUES,
    )
    return _inventory_survey_excel_bytes(df, "부자재재고실사")


def import_stock_survey_excel(uploaded_file, replace_current=True):
    """기준재고 엑셀을 현재 WMS 재고로 불러온다.

    같은 사업장·표준제품명·전산상명칭·LOT·유통기한·로케이션 행이 이미 있으면
    새 행을 또 만들지 않고 기존 행에 수량만 합친다.
    """
    normal_df, issue_df = prepare_baseline_stock_dataframe(uploaded_file)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    inserted = 0
    skipped = int(len(issue_df)) if issue_df is not None else 0
    product_inserted = 0

    with connect() as con:
        cur = con.cursor()
        try:
            if replace_current:
                cur.execute("DELETE FROM inventory")
                cur.execute("DELETE FROM transactions WHERE tx_type='재고조사불러오기'")

            for _, r in normal_df.iterrows():
                company = str(r.get("사업장") or "").strip()
                code = str(r.get("ERP제품코드") or "").strip()
                product_raw = str(r.get("ERP제품명") or "").strip()
                product = str(r.get("표준제품명") or "").strip()
                lot = str(r.get("LOT/제조번호") or "").strip() or "-"
                exp = _excel_date_to_iso(r.get("유통기한"))
                loc = str(r.get("로케이션") or "").strip()
                qty = int(float(r.get("수량") or 0))
                if not company or not product or not loc or qty <= 0:
                    skipped += 1
                    continue

                exists = cur.execute(
                    "SELECT id FROM products WHERE standard_name=? ORDER BY id LIMIT 1",
                    (product,),
                ).fetchone()
                if not exists:
                    cur.execute(
                        """
                        INSERT INTO products(
                            product_code, standard_name, warehouse_name, aliases,
                            erp_nohtuspharm_name, erp_noh_name, erp_noh_code,
                            erp_nohtus_name, bidata_name
                        ) VALUES(?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            code if company == "노투스팜" else "",
                            product,
                            product_raw,
                            "",
                            product_raw if company == "노투스팜" else "",
                            product_raw if company == "NOH" else "",
                            code if company == "NOH" else "",
                            product_raw if company == "노투스" else "",
                            product_raw if company == "비자료" else "",
                        ),
                    )
                    product_inserted += 1
                else:
                    pid = int(exists[0])
                    if company == "노투스팜":
                        cur.execute(
                            "UPDATE products SET erp_nohtuspharm_name=COALESCE(NULLIF(erp_nohtuspharm_name,''), ?), product_code=COALESCE(NULLIF(product_code,''), ?) WHERE id=?",
                            (product_raw, code, pid),
                        )
                    elif company == "NOH":
                        cur.execute(
                            "UPDATE products SET erp_noh_name=COALESCE(NULLIF(erp_noh_name,''), ?), erp_noh_code=COALESCE(NULLIF(erp_noh_code,''), ?) WHERE id=?",
                            (product_raw, code, pid),
                        )
                    elif company == "노투스":
                        cur.execute(
                            "UPDATE products SET erp_nohtus_name=COALESCE(NULLIF(erp_nohtus_name,''), ?) WHERE id=?",
                            (product_raw, pid),
                        )
                    elif company == "비자료":
                        cur.execute(
                            "UPDATE products SET bidata_name=COALESCE(NULLIF(bidata_name,''), ?) WHERE id=?",
                            (product_raw, pid),
                        )

                existing_inventory = cur.execute(
                    """
                    SELECT id, qty
                    FROM inventory
                    WHERE company=?
                      AND product_name=?
                      AND COALESCE(warehouse_name,'')=?
                      AND COALESCE(lot,'-')=?
                      AND COALESCE(exp_date,'-')=?
                      AND location=?
                    ORDER BY id
                    LIMIT 1
                    """,
                    (company, product, product_raw, lot, exp, loc),
                ).fetchone()

                if existing_inventory:
                    inventory_id = int(existing_inventory[0])
                    merged_qty = int(existing_inventory[1] or 0) + qty
                    cur.execute(
                        "UPDATE inventory SET qty=?, updated_at=? WHERE id=?",
                        (merged_qty, now, inventory_id),
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO inventory(
                            company, product_name, warehouse_name, lot,
                            exp_date, location, qty, updated_at
                        ) VALUES(?,?,?,?,?,?,?,?)
                        """,
                        (company, product, product_raw, lot, exp, loc, qty, now),
                    )

                insert_transaction_log(
                    cur,
                    created_at=now,
                    tx_type="재고조사불러오기",
                    product_name=product,
                    warehouse_name=product_raw,
                    lot=lot,
                    exp_date=exp,
                    from_company=None,
                    from_location=None,
                    to_company=company,
                    to_location=loc,
                    qty=qty,
                    memo=f"기준재고 엑셀 업로드 / 원본명: {product_raw}",
                )
                inserted += 1

            con.commit()
        except Exception:
            con.rollback()
            raise

    return inserted, skipped, product_inserted, skipped


def _baseline_stock_excel_bytes_from_dataframe(df):
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="기준재고업로드")
        ws = writer.book["기준재고업로드"]

        from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
        from openpyxl.utils import get_column_letter

        thin = Side(style="thin", color="000000")
        border = Border(left=thin, right=thin, top=thin, bottom=thin)
        header_fill = PatternFill("solid", fgColor="E5E7EB")
        optional_fill = PatternFill("solid", fgColor="EEF2FF")
        header_widths = {
            "사업장": 14,
            "로케이션": 18,
            "ERP제품코드": 18,
            "ERP제품명": 34,
            "표준제품명": 30,
            "LOT/제조번호": 18,
            "유통기한": 16,
            "전산수량": 12,
            "실제수량": 12,
            "차이": 10,
            "수량": 10,
        }
        headers = {
            cell.value: cell.column
            for cell in ws[1]
            if cell.value is not None
        }
        for header, column_index in headers.items():
            ws.column_dimensions[get_column_letter(column_index)].width = header_widths.get(header, 18)

        ws.freeze_panes = "A2"
        max_row = max(1, len(df) + 1)
        max_column = max(1, len(df.columns))
        ws.auto_filter.ref = f"A1:{get_column_letter(max_column)}{max_row}"
        product_code_column = headers.get("ERP제품코드")
        for row in ws.iter_rows():
            for cell in row:
                cell.border = border
                cell.alignment = Alignment(vertical="center", wrap_text=True)
                if product_code_column and cell.column == product_code_column and cell.row > 1:
                    cell.number_format = "@"
                    if cell.value is not None:
                        cell.value = str(cell.value)
                if cell.row == 1:
                    cell.font = Font(bold=True)
                    cell.fill = optional_fill if cell.value == "표준제품명" else header_fill

    bio.seek(0)
    return bio.getvalue()


def prepare_baseline_stock_dataframe(uploaded_file):
    df = pd.read_excel(uploaded_file, dtype=str).fillna("")
    col_alias = {
        "구분": "사업장",
        "ERP제품코드": "ERP제품코드",
        "ERP 제품코드": "ERP제품코드",
        "전산제품코드": "ERP제품코드",
        "제품코드": "ERP제품코드",
        "노투스팜 ERP 제품코드": "ERP제품코드",
        "NOH ERP 제품코드": "ERP제품코드",
        "ERP상제품명": "ERP제품명",
        "ERP제품명": "ERP제품명",
        "제품명": "ERP제품명",
        "전산상명칭": "ERP제품명",
        "전산상 명칭": "ERP제품명",
        "전산상제품명": "ERP제품명",
        "비자료명": "비자료명",
        "LOT": "LOT/제조번호",
        "제조번호": "LOT/제조번호",
        "수량": "수량",
        "기준수량": "수량",
        "현재재고": "수량",
        "실재고": "수량",
    }
    df = df.rename(columns={column: col_alias.get(column, column) for column in df.columns})

    required_columns = [
        "사업장", "ERP제품코드", "ERP제품명", "비자료명", "표준제품명",
        "LOT/제조번호", "유통기한", "로케이션", "수량",
    ]
    for column in required_columns:
        if column not in df.columns:
            df[column] = ""

    rows = []
    for _, row in df.iterrows():
        rows.append(
            {
                "사업장": first_nonblank(row.get("사업장")),
                "ERP제품코드": first_nonblank(row.get("ERP제품코드"), row.get("노투스팜 ERP 제품코드"), row.get("NOH ERP 제품코드")),
                "ERP제품명": _baseline_get_product_raw(row),
                "표준제품명": first_nonblank(row.get("표준제품명")),
                "LOT/제조번호": first_nonblank(row.get("LOT/제조번호")) or "-",
                "유통기한": first_nonblank(row.get("유통기한")) or "-",
                "로케이션": first_nonblank(row.get("로케이션")),
                "수량": first_nonblank(row.get("수량")),
            }
        )

    return pd.DataFrame(rows), pd.DataFrame()


def first_nonblank(*values):
    for value in values:
        if value is None or pd.isna(value):
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _baseline_get_product_raw(row):
    return first_nonblank(row.get("ERP제품명"), row.get("비자료명"))


def _excel_date_to_iso(value):
    if value is None or pd.isna(value):
        return "-"
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.strftime("%Y-%m-%d")
    return normalize_exp_date(value)
