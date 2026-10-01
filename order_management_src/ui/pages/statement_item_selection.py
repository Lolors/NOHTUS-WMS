"""가로 스크롤 없이 전체 너비에 맞추는 거래명세서 품목 선택 표."""
import html
import streamlit as st
import streamlit.components.v2 as components

COLUMNS = [("선택",4),("입고발주ID",10),("발주일자",10),("제품코드",8),
           ("제품명",27),("규격",12),("포장단위",8),("발주수량",7),("누적입고",7),("남은수량",7)]


@st.cache_resource
def _component():
    return components.component(
        "statement_item_selection_fit",
        html='<div class="item-selection-root"></div>',
        css="""
        .item-selection-root {width:100%;max-height:420px;overflow-y:auto;overflow-x:hidden;border:1px solid #e2e8f0;border-radius:6px;box-sizing:border-box;}
        table {width:100%;table-layout:fixed;border-collapse:collapse;font-size:13px;color:#1e293b;}
        th,td {padding:8px 4px;border-bottom:1px solid #e2e8f0;text-align:left;white-space:normal;overflow-wrap:anywhere;vertical-align:middle;}
        th {position:sticky;top:0;background:#f8fafc;z-index:1;}
        th:first-child,td:first-child {text-align:center;padding-left:0;padding-right:0;}
        input[type=checkbox] {width:14px;height:14px;max-width:100%;margin:0;accent-color:#2563eb;cursor:pointer;}
        tr:has(input:checked) {background:#eff6ff;}
        tbody tr:hover {background:#f1f5f9;}
        """,
        js="""
        export default function(component) {
            const root = component.parentElement.querySelector('.item-selection-root');
            root.innerHTML = component.data;
            const change = (event) => {
                if (event.target.dataset.all === 'true') {
                    root.querySelectorAll('input[data-id]').forEach(input => input.checked = event.target.checked);
                }
                const selected = Array.from(root.querySelectorAll('input[data-id]:checked'), input => input.dataset.id);
                component.setTriggerValue('selected', selected);
            };
            root.addEventListener('change', change);
            return () => root.removeEventListener('change', change);
        }
        """,
    )


def _table(frame, selected):
    cols = ''.join(f'<col style="width:{width}%">' for _,width in COLUMNS)
    all_checked = len(selected)==len(frame) and len(frame)>0
    headers = '<th><input type="checkbox" data-all="true" aria-label="전체 품목 선택" '+('checked' if all_checked else '')+'></th>'
    headers += ''.join(f'<th>{"발주서" if name=="입고발주ID" else name}</th>' for name,_ in COLUMNS[1:])
    rows=[]
    for _,row in frame.iterrows():
        id=str(int(row['품목번호']))
        cells=f'<td><input type="checkbox" data-id="{id}" aria-label="품목 {id} 선택" '+('checked' if id in selected else '')+'></td>'
        for name,_ in COLUMNS[1:]:
            value=row.get(name, '')
            if name in ('발주수량','누적입고','남은수량'):
                value=f'{float(value):g}'
            text=html.escape(str(value),quote=True)
            cells+=f'<td title="{text}">{text}</td>'
        rows.append('<tr>'+cells+'</tr>')
    return '<table><colgroup>'+cols+'</colgroup><thead><tr>'+headers+'</tr></thead><tbody>'+''.join(rows)+'</tbody></table>'


def render(frame, order_key):
    key=f'statement_item_selection_ids_{order_key}'
    valid={str(int(value)) for value in frame['품목번호']}
    selected=set(st.session_state.get(key,[])) & valid
    event=_component()(data=_table(frame,selected),key=f'statement_item_selection_fit_{order_key}',on_selected_change=lambda:None)
    if event.selected is not None:
        incoming=set(map(str,event.selected)) & valid
        if incoming != selected:
            st.session_state[key]=sorted(incoming)
            st.rerun()
    result=frame.copy()
    result['선택']=result['품목번호'].map(lambda value:str(int(value)) in selected)
    return result
