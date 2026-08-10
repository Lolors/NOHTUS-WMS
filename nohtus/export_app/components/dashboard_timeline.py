from __future__ import annotations

from calendar import month_abbr
from datetime import date, timedelta
from html import escape
import json
from pathlib import Path

import streamlit.components.v1 as components

from nohtus.export_app.services.dashboard_view_service import timeline_bounds


DAY_WIDTH = 44
LABEL_WIDTH = 0

_timeline_component = components.declare_component(
    'dashboard_order_timeline',
    path=str(Path(__file__).with_name('dashboard_timeline_component')),
)


def _parse_date(value: object) -> date | None:
    try:
        return date.fromisoformat(str(value or '').strip()[:10])
    except ValueError:
        return None


def _month_segments(start: date, end: date) -> list[tuple[str, int]]:
    segments: list[tuple[str, int]] = []
    cursor = start
    while cursor <= end:
        month_start = cursor
        while cursor <= end and cursor.month == month_start.month:
            cursor += timedelta(days=1)
        label = f'{month_abbr[month_start.month]} {month_start.year}'
        segments.append((label, (cursor - month_start).days))
    return segments


def render_order_timeline(rows: list[dict]) -> int | None:
    if not rows:
        return None

    today = date.today()
    start, end = timeline_bounds(rows, today=today)
    dates: list[date] = []
    cursor = start
    while cursor <= end:
        dates.append(cursor)
        cursor += timedelta(days=1)

    day_headers = ''.join(
        f'<div class="day {"weekend" if value.weekday() >= 5 else ""} '
        f'{"today-day" if value == today else ""}" data-date="{value.isoformat()}">'
        f'<span>{value.day}</span></div>'
        for value in dates
    )
    month_headers = ''.join(
        f'<div class="month" style="width:{count * DAY_WIDTH}px">{escape(label)}</div>'
        for label, count in _month_segments(start, end)
    )
    grid_columns = ''.join(
        f'<div class="grid-day {"weekend" if value.weekday() >= 5 else ""} '
        f'{"today-grid" if value == today else ""}"></div>'
        for value in dates
    )

    body_rows: list[str] = []
    for row in rows:
        start_date = _parse_date(row.get('start_date')) or start
        requested_end = _parse_date(row.get('end_date'))
        end_date = max(start_date, requested_end or today)
        offset = (start_date - start).days * DAY_WIDTH + 4
        width = max(DAY_WIDTH - 8, ((end_date - start_date).days + 1) * DAY_WIDTH - 8)
        export_no = escape(str(row.get('export_no') or '수출번호 미입력'))
        party = escape(str(row.get('party') or '국가·바이어 미입력'))
        stage = escape(str(row.get('stage') or '단계 미입력'))
        bar_label = escape(str(row.get('bar_label') or party))
        product_summary = escape(str(row.get('product_summary') or '주문목록 없음'))
        products = escape(str(row.get('products') or '-'), quote=True).replace('\n', '&#10;')
        period = f'{start_date.isoformat()} ~ {end_date.isoformat()}'
        tooltip = escape(f'{export_no}\n{period}\n{stage}\n주문목록:\n', quote=True) + products
        bar_background = escape(str(row.get('bar_background') or '#94a3b8'), quote=True)
        bar_text = escape(str(row.get('bar_text') or '#1f2937'), quote=True)
        bar_accent = escape(str(row.get('bar_accent') or '#64748b'), quote=True)
        case_id = int(row.get('case_id') or 0)
        body_rows.append(
            '<div class="order-row">'
            f'<div class="row-track">{grid_columns}'
            f'<button class="order-bar" type="button" data-case-id="{case_id}" '
            f'data-start="{start_date.isoformat()}" '
            f'data-end="{end_date.isoformat()}" '
            f'title="{tooltip}" aria-label="{tooltip}" '
            f'style="left:{offset}px;width:{width}px;--bar-bg:{bar_background};'
            f'--bar-text:{bar_text};--bar-accent:{bar_accent}">'
            f'<span class="bar-party">{bar_label}</span>'
            f'<span class="bar-products">{product_summary}</span></button></div></div>'
        )

    payload = json.dumps({
        'todayOffset': max(0, (today - start).days * DAY_WIDTH),
        'dayWidth': DAY_WIDTH,
    })
    height = min(820, max(350, 150 + len(rows) * 76))
    document = f'''<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><style>
* {{ box-sizing: border-box; }}
body {{ margin: 0; color: #2d333b; font-family: Arial, "Noto Sans KR", sans-serif; }}
.toolbar {{ display:flex; justify-content:flex-end; gap:5px; margin:0 2px 9px; }}
.toolbar button {{ border:1px solid #d7dce3; border-radius:7px; background:#fff; color:#505864; padding:6px 11px; cursor:pointer; }}
.toolbar button:hover,.toolbar button.active {{ border-color:#3b82f6; background:#eef5ff; color:#1769d2; }}
.shell {{ border:1px solid #d9dde3; border-radius:10px; overflow:hidden; background:#fff; }}
.timeline {{ overflow:auto; max-height:{height - 50}px; position:relative; }}
.canvas {{ min-width:{LABEL_WIDTH + len(dates) * DAY_WIDTH}px; }}
.month-row,.day-row,.order-row {{ display:flex; min-width:max-content; }}
.month-row {{ position:sticky; top:0; z-index:7; height:34px; border-bottom:1px solid #d5d9df; }}
.month {{ flex:0 0 auto; padding:8px 12px; border-right:1px solid #d5d9df; background:#f1f2f4; font-weight:700; color:#5d6570; }}
.day-row {{ position:sticky; top:34px; z-index:7; height:35px; border-bottom:1px solid #cfd4da; background:#fff; }}
.day {{ width:{DAY_WIDTH}px; flex:0 0 {DAY_WIDTH}px; text-align:center; padding-top:8px; border-right:1px solid #edf0f3; color:#656d78; }}
.day.weekend,.grid-day.weekend {{ background:#f7f8fa; }}
.day.today-day span {{ padding:3px 7px; border-radius:8px; background:#3b82f6; color:#fff; font-weight:800; }}
.order-row {{ height:76px; border-bottom:1px solid #edf0f3; }}
.order-row:last-child {{ border-bottom:0; }}
.row-track {{ position:relative; width:{len(dates) * DAY_WIDTH}px; flex:0 0 {len(dates) * DAY_WIDTH}px; }}
.grid-day {{ display:inline-block; width:{DAY_WIDTH}px; height:100%; border-right:1px solid #edf0f3; }}
.grid-day.today-grid {{ border-left:2px solid #3b82f6; }}
.order-bar {{ position:absolute; top:14px; height:48px; padding:6px 10px 5px 12px; border:0; border-radius:7px; background:var(--bar-bg); color:var(--bar-text); font:inherit; font-size:13px; font-weight:800; text-align:left; box-shadow:0 2px 6px rgba(31,41,55,.18); overflow:visible; display:flex; flex-direction:column; justify-content:center; gap:2px; z-index:2; cursor:pointer; }}
.order-bar:hover,.order-bar:focus {{ z-index:4; outline:2px solid color-mix(in srgb, var(--bar-accent) 70%, white); outline-offset:2px; filter:brightness(.98); }}
.order-bar::before {{ content:""; position:absolute; left:0; top:0; bottom:0; width:5px; border-radius:7px 0 0 7px; background:var(--bar-accent); }}
.order-bar span {{ display:block; margin-left:3px; width:max-content; max-width:none; overflow:visible; white-space:nowrap; text-overflow:clip; text-shadow:0 1px 1px rgba(255,255,255,.28); }}
.order-bar .bar-products {{ color:inherit; font-size:12px; font-weight:700; opacity:.9; }}
</style></head><body>
<div class="toolbar"><button data-view="today">오늘</button><button data-view="week">주</button><button data-view="month" class="active">개월</button><button data-view="quarter">분기</button></div>
<div class="shell"><div class="timeline" id="timeline"><div class="canvas">
<div class="month-row">{month_headers}</div>
<div class="day-row">{day_headers}</div>
{''.join(body_rows)}
</div></div></div>
<script>
const config={payload}; const timeline=document.getElementById('timeline');
const labelWidth={LABEL_WIDTH};
function centerToday() {{ timeline.scrollLeft=Math.max(0,labelWidth+config.todayOffset-timeline.clientWidth/2); }}
function setZoom(days) {{
  const available=Math.max(360,timeline.clientWidth-labelWidth); const width=Math.max(24,Math.min(88,available/days));
  document.documentElement.style.setProperty('--unused',width+'px');
  document.querySelectorAll('.day,.grid-day').forEach(el=>{{el.style.width=width+'px';el.style.flexBasis=width+'px';}});
  document.querySelectorAll('.month').forEach(el=>{{const count=Math.round(parseFloat(el.style.width)/config.dayWidth);el.style.width=(count*width)+'px';}});
  document.querySelectorAll('.row-track').forEach(el=>{{el.style.width=({len(dates)}*width)+'px';el.style.flexBasis=({len(dates)}*width)+'px';}});
  document.querySelectorAll('.order-bar').forEach(el=>{{
    const axisStart=new Date('{start.isoformat()}');
    const barStart=new Date(el.dataset.start); const barEnd=new Date(el.dataset.end);
    const offset=Math.round((barStart-axisStart)/86400000);
    const duration=Math.max(1,Math.round((barEnd-barStart)/86400000)+1);
    el.style.left=(offset*width+4)+'px'; el.style.width=Math.max(width-8,duration*width-8)+'px';
  }});
  config.dayWidth=width; config.todayOffset={(today-start).days}*width; centerToday();
}}
document.querySelectorAll('[data-view]').forEach(btn=>btn.addEventListener('click',()=>{{
  document.querySelectorAll('[data-view]').forEach(b=>b.classList.remove('active'));btn.classList.add('active');
  const views={{today:3,week:7,month:31,quarter:92}};setZoom(views[btn.dataset.view]);
}}));
document.querySelectorAll('.order-bar').forEach(bar=>bar.addEventListener('click',()=>{{
  window.parent.postMessage({{
    isStreamlitMessage:true,
    type:'streamlit:setComponentValue',
    value:Number(bar.dataset.caseId),
  }}, '*');
}}));
requestAnimationFrame(()=>{{setZoom(31);}});
window.parent.postMessage({{
  isStreamlitMessage:true,
  type:'streamlit:setFrameHeight',
  height:{height},
}}, '*');
</script></body></html>'''
    selected_case_id = _timeline_component(
        document=document,
        height=height,
        key='dashboard_order_timeline',
        default=None,
    )
    try:
        return int(selected_case_id) if selected_case_id is not None else None
    except (TypeError, ValueError):
        return None
