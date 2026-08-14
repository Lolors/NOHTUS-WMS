from __future__ import annotations

import html
import re
import unicodedata

import streamlit as st
import streamlit.components.v1 as components

from nohtus.export_app.services.shared_document_view_service import quantity_with_unit, shipment_date
from nohtus.export_app.utils.formatters import fmt_number


def render_document(case, packed, actual_rows=None) -> None:
    if not packed:
        st.warning('패킹 완료된 CTN 정보가 없어 최종문서를 출력할 수 없습니다.')
        return

    domestic_method = str(case['domestic_method'] or '').strip()
    is_hand_carry = domestic_method.replace(' ', '').casefold() in {'핸드캐리', 'handcarry'}
    domestic_delivery_cells = (
        '<div class="cell"><div class="label">국내배송 방식</div>'
        f'<div class="value">{html.escape(domestic_method or "-")}</div></div>'
        '<div class="cell"><div class="label">송장번호</div>'
        f'<div class="value">{html.escape(case["tracking_no"] or "-")}</div></div>'
        '<div class="cell"><div class="label">수하인명</div>'
        f'<div class="value">{html.escape(case["consignee_name"] or "-")}</div></div>'
        '<div class="cell"><div class="label">수하인주소</div>'
        f'<div class="value address-value">{html.escape(case["consignee_address"] or "-")}</div></div>'
        '<div class="cell"><div class="label">특이사항</div>'
        f'<div class="value">{html.escape(case["note"] or "-")}</div></div>'
    )

    unit_by_shipment_id: dict[int, str] = {}
    for actual in actual_rows or []:
        try:
            shipment_id = int(actual['id'])
        except (KeyError, TypeError, ValueError):
            continue
        try:
            unit = str(actual['unit'] or '').strip()
        except (KeyError, IndexError, TypeError):
            unit = ''
        unit_by_shipment_id[shipment_id] = unit or '-'

    rows_html: list[str] = []
    grouped: dict[int, list] = {}
    for row in packed:
        grouped.setdefault(int(row['box_no']), []).append(row)
    for box_no, group in grouped.items():
        rowspan = len(group)
        for index, row in enumerate(group):
            rows_html.append('<tr>')
            if index == 0:
                rows_html.append(f'<td rowspan="{rowspan}" class="center merged">CTN {box_no}</td>')
            detail_values = [row['business_unit'], row['product_name'], row['lot_no'], row['expiry_date']]
            detail_classes = ['center', 'product-name', 'center', 'center']
            for value, css_class in zip(detail_values, detail_classes):
                class_attr = f' class="{css_class}"' if css_class else ''
                rows_html.append(f'<td{class_attr}>{html.escape(str(value or ""))}</td>')
            rows_html.append(f'<td class="right">{fmt_number(row["requested_qty"])}</td>')
            try:
                shipment_id = int(row['id'])
            except (KeyError, TypeError, ValueError):
                shipment_id = 0
            unit = unit_by_shipment_id.get(shipment_id, '-')
            rows_html.append(f'<td class="center">{html.escape(unit)}</td>')
            if index == 0:
                weight = f'{fmt_number(row["weight_kg"])} kg' if row['weight_kg'] else '-'
                size_values = [row['length_cm'], row['width_cm'], row['height_cm']]
                size = ' × '.join(fmt_number(value) for value in size_values) + ' cm' if all(size_values) else '-'
                rows_html.append(f'<td rowspan="{rowspan}" class="center merged">{weight}</td>')
                rows_html.append(f'<td rowspan="{rowspan}" class="center merged">{size}</td>')
            rows_html.append('</tr>')

    total_qty = sum(float(row['requested_qty'] or 0) for row in packed)
    box_metrics: dict[int, tuple[float, float, float, float]] = {}
    for row in packed:
        box_no = int(row['box_no'])
        if box_no not in box_metrics:
            box_metrics[box_no] = (
                float(row['weight_kg'] or 0),
                float(row['length_cm'] or 0),
                float(row['width_cm'] or 0),
                float(row['height_cm'] or 0),
            )
    total_weight = sum(metrics[0] for metrics in box_metrics.values())
    total_volume_cbm = sum(
        length * width * height / 1_000_000
        for _, length, width, height in box_metrics.values()
        if length and width and height
    )
    total_volumetric_weight = sum(
        length * width * height / 5_000
        for _, length, width, height in box_metrics.values()
        if length and width and height
    )
    rows_html.append(
        '<tr class="total-row"><td colspan="5" class="right"><b>합계</b></td>'
        f'<td class="right"><b>{fmt_number(total_qty)}</b></td><td></td>'
        f'<td class="center"><b>{fmt_number(total_weight)} kg</b></td><td></td></tr>'
    )
    table_columns = '<colgroup><col style="width:9%"><col style="width:8%"><col style="width:26%"><col style="width:12%"><col style="width:11%"><col style="width:7%"><col style="width:5%"><col style="width:8%"><col style="width:14%"></colgroup>'
    table_header = '<tr><th>CTN No.</th><th>출고처</th><th>제품명</th><th>제조번호</th><th>유통기한</th><th>수량</th><th>단위</th><th>GW (kg)</th><th>CTN 사이즈</th></tr>'
    first_summary = f'{len({row["box_no"] for row in packed})} CTN'
    display_rows = packed
    item_count = len({str(row['product_name']).strip() for row in display_rows if str(row['product_name']).strip()})
    if is_hand_carry:
        summary_column_count = 3
        summary_cards = (
            f'<div class="card"><small>총 CTN 수</small><b>{first_summary}</b></div>'
            f'<div class="card"><small>품목 수</small><b>{item_count} 품목</b></div>'
            f'<div class="card"><small>출고 수량</small><b>{fmt_number(total_qty)}</b></div>'
        )
    else:
        summary_column_count = 5
        summary_cards = (
            f'<div class="card"><small>총 CTN 수</small><b>{first_summary}</b></div>'
            f'<div class="card"><small>총 중량</small><b>{fmt_number(total_weight)} kg</b></div>'
            '<div class="card"><small>운임 계산 참조값</small><div class="freight-ref">'
            f'<span>CBM</span><b>{fmt_number(round(total_volume_cbm, 2))}</b>'
            f'<span>부피중량</span><b>{fmt_number(int(total_volumetric_weight + 0.5))} kg</b>'
            '</div></div>'
            f'<div class="card"><small>품목 수</small><b>{item_count} 품목</b></div>'
            f'<div class="card"><small>출고 수량</small><b>{fmt_number(total_qty)}</b></div>'
        )
    document = f'''<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
*{{box-sizing:border-box}} @page{{size:A4 portrait;margin:6mm}}
html,body{{margin:0;padding:0;background:#f4f7fa;color:#172033;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans KR",Arial,sans-serif}} body{{padding:8px}}
.toolbar{{width:198mm;max-width:100%;margin:0 auto 10px;text-align:right}} .print{{border:0;border-radius:8px;background:#173b5f;color:#fff;font-weight:700;padding:10px 18px;cursor:pointer}}
.document{{width:198mm;max-width:100%;margin:auto;background:#fff;border:0;border-radius:0;overflow:visible;box-shadow:none}}
.header{{padding:16px 22px;background:linear-gradient(135deg,#173b5f,#245d88);color:#fff;display:flex;justify-content:space-between;gap:16px}} .title{{font-size:20px;font-weight:800}} .sub{{font-size:9px;opacity:.8}} .number{{text-align:right}}
.body{{padding:12px 8px 10px}} .section{{font-size:13px;font-weight:800;color:#294f71;margin:0 0 4px;display:flex;align-items:center;gap:5px}} .section-icon{{width:18px;height:18px;border-radius:5px;background:#e8f1f8;color:#245d88;display:inline-flex;align-items:center;justify-content:center;flex:0 0 18px}} .section-icon svg{{width:12px;height:12px;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}}
.grid{{display:grid;grid-template-columns:repeat(4,1fr);border:1px solid #dce3eb;border-radius:7px;overflow:hidden;margin-bottom:7px}} .domestic-grid{{grid-template-columns:repeat(5,1fr)}} .cell{{padding:5px 6px;border-right:1px solid #e5eaf0}} .grid .cell:last-child{{border-right:0}} .label{{font-size:11px;color:#7c8797}} .value{{font-size:13px;font-weight:700;margin-top:2px;white-space:pre-wrap;word-break:break-word}} .address-value{{font-size:11px}}
.summary{{display:grid;grid-template-columns:repeat({summary_column_count},1fr);gap:6px;margin-bottom:20px}} .card{{border:1px solid #dce3eb;border-radius:7px;padding:6px 7px;background:#f8fafc;text-align:center;display:flex;flex-direction:column;justify-content:center}} .card small{{font-size:12px;color:#7c8797}} .card b{{font-size:18px;color:#214f76;white-space:nowrap}} .card>small+ b{{margin-top:5px}} .freight-ref{{margin:5px auto 0;display:grid;grid-template-columns:auto auto;justify-content:center;gap:3px 8px;align-items:baseline;text-align:center}} .freight-ref span{{font-size:10px;color:#607083;text-align:center}} .freight-ref b{{font-size:13px;text-align:center}}
.wrap{{width:100%;max-width:100%;margin:0 auto;overflow:hidden;border:1px solid #d8e0e8;border-radius:7px}} table{{border-collapse:collapse;width:100%;max-width:100%;min-width:0;table-layout:fixed;font-size:11.67px}} th{{background:#294f71;color:#fff;padding:6px 4px;text-align:center;white-space:nowrap;line-height:1.2}} td{{padding:6px 4px;border-right:1px solid #e0e6ed;border-bottom:1px solid #e0e6ed;vertical-align:middle;line-height:1.2;overflow-wrap:anywhere}} .product-name{{white-space:nowrap;font-size:10.8px;letter-spacing:-.15px}} tr{{break-inside:avoid}} .center{{text-align:center}} .right{{text-align:right}} .merged{{background:#f5f8fb;font-weight:700;white-space:nowrap}} .total-row td{{background:#eef3f8;font-weight:700}}
.note-box{{width:100%;margin:6px auto 0;padding:5px 7px;border:1px solid #dce3eb;border-left:4px solid #294f71;border-radius:7px;font-size:8px}}
@media print{{html,body{{width:210mm;height:297mm;background:#fff;padding:0}} .toolbar{{display:none!important}} .document{{width:198mm;max-width:none;margin:0 auto}} .header,th,.merged,.total-row td{{-webkit-print-color-adjust:exact;print-color-adjust:exact}}}}
</style></head><body>
<div class="toolbar"><button class="print" onclick="window.print()">🖨 출력하기</button></div>
<div class="document"><div class="header"><div><div class="title">주문 정보 및 패킹 리스트</div><div class="sub">ORDER INFORMATION &amp; PACKING LIST</div></div><div class="number"><small>EXPORT NO.</small><br><b>{html.escape(case['export_no'])}</b></div></div>
<div class="body"><div class="section"><span class="section-icon"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18"/></svg></span>EXPORT INFORMATION</div><div class="grid">
<div class="cell"><div class="label">국가 / Country</div><div class="value">{html.escape(case['country'] or '-')}</div></div>
<div class="cell"><div class="label">바이어 / Buyer</div><div class="value">{html.escape(case['buyer'] or '-')}</div></div>
<div class="cell"><div class="label">운송방식 / Transport</div><div class="value">{html.escape(case['transport_mode'] or '-')}</div></div>
<div class="cell"><div class="label">출고일 / Ship Date</div><div class="value">{html.escape(shipment_date(case) or '-')}</div></div></div>
<div class="section"><span class="section-icon"><svg viewBox="0 0 24 24"><path d="M3 6h11v11H3zM14 10h4l3 3v4h-7z"/><circle cx="7" cy="18" r="2"/><circle cx="18" cy="18" r="2"/></svg></span>DOMESTIC DELIVERY</div><div class="grid domestic-grid">{domestic_delivery_cells}</div>
<div class="section"><span class="section-icon"><svg viewBox="0 0 24 24"><path d="M4 7l8-4 8 4-8 4zM4 7v10l8 4 8-4V7M12 11v10"/></svg></span>PACKING SUMMARY</div><div class="summary">{summary_cards}</div>
<div class="section">PACKING LIST</div><div class="wrap"><table>{table_columns}<thead>{table_header}</thead><tbody>{''.join(rows_html)}</tbody></table></div></div></div></body></html>'''
    st.markdown(
        '''
        <style>
        div[data-testid="stElementContainer"]:has(iframe[title="streamlit_components.core.html"]),
        div[data-testid="stCustomComponentV1"]:has(iframe[title="streamlit_components.core.html"]) {
            width: 100vw !important;
            max-width: 100vw !important;
        }
        @media (max-width: 900px) {
            div[data-testid="stElementContainer"]:has(iframe[title="streamlit_components.core.html"]),
            div[data-testid="stCustomComponentV1"]:has(iframe[title="streamlit_components.core.html"]) {
                width: 100% !important;
                max-width: 100% !important;
            }
        }
        </style>
        ''',
        unsafe_allow_html=True,
    )
    components.html(document, height=min(1800, max(850, 760 + len(display_rows) * 44)), scrolling=True)


def render_shipment_product_list(case, actual_rows) -> None:
    destination_order = {
        '노투스팜': 0,
        '노투스': 1,
        'NOH': 2,
        '비자료': 3,
    }

    def normalize_product_group_name(value: object) -> str:
        text = unicodedata.normalize('NFKC', str(value or ''))
        text = text.replace('\u200b', '').replace('\ufeff', '')
        text = re.sub(r'\s+', ' ', text).strip()
        return text.casefold()

    sorted_rows = sorted(
        actual_rows,
        key=lambda row: (
            destination_order.get(str(row['business_unit'] or '').strip(), 99),
            str(row['business_unit'] or '').strip().casefold(),
            normalize_product_group_name(row['product_name']),
            str(row['lot_no'] or '').strip().casefold(),
            str(row['expiry_date'] or '').strip(),
        ),
    )

    destination_groups: dict[str, list] = {}
    for row in sorted_rows:
        destination = str(row['business_unit'] or '').strip() or '-'
        destination_groups.setdefault(destination, []).append(row)

    rows_html: list[str] = []
    unique_products: set[str] = set()

    for destination, destination_rows in destination_groups.items():
        destination_rowspan = len(destination_rows)
        product_groups: dict[str, dict[str, object]] = {}
        for row in destination_rows:
            raw_product_name = str(row['product_name'] or '').strip() or '-'
            product_key = normalize_product_group_name(raw_product_name) or '-'
            if product_key not in product_groups:
                product_groups[product_key] = {
                    'display_name': re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', raw_product_name)).strip() or '-',
                    'rows': [],
                }
            product_groups[product_key]['rows'].append(row)
            unique_products.add(product_key)

        destination_written = False
        for product_group in product_groups.values():
            product_name = str(product_group['display_name'])
            product_rows = product_group['rows']
            product_rowspan = len(product_rows)
            for product_index, row in enumerate(product_rows):
                rows_html.append('<tr>')
                if not destination_written:
                    rows_html.append(
                        f'<td rowspan="{destination_rowspan}" class="center merged destination">'
                        f'{html.escape(destination)}</td>'
                    )
                    destination_written = True
                if product_index == 0:
                    rows_html.append(
                        f'<td rowspan="{product_rowspan}" class="product merged">'
                        f'{html.escape(product_name)}</td>'
                    )
                rows_html.append(f'<td class="center lot">{html.escape(str(row["lot_no"] or "-"))}</td>')
                rows_html.append(f'<td class="center expiry">{html.escape(str(row["expiry_date"] or "-"))}</td>')
                rows_html.append(f'<td class="right qty">{html.escape(fmt_number(row["requested_qty"]))}</td>')
                try:
                    unit = str(row['unit'] or '').strip() or '-'
                except (KeyError, IndexError):
                    unit = '-'
                rows_html.append(f'<td class="center unit">{html.escape(unit)}</td>')
                rows_html.append('</tr>')

    if not rows_html:
        rows_html.append('<tr><td colspan="6" class="empty">입력된 출고제품이 없습니다.</td></tr>')

    item_count = len(unique_products)
    total_quantity = sum(float(row['requested_qty'] or 0) for row in sorted_rows)

    document = f'''<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
*{{box-sizing:border-box}} @page{{size:A4 portrait;margin:15mm}}
html,body{{margin:0;padding:0;background:#eef2f6;color:#172033;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans KR",Arial,sans-serif}} body{{padding:10px}}
.toolbar{{width:198mm;max-width:100%;margin:0 auto 10px;text-align:right}} .print{{border:0;border-radius:8px;background:#173b5f;color:white;font-weight:700;padding:10px 18px;cursor:pointer}}
.sheet{{width:198mm;max-width:100%;margin:auto;background:white;border:1px solid #d7dee7;box-shadow:0 10px 28px rgba(30,45,70,.08)}}
.header{{padding:18px 20px 15px;border-bottom:3px solid #234f75;display:flex;justify-content:space-between;gap:20px;align-items:flex-end}} .title{{font-size:21px;font-weight:850;color:#173b5f;letter-spacing:.02em}} .export-no{{text-align:right;font-size:9px;color:#758294}} .export-no b{{display:block;font-size:13px;color:#172033;margin-top:3px}}
.meta{{display:grid;grid-template-columns:repeat(3,1fr);margin:13px 16px 12px;border:1px solid #dce3eb}} .meta div{{padding:7px 8px;border-right:1px solid #e3e8ee}} .meta div:last-child{{border-right:0}} .label{{font-size:12px;color:#7c8797}} .value{{font-size:14px;font-weight:700;margin-top:2px;word-break:break-word}}
.list-summary{{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;margin:0 16px 12px}} .summary-card{{display:flex;align-items:center;justify-content:center;padding:9px 11px;border:1px solid #d8e1ea;border-radius:6px;background:#f7fafc;color:#214f76;font-size:13px;font-weight:700;white-space:nowrap;text-align:center}}
.content{{padding:0 16px 17px}} .summary{{width:100%;margin:0 auto 7px;font-size:11px;color:#697586;text-align:right}}
table{{width:100%;max-width:100%;margin:0 auto;border-collapse:collapse;table-layout:fixed;font-size:11.67px;border:1px solid #cfd8e2}} col.destination{{width:13.5%}} col.product{{width:32.5%}} col.lot{{width:21%}} col.expiry{{width:18%}} col.qty{{width:9%}} col.unit{{width:6%}}
th{{background:#294f71;color:white;padding:7px 5px;text-align:center;font-weight:750}} td{{padding:7px 6px;border-right:1px solid #dce3ea;border-bottom:1px solid #dce3ea;vertical-align:middle;line-height:1.35}} .center{{text-align:center}} .right{{text-align:right}} .product{{white-space:normal;overflow-wrap:anywhere;word-break:keep-all;font-weight:700;text-align:left;padding-left:9px}} .destination{{font-weight:700}} .merged{{background:#f5f8fb}} .lot,.expiry,.unit{{white-space:nowrap}} .qty{{white-space:nowrap;font-weight:650;padding-left:3px;padding-right:3px}} .unit{{padding-left:2px;padding-right:2px}} .empty{{text-align:center;color:#8993a0;padding:20px}}
.notice{{padding:10px 20px 14px;font-size:8.2px;color:#788493;border-top:1px solid #e0e6ed}}
@media print{{html,body{{width:210mm;min-height:297mm;background:white;padding:0}} .toolbar{{display:none!important}} .sheet{{width:198mm;max-width:none;margin:0 auto;border:0;box-shadow:none}} .header{{padding:13px 15px 11px}} .title{{font-size:18px}} .meta{{margin:10px 8px}} .list-summary{{margin:0 8px 9px;gap:6px}} .summary-card{{padding:7px 9px}} .content{{padding:0 8px 12px}} .summary,table{{width:100%;max-width:none}} table{{font-size:10.5px}} th{{padding:5px 3px}} td{{padding:5px 4px}} .product{{padding-left:6px}} .qty,.unit{{padding-left:2px;padding-right:2px}} .notice{{padding:8px 15px 0}} .header,th{{-webkit-print-color-adjust:exact;print-color-adjust:exact}}}}
</style></head><body>
<div class="toolbar"><button class="print" onclick="window.print()">🖨 출력하기</button></div>
<div class="sheet"><div class="header"><div class="title">출고 예정 제품 리스트</div><div class="export-no">EXPORT NO.<b>{html.escape(case['export_no'] or '-')}</b></div></div>
<div class="meta"><div><span class="label">국가 / Country</span><div class="value">{html.escape(case['country'] or '-')}</div></div><div><span class="label">바이어 / Buyer</span><div class="value">{html.escape(case['buyer'] or '-')}</div></div><div><span class="label">운송방식 / Transport</span><div class="value">{html.escape(case['transport_mode'] or '-')}</div></div></div>
<div class="list-summary"><div class="summary-card">전체 품목 수 : {item_count}품목</div><div class="summary-card">출고수량 : {fmt_number(total_quantity)}</div></div>
<div class="content"><table><colgroup><col class="destination"><col class="product"><col class="lot"><col class="expiry"><col class="qty"><col class="unit"></colgroup><thead><tr><th>출고처</th><th>제품명</th><th>제조번호</th><th>유통기한</th><th>출고수량</th><th>단위</th></tr></thead><tbody>{''.join(rows_html)}</tbody></table></div>
<div class="notice">본 문서는 패킹 완료 전 작성된 출고 예정 제품 목록이며, 최종 수량 및 패킹 정보는 변경될 수 있습니다.</div></div></body></html>'''
    components.html(document, height=min(1800, max(700, 500 + len(sorted_rows) * 38)), scrolling=True)
