from __future__ import annotations
from datetime import date
import streamlit as st
import streamlit.components.v2 as components
from nohtus.export_app.services import statistics_service as stats
from nohtus.export_app.services.statistics_order_table import order_table_html, order_summary_html
from nohtus.export_app.services.statistics_view_service import csv_bytes, integer_quantity_table, preset_range, previous_month_range


@st.cache_resource
def order_component():
    return components.component(
        "statistics_order_navigation",
        html='<p class="navigation-help">이전·다음 버튼으로 검색한 제품이 포함된 주문을 한 건씩 확인하세요.</p><div class="navigation"><button class="previous">이전 일치</button><span class="position"></span><button class="next">다음 일치</button></div><div class="orders"></div>',
        css="""
        .navigation{position:relative;background:#f8fafc;padding:10px;z-index:2;display:flex;gap:15px;align-items:center;justify-content:center;flex-wrap:wrap}
        .navigation-help{text-align:center;margin:6px 0;color:#64748b;font-size:13px}.order-metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:12px 0}.order-metrics>div{border:1px solid #dbe4ef;border-radius:10px;padding:15px;text-align:center}.order-metrics strong{display:block;font-size:24px;margin-top:6px}
        button{padding:7px 12px;border:1px solid #cbd5e1;border-radius:6px;background:white;cursor:pointer}button:disabled{opacity:.45;cursor:default}
        section{border:1px solid #cbd5e1;border-radius:9px;padding:16px;margin:12px 0;color:#183153}h4{margin:0}p{font-size:13px;color:#64748b}
        .orders{max-height:65vh;overflow:auto;overscroll-behavior:contain;scroll-behavior:smooth}.table-scroll{overflow:visible}table{border-collapse:collapse;width:100%;font-size:13px}td,th{padding:9px;border:1px solid #e2e8f0;text-align:left}th{background:#f1f5f9;position:sticky;top:0}td.highlight{background:#fff4b8;color:#1f2937}.current td.highlight{outline:2px solid #d6a520;outline-offset:-2px}tr{scroll-margin-top:100px}
        """,
        js="""
        export default function({parentElement,data}) {
            const viewport=parentElement.querySelector('.orders');
            viewport.innerHTML=data.html;

            const rows=[...viewport.querySelectorAll('section')];
            let index=0;
            const label=parentElement.querySelector('.position');
            const prev=parentElement.querySelector('.previous'), next=parentElement.querySelector('.next');
            prev.disabled=next.disabled=!rows.length;
            function move(delta,scroll=true){
                if(!rows.length){label.textContent='주문 없음';return;}
                index=(index+delta+rows.length)%rows.length;
                rows.forEach((row,i)=>{row.hidden=i!==index;});
                label.textContent=`${index+1} / ${rows.length}건 주문`;
                if(scroll)viewport.scrollTo({top:0,left:0,behavior:'instant'});
            }
            const back=()=>move(-1), forward=()=>move(1);
            prev.addEventListener('click',back);next.addEventListener('click',forward);
            move(0,false);
            return ()=>{prev.removeEventListener('click',back);next.removeEventListener('click',forward);};
        }
        """,
    )


def show_table(frame, filename):
    frame = integer_quantity_table(frame)
    st.dataframe(frame, hide_index=True, use_container_width=True)
    st.download_button('통계 CSV 다운로드', csv_bytes(frame), file_name=filename, mime='text/csv', key=filename)


def render():
    st.markdown("""<style>
    .st-key-export_statistics_area {width:60%;max-width:60%;}
    .st-key-export_statistics_area [data-testid="stMetric"] {background:#fff;border:1px solid #dbe4ef;border-radius:16px;padding:16px;}
    .order-summary-list{margin:0;color:#183153;background:transparent;padding:0;overflow:auto;}
    .st-key-statistics_search_panel{background:#fff;border:1px solid #dbe4ef;border-radius:12px;padding:20px;box-sizing:border-box;margin-bottom:18px;}
    .st-key-statistics_order_search{background:transparent!important;border:0!important;padding:0!important;}
    .st-key-statistics_order_search [data-testid="stForm"]{background:transparent!important;border:0!important;padding:0!important;}
    .order-summary-heading{font-size:16px;margin-bottom:10px;}
    .order-summary-list table{width:100%;border-collapse:collapse;font-size:14px;}
    .order-summary-list th,.order-summary-list td{text-align:left;padding:9px 12px;border-bottom:1px solid #edf0f5;}
    .order-summary-list th{background:#f8fafc;color:#64748b;font-weight:500;}
    .order-summary-list tr:last-child td{border-bottom:0;}
    @media(max-width:1000px){.st-key-export_statistics_area {width:100%;max-width:100%;}}
    </style>""", unsafe_allow_html=True)
    with st.container(key='export_statistics_area'):
        _render_statistics()


def _render_statistics():
    st.title('기간별 통계')
    st.caption('실제 출고일 기준입니다. 기간은 공통으로 적용하고 각 탭의 검색 조건은 따로 사용합니다.')
    cols=st.columns([1.2,1,1])
    preset=cols[0].selectbox('조회 기간',['이번 달','지난 달','최근 3개월','올해','직접 선택'])
    if preset=='직접 선택':
        start,end=previous_month_range(date.today())
        start=cols[1].date_input('시작일',value=start);end=cols[2].date_input('종료일',value=end)
    else:
        start,end=preset_range(preset,date.today())
        cols[1].text_input('시작일',value=start.isoformat(),disabled=True)
        cols[2].text_input('종료일',value=end.isoformat(),disabled=True)
    if start>end:
        st.error('시작일은 종료일보다 늦을 수 없습니다.');return
    rows=stats.shipment_rows(start,end)
    if rows.empty:
        st.info('선택한 기간에 출고 데이터가 없습니다.');return
    countries=sorted(rows['국가'].dropna().unique().tolist())
    orders,top,product=st.tabs(['주문별 카톤 조회','국가별 수출 TOP10 제품','특정 제품 국가별 수출내역'])
    with orders:
        with st.container(key='statistics_search_panel'):
            search_col,summary_col=st.columns([2,3],gap='large')
            with search_col:
                with st.form('statistics_order_search',border=False):
                    query=st.text_input('포함된 제품명',placeholder='제품명 일부를 입력하세요',key='statistics_order_query')
                    selected=st.multiselect('국가',countries,placeholder='전체 국가',key='statistics_order_countries')
                    with st.container(horizontal=True,horizontal_alignment='center'):
                        submitted=st.form_submit_button('주문 검색',type='primary')
            if submitted:
                st.session_state['statistics_search_nonce']=st.session_state.get('statistics_search_nonce',0)+1
            filtered=stats.filter_rows(rows,countries=selected,product_query=query,include_case_rows=True)
            with summary_col:
                if filtered.empty:
                    st.info('조건에 맞는 주문이 없습니다.')
                else:
                    st.markdown(order_summary_html(filtered),unsafe_allow_html=True)
        if not filtered.empty:
            html=order_table_html(filtered,query)
            if html:
                nonce=st.session_state.get('statistics_search_nonce',0)
                order_component()(data={'html':html,'token':str(nonce) if nonce and query.strip() else ''},key='statistics_order_tables')
            else:st.info('패킹 완료 카톤이 없습니다.')
    with top:
        country=st.selectbox('국가 선택',countries,key='statistics_top_country')
        ranking=stats.country_product_summary(rows[rows['국가']==country])
        units=sorted(ranking['단위'].dropna().unique().tolist())
        if len(units)>1:
            unit=st.selectbox('수량 단위',units,key='statistics_top_unit')
            ranking=ranking[ranking['단위']==unit]
        ranking=ranking.sort_values(['출고수량','제품명'],ascending=[False,True]).head(10).reset_index(drop=True)
        st.caption('제품 검색과 무관하게, 선택한 국가의 출고수량 상위 10개 제품입니다. 서로 다른 단위는 분리합니다.')
        if not ranking.empty:st.bar_chart(ranking,x='제품명',y='출고수량',horizontal=True,sort='-출고수량')
        show_table(ranking,f'국가별_TOP10_{start}_{end}.csv')
    with product:
        term=st.text_input('제품 검색',placeholder='예: 루나',key='statistics_exact_query')
        if not term.strip():st.info('제품명을 검색한 뒤 비교할 제품을 선택하세요.')
        else:
            candidates=stats.filter_rows(rows,product_query=term)
            names=sorted(candidates['제품명'].dropna().unique().tolist())
            if not names:st.info('검색한 제품의 출고내역이 없습니다.')
            else:
                name=st.selectbox('제품 선택',names,key='statistics_exact_product')
                result=stats.product_country_summary(rows[rows['제품명']==name])
                st.caption('선택한 제품만 국가별로 합산합니다. 같은 주문의 다른 제품은 포함하지 않습니다.')
                for unit,group in result.groupby('단위'):
                    st.markdown(f'**출고수량 ({unit})**')
                    st.bar_chart(group,x='국가',y='출고수량',horizontal=True,sort='-출고수량')
                show_table(result,f'특정제품_국가별_{start}_{end}.csv')
