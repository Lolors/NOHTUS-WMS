"""Escaped order tables and matched-product navigation."""
from html import escape
import pandas as pd
from nohtus.export_app.services.statistics_service import normalize_text
from nohtus.export_app.services.statistics_view_service import integer_quantity_table


def order_table_html(frame, query):
    term = normalize_text(query)
    packed = frame[frame['CTN 번호'].notna()].copy()
    packed = packed.sort_values(['출고일자', 'case_id', 'CTN 번호'], ascending=[False, False, True])
    columns = ['CTN 번호', '출고처', '제품명', '제조번호', '유통기한', '출고수량', '단위']
    parts = []
    for _, group in packed.groupby('case_id', sort=False):
        head = group.iloc[0]
        title = ' · '.join(str(head[c]) for c in ['수출번호', '출고일자', '국가', '바이어'])
        parts.append('<section><h4>'+escape(title)+'</h4><p>총 '+str(group['CTN 번호'].nunique())+' 카톤</p><div class="table-scroll"><table><thead><tr>')
        parts.extend('<th>'+escape(c.replace('출고수량','수량'))+'</th>' for c in columns)
        parts.append('</tr></thead><tbody>')
        group = integer_quantity_table(group[columns])
        for _, row in group.iterrows():
            match = bool(term and term in normalize_text(row['제품명']))
            parts.append('<tr'+(' class="match"' if match else '')+'>')
            for col in columns:
                value = row[col]
                text = '' if pd.isna(value) else str(int(value)) if col == 'CTN 번호' else str(value)
                parts.append('<td'+(' class="highlight"' if match and col == '제품명' else '')+'>'+escape(text)+'</td>')
            parts.append('</tr>')
        parts.append('</tbody></table></div></section>')
    return ''.join(parts)


def order_summary_html(frame):
    """One compact summary row per matching order."""
    count = frame['case_id'].nunique()
    parts = [f'<div class="order-summary-list"><div class="order-summary-heading">검색된 주문 <strong>{count:,}건</strong></div><table><thead><tr><th>출고일자</th><th>국가</th><th>카톤</th><th>포함제품</th></tr></thead><tbody>']
    ordered = frame.sort_values(['출고일자', 'case_id'], ascending=[False, False])
    for _, group in ordered.groupby('case_id', sort=False):
        head = group.iloc[0]
        cartons = group['CTN 번호'].dropna().nunique()
        products = group['제품명'].nunique()
        parts.append(f'<tr><td>{escape(str(head["출고일자"]))}</td><td>{escape(str(head["국가"]))}</td><td>{cartons:,} CTN</td><td>{products:,}종</td></tr>')
    parts.append('</tbody></table></div>')
    return ''.join(parts)
