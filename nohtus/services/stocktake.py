"""Stocktake service helpers."""
from __future__ import annotations
from datetime import date, datetime
from io import BytesIO
import pandas as pd
from nohtus.db import connect, q
from nohtus.dates import display_date_only, normalize_exp_date
from nohtus.services.inventory import insert_transaction_log
from nohtus.config import COMPANIES

def current_baseline_stock_excel_bytes(exclude_zero=False):
    """현재 WMS 재고를 기준재고 업로드 양식에 채워서 내려받는다."""
    where_sql = 'WHERE 1=1' if exclude_zero else ''
    inv = q(f'\n        SELECT company, product_name, warehouse_name, lot, exp_date, location, qty\n        FROM inventory\n        {where_sql}\n        ORDER BY company, product_name, lot, exp_date, location\n    ')
    cols = ['사업장', 'ERP제품코드', 'ERP제품명', '표준제품명', 'LOT/제조번호', '유통기한', '로케이션', '수량']
    if inv.empty:
        return _baseline_stock_excel_bytes_from_dataframe(pd.DataFrame(columns=cols))
    product_df = q('\n        SELECT standard_name, product_code, erp_noh_code,\n               erp_nohtuspharm_name, erp_noh_name, erp_nohtus_name, bidata_name\n        FROM products\n    ')
    product_map = {}
    if not product_df.empty:
        for r in product_df.itertuples(index=False):
            product_map[str(getattr(r, 'standard_name') or '').strip()] = {'product_code': str(getattr(r, 'product_code') or '').strip(), 'erp_noh_code': str(getattr(r, 'erp_noh_code') or '').strip(), 'erp_nohtuspharm_name': str(getattr(r, 'erp_nohtuspharm_name') or '').strip(), 'erp_noh_name': str(getattr(r, 'erp_noh_name') or '').strip(), 'erp_nohtus_name': str(getattr(r, 'erp_nohtus_name') or '').strip(), 'bidata_name': str(getattr(r, 'bidata_name') or '').strip()}
    rows = []
    for r in inv.itertuples(index=False):
        company = str(getattr(r, 'company') or '').strip()
        standard = str(getattr(r, 'product_name') or '').strip()
        warehouse = str(getattr(r, 'warehouse_name') or '').strip()
        info = product_map.get(standard, {})
        code = ''
        erp_name = warehouse or standard
        if company == '노투스팜':
            code = info.get('product_code', '')
            erp_name = info.get('erp_nohtuspharm_name', '') or warehouse or standard
        elif company == 'NOH':
            code = info.get('erp_noh_code', '')
            erp_name = info.get('erp_noh_name', '') or warehouse or standard
        elif company == '노투스':
            erp_name = info.get('erp_nohtus_name', '') or warehouse or standard
        elif company == '비자료':
            erp_name = info.get('bidata_name', '') or warehouse or standard
        rows.append({'사업장': company, 'ERP제품코드': code, 'ERP제품명': erp_name, '표준제품명': standard, 'LOT/제조번호': str(getattr(r, 'lot') or '-').strip() or '-', '유통기한': display_date_only(getattr(r, 'exp_date') or '-'), '로케이션': str(getattr(r, 'location') or '').strip(), '수량': int(getattr(r, 'qty') or 0)})
    return _baseline_stock_excel_bytes_from_dataframe(pd.DataFrame(rows, columns=cols))

def full_inventory_excel_bytes(exclude_zero=True):
    where_sql = 'WHERE 1=1' if exclude_zero else ''
    df = q(f'\n        SELECT location, product_name, warehouse_name, lot, exp_date, qty\n        FROM inventory\n        {where_sql}\n        ORDER BY location, product_name, lot, exp_date\n    ')
    out = pd.DataFrame()
    out['로케이션'] = df['location'] if not df.empty else []
    out['제품명(표준제품명)'] = df['product_name'] if not df.empty else []
    out['제조번호'] = df['lot'] if not df.empty else []
    out['유통기한'] = df['exp_date'].apply(display_date_only) if not df.empty else []
    out['전산수량'] = df['qty'] if not df.empty else []
    out['실물수량'] = ''
    from io import BytesIO
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine='openpyxl') as writer:
        out.to_excel(writer, index=False, sheet_name='전체재고실사')
        ws = writer.book['전체재고실사']
        widths = {'A': 16, 'B': 30, 'C': 18, 'D': 16, 'E': 12, 'F': 12}
        for col, width in widths.items():
            ws.column_dimensions[col].width = width
        from openpyxl.styles import Border, Side, Font, PatternFill, Alignment
        thin = Side(style='thin', color='000000')
        border = Border(left=thin, right=thin, top=thin, bottom=thin)
        header_fill = PatternFill('solid', fgColor='E5E7EB')
        for row in ws.iter_rows():
            for cell in row:
                cell.border = border
                cell.alignment = Alignment(vertical='center')
                if cell.row == 1:
                    cell.font = Font(bold=True)
                    cell.fill = header_fill
    bio.seek(0)
    return bio.getvalue()

def import_stock_survey_excel(uploaded_file, replace_current=True):
    """기준재고 엑셀을 현재 WMS 재고로 불러온다.

    기준재고 파일은 사용자가 ERP/비자료 내용을 가공한 초기 DB 투입용 자료다.
    업로드 시 제품매칭표를 기준으로 표준제품명을 자동 보완하고,
    필수값 누락 또는 매칭 실패 행은 DB에 반영하지 않는다.
    """
    normal_df, issue_df = prepare_baseline_stock_dataframe(uploaded_file)
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    inserted = 0
    skipped = int(len(issue_df)) if issue_df is not None else 0
    product_inserted = 0
    with connect() as con:
        cur = con.cursor()
        if replace_current:
            cur.execute('DELETE FROM inventory')
            cur.execute("DELETE FROM transactions WHERE tx_type='재고조사불러오기'")
        for _, r in normal_df.iterrows():
            company = str(r.get('사업장') or '').strip()
            code = str(r.get('ERP제품코드') or '').strip()
            product_raw = str(r.get('ERP제품명') or '').strip()
            product = str(r.get('표준제품명') or '').strip()
            lot = str(r.get('LOT/제조번호') or '').strip() or '-'
            exp = _excel_date_to_iso(r.get('유통기한'))
            loc = str(r.get('로케이션') or '').strip()
            qty = int(float(r.get('수량') or 0))
            if not company or not product or (not loc) or (qty <= 0):
                skipped += 1
                continue
            exists = cur.execute('SELECT id FROM products WHERE standard_name=?', (product,)).fetchone()
            if not exists:
                cur.execute('INSERT INTO products(product_code, standard_name, warehouse_name, aliases, erp_nohtuspharm_name, erp_noh_name, erp_noh_code, erp_nohtus_name, bidata_name)\n                               VALUES(?,?,?,?,?,?,?,?,?)', (code if company == '노투스팜' else '', product, product_raw, '', product_raw if company == '노투스팜' else '', product_raw if company == 'NOH' else '', code if company == 'NOH' else '', product_raw if company == '노투스' else '', product_raw if company == '비자료' else ''))
                product_inserted += 1
            else:
                pid = int(exists[0])
                if company == '노투스팜':
                    cur.execute("UPDATE products SET erp_nohtuspharm_name=COALESCE(NULLIF(erp_nohtuspharm_name,''), ?), product_code=COALESCE(NULLIF(product_code,''), ?) WHERE id=?", (product_raw, code, pid))
                elif company == 'NOH':
                    cur.execute("UPDATE products SET erp_noh_name=COALESCE(NULLIF(erp_noh_name,''), ?), erp_noh_code=COALESCE(NULLIF(erp_noh_code,''), ?) WHERE id=?", (product_raw, code, pid))
                elif company == '노투스':
                    cur.execute("UPDATE products SET erp_nohtus_name=COALESCE(NULLIF(erp_nohtus_name,''), ?) WHERE id=?", (product_raw, pid))
                elif company == '비자료':
                    cur.execute("UPDATE products SET bidata_name=COALESCE(NULLIF(bidata_name,''), ?) WHERE id=?", (product_raw, pid))
            cur.execute('INSERT INTO inventory(company, product_name, warehouse_name, lot, exp_date, location, qty, updated_at)\n                           VALUES(?,?,?,?,?,?,?,?)', (company, product, product_raw, lot, exp, loc, qty, now))
            insert_transaction_log(cur, created_at=now, tx_type='재고조사불러오기', product_name=product, warehouse_name=product_raw, lot=lot, exp_date=exp, from_company=None, from_location=None, to_company=company, to_location=loc, qty=qty, memo=f'기준재고 엑셀 업로드 / 원본명: {product_raw}')
            inserted += 1
        con.commit()
    return (inserted, skipped, product_inserted, skipped)

def _baseline_stock_excel_bytes_from_dataframe(df):
    """기준재고 업로드 양식 형태로 DataFrame을 엑셀로 변환한다."""
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='기준재고업로드')
        ws = writer.book['기준재고업로드']
        from openpyxl.styles import Border, Side, Font, PatternFill, Alignment
        thin = Side(style='thin', color='000000')
        border = Border(left=thin, right=thin, top=thin, bottom=thin)
        header_fill = PatternFill('solid', fgColor='E5E7EB')
        optional_fill = PatternFill('solid', fgColor='EEF2FF')
        widths = {'A': 14, 'B': 18, 'C': 34, 'D': 30, 'E': 18, 'F': 16, 'G': 18, 'H': 10}
        for col, width in widths.items():
            ws.column_dimensions[col].width = width
        ws.freeze_panes = 'A2'
        max_row = max(1, len(df) + 1)
        ws.auto_filter.ref = f'A1:H{max_row}'
        for row in ws.iter_rows():
            for cell in row:
                cell.border = border
                cell.alignment = Alignment(vertical='center', wrap_text=True)
                if cell.column_letter == 'B':
                    cell.number_format = '@'
                    if cell.value is not None:
                        cell.value = str(cell.value)
                if cell.row == 1:
                    cell.font = Font(bold=True)
                    cell.fill = optional_fill if cell.value == '표준제품명' else header_fill
    bio.seek(0)
    return bio.getvalue()

def prepare_baseline_stock_dataframe(uploaded_file):
    """기준재고 파일을 제품매칭표 기준으로 정제한다.
    별도 검증으로 막지 않고, 제품매칭표에 따라 표준제품명을 자동 보완한다.
    표준제품명이 직접 입력되어 있으면 절대 덮어쓰지 않는다.
    """
    df = pd.read_excel(uploaded_file, dtype=str).fillna('')
    col_alias = {'구분': '사업장', 'ERP제품코드': 'ERP제품코드', 'ERP 제품코드': 'ERP제품코드', '전산제품코드': 'ERP제품코드', '제품코드': 'ERP제품코드', '노투스팜 ERP 제품코드': 'ERP제품코드', 'NOH ERP 제품코드': 'ERP제품코드', 'ERP상제품명': 'ERP제품명', 'ERP제품명': 'ERP제품명', '제품명': 'ERP제품명', '전산상명칭': 'ERP제품명', '전산상 명칭': 'ERP제품명', '전산상제품명': 'ERP제품명', '비자료명': '비자료명', 'LOT': 'LOT/제조번호', '제조번호': 'LOT/제조번호', '수량': '수량', '기준수량': '수량', '현재재고': '수량', '실재고': '수량'}
    df = df.rename(columns={c: col_alias.get(c, c) for c in df.columns})
    for c in ['사업장', 'ERP제품코드', 'ERP제품명', '비자료명', '표준제품명', 'LOT/제조번호', '유통기한', '로케이션', '수량']:
        if c not in df.columns:
            df[c] = ''
    rows = []
    for _, r in df.iterrows():
        company = first_nonblank(r.get('사업장'))
        code = first_nonblank(r.get('ERP제품코드'), r.get('노투스팜 ERP 제품코드'), r.get('NOH ERP 제품코드'))
        product_raw = _baseline_get_product_raw(r)
        standard = first_nonblank(r.get('표준제품명'), r.get('WMS표준제품명'), r.get('실제제품명'), r.get('실제품명'))
        if not standard:
            standard = _baseline_match_standard(company, product_raw)
        if not standard:
            standard = product_raw
        lot = first_nonblank(r.get('LOT/제조번호')) or '-'
        exp_raw = first_nonblank(r.get('유통기한')) or '-'
        loc = first_nonblank(r.get('로케이션')) or '-'
        qty_text = first_nonblank(r.get('수량'))
        try:
            qty = int(float(str(qty_text).replace(',', '')))
        except Exception:
            qty = 0
        if not company or company not in COMPANIES or (not standard) or (qty <= 0):
            continue
        rows.append({'사업장': company, 'ERP제품코드': code, 'ERP제품명': product_raw, '표준제품명': standard, 'LOT/제조번호': lot, '유통기한': _excel_date_to_iso(exp_raw), '로케이션': loc, '수량': qty})
    normal_df = pd.DataFrame(rows, columns=['사업장', 'ERP제품코드', 'ERP제품명', '표준제품명', 'LOT/제조번호', '유통기한', '로케이션', '수량'])
    issue_df = pd.DataFrame(columns=['보완사유', '사업장', 'ERP제품코드', 'ERP제품명', '표준제품명', 'LOT/제조번호', '유통기한', '로케이션', '수량'])
    return (normal_df, issue_df)

def _excel_date_to_iso(v):
    """엑셀 날짜값/문자열을 YYYY-MM-DD로 정규화한다."""
    if pd.isna(v):
        return '-'
    if isinstance(v, (datetime, date)):
        return v.strftime('%Y-%m-%d')
    if isinstance(v, (int, float)) and (not isinstance(v, bool)):
        try:
            d = pd.to_datetime(v, unit='D', origin='1899-12-30')
            return d.strftime('%Y-%m-%d')
        except Exception:
            pass
    text = str(v).strip()
    if not text or text.lower() == 'nan':
        return '-'
    if text == '-':
        return '-'
    return normalize_exp_date(text)


def _baseline_get_product_raw(row):
    return first_nonblank(
        row.get("ERP제품명"), row.get("제품명"), row.get("비자료명"),
        row.get("노투스팜 ERP명"), row.get("NOH ERP명"), row.get("노투스 ERP명")
    )


def _baseline_match_standard(company, product_raw):
    company = (company or "").strip()
    product_raw = (product_raw or "").strip()
    if not company or not product_raw:
        return ""
    if company in ["노투스팜", "NOH", "노투스"]:
        m = match_erp_name(company, product_raw)
        if m.get("status") == "auto" and m.get("candidates"):
            return m["candidates"][0]
        return ""
    if company == "비자료":
        df = q("SELECT standard_name FROM products WHERE TRIM(COALESCE(bidata_name, '')) = ?", (product_raw,))
        if len(df) == 1:
            return str(df.iloc[0]["standard_name"] or "")
        if df.empty:
            same = q("SELECT standard_name FROM products WHERE TRIM(standard_name)=?", (product_raw,))
            if len(same) == 1:
                return str(same.iloc[0]["standard_name"] or "")
    return ""


def first_nonblank(*values):
    for v in values:
        if v is None:
            continue
        text = str(v).strip()
        if text and text.lower() != "nan" and text != "-":
            return text
    return ""
