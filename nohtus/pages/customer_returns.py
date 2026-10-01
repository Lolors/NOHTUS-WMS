"""Customer-return entry shared by outbound search and statement history."""
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
import uuid
import json
import sqlite3
import pandas as pd
import streamlit as st
from nohtus.auth import can_access_page
from nohtus.locations import parse_location
from nohtus.services import customer_returns as service


def open_statement_return(statement_id):
    for key in ('return_customer_search','return_product_search','return_source_거래명세서 반품'):
        st.session_state.pop(key,None)
    st.session_state['_customer_return_statement']=str(statement_id)
    st.session_state['_customer_return_mode']='거래명세서 반품'
    st.session_state['_top_app_mode']='wms'
    st.session_state['app_mode_switch']=False
    st.session_state['page']='반품 입고'


def _location_picker(prefix, cols=None):
    allowed=service.valid_locations()
    areas=sorted({parse_location(loc)[0] for loc in allowed})
    if cols is None:cols=st.columns(2)
    area=cols[0].selectbox('입고 구역',areas,index=areas.index('REC') if 'REC' in areas else 0,key=prefix+'_area')
    locations=sorted(loc for loc in allowed if parse_location(loc)[0]==area)
    return cols[1].selectbox('입고 로케이션',locations,key=prefix+'_location')


def _source_label(row):
    reference=f"출고 #{row['order_id']}" if row.get('order_id') else f"명세서 {row.get('statement_number') or row.get('statement_id')} / {row.get('sequence')}행"
    return f"{row.get('customer','')} · {row['product_name']} · {row['lot']} · {row['exp_date']} · 미입고 {row['remaining_qty']} · {reference}"


def _entry(source):
    prefix='customer_return_'+source['source_kind']+'_'+service._hash([source['source_key'],source['fingerprint'],source['remaining_qty']])[:18]
    st.info(f"제조번호: {source['lot']} · 유통기한: {source['exp_date']}")
    cols=st.columns(3)
    cols[0].metric('원출고 / 반품 처리 수량',source['total_qty'])
    cols[1].metric('반품 입고 완료',source['returned_qty'])
    cols[2].metric('반품 입고 가능',source['remaining_qty'])
    if source['remaining_qty']<=0:
        st.success('이 내역의 반품 가능 수량을 모두 입고했습니다.')
        return
    company=st.selectbox('반품 입고 사업장',service.COMPANIES,index=service.COMPANIES.index(service.COMPANY),key=prefix+'_company')
    outbound_key=None;factor='1';product=source['product_name']
    if source['source_kind']=='statement':
        catalog=service.product_catalog(company);names=sorted({r['standard_name'] for r in catalog})
        suggested=sorted({r['standard_name'] for r in catalog if source['product_name'] in (r['standard_name'],r['erp_name']) or (source.get('product_code') and source['product_code']==r['product_code'])})
        selected=st.selectbox('WMS 표준제품명',names,index=names.index(suggested[0]) if len(suggested)==1 else None,placeholder='반품 제품과 동일한 WMS 제품을 선택하세요',key=prefix+'_product')
        if not selected:return
        product=selected
        st.caption(f"명세서 제품: {source['product_name']} / 단위: {source.get('packaging_unit') or '미기재'}. WMS 제품의 포장 단위를 확인하세요.")
        factor=st.text_input('명세서 1단위당 WMS 수량',value='1',key=prefix+'_factor',help='같은 단위면 1. 명세서 낱개 5개가 WMS 1박스면 0.2를 입력합니다.')
        candidates=[r for r in service.outbound_sources(product=product) if r['product_name']==product and r['lot']==source['lot'] and r['exp_date']==source['exp_date'] and service.customer_matches(source['customer'],r['customer'])]
        if candidates:
            options={r['source_key']:r for r in candidates}
            outbound_key=st.selectbox('연결할 원출고',list(options),index=None,format_func=lambda key:_source_label(options[key]),placeholder='해당 고객에게 판매한 원출고를 선택하세요',key=prefix+'_outbound')
            if not outbound_key:return
            st.caption(f"선택한 원출고의 반품 입고 가능 수량: {options[outbound_key]['remaining_qty']} (WMS 단위)")
        else:
            st.caption('동일 거래처·제품·제조번호·유통기한의 WMS 출고 내역이 없습니다. 거래명세서를 원본으로 연결해 입고합니다.')
    else:
        st.write(f'**입고 제품: {product}**')
    quantity=st.number_input('이번 반품 입고수량'+(' (명세서 단위)' if source['source_kind']=='statement' else ' (WMS 단위)'),min_value=1,max_value=int(source['remaining_qty']),value=int(source['remaining_qty']),step=1,key=prefix+'_qty')
    valid=False
    try:
        converted=service._qty(Decimal(quantity)*service._positive(factor,'환산계수'))
        st.write(f'**WMS 재고 반영: {converted:,}개**')
        valid=True
    except (ValueError,InvalidOperation):
        st.error('환산 후 WMS 수량은 1 이상의 정수가 되어야 합니다.')
    if st.button('반품 목록에 담기',disabled=not valid,key=prefix+'_add'):
        cart=st.session_state.setdefault('_customer_return_cart',[])
        item=dict(company=company,kind=source['source_kind'],key=source['source_key'],fingerprint=source['fingerprint'],source_qty=quantity,product_name=product,factor=factor,outbound_key=outbound_key)
        existing=next((r for r in cart if (r['item']['kind'],r['item']['key'],r['item']['company'])==(item['kind'],item['key'],company)),None)
        item['request_token']=str(uuid.uuid4())
        row=dict(item=item,customer=source.get('customer',''),lot=source['lot'],exp_date=source['exp_date'],qty=converted)
        if existing is not None:
            cart[cart.index(existing)]=row
        else:
            cart.append(row)
        st.session_state['_customer_return_success']='반품 목록에 담았습니다. 같은 내역·사업장을 다시 담으면 수량이 변경됩니다.'
        st.rerun()


def _cart():
    cart=st.session_state.get('_customer_return_cart',[])
    st.divider()
    st.subheader(f'반품 입고 목록 ({len(cart)}건)')
    st.caption('제품별 사업장과 수량을 담은 뒤 공통 입고 정보를 입력하세요. 담기만 하면 재고는 변경되지 않습니다.')
    if not cart:
        st.info('반품할 제품을 목록에 담아 주세요.')
    rows=[{'거래처':r['customer'],'입고 사업장':r['item']['company'],'표준제품명':r['item']['product_name'],'제조번호':r['lot'],'유통기한':r['exp_date'],'원본 수량':r['item']['source_qty'],'WMS 수량':r['qty'],'연결 제품명':r['item'].get('mapping_name','기존 매칭 사용')} for r in cart]
    st.dataframe(pd.DataFrame(rows),hide_index=True,use_container_width=True)
    tokens={r['item']['request_token']:r for r in cart}
    selected=st.multiselect('목록에서 제외할 제품',list(tokens),format_func=lambda k:f"{tokens[k]['item']['company']} · {tokens[k]['item']['product_name']} · {tokens[k]['lot']} · {tokens[k]['qty']}개",key='return_cart_remove')
    if st.button('선택 제품 빼기',disabled=not selected):
        st.session_state['_customer_return_cart']=[r for r in cart if r['item']['request_token'] not in selected]
        st.session_state.pop('return_cart_remove',None)
        st.rerun()
    with st.container(key='return_common_panel'):
        st.subheader('공통 입고 정보')
        fields=st.columns([1,1.2,1.3,1.8],gap='small')
        location=_location_picker('return_cart',fields[:2])
        received_day=fields[2].date_input('실물 반품 입고일',value=date.today(),max_value=date.today(),key='return_cart_date')
        memo=fields[3].text_input('반품 사유 / 메모',key='return_cart_memo')
        st.caption('공통 입고 정보가 목록 전체에 적용됩니다. 실제 도착하고 검수가 끝난 정상 제품만 완료하세요.')
        with st.container(horizontal=True,horizontal_alignment='center'):
            submit=st.button('반품 입고 완료',type='primary',disabled=not cart,key='return_cart_submit')
    if submit:
        try:
            ids=service.receive_returns([r['item'] for r in cart],location=location,receipt_date=received_day,memo=memo)
        except (ValueError,RuntimeError,sqlite3.Error) as exc:
            st.error(f'입고하지 못했습니다. 목록 전체가 저장되지 않았습니다: {exc}')
        else:
            st.session_state['_customer_return_cart']=[]
            st.session_state.pop('return_cart_remove',None)
            st.session_state['_customer_return_success']=f'반품 {len(ids)}건 입고 완료 / {sum(r["qty"] for r in cart):,}개 / {location}'
            st.rerun()



def _history():
    rows=[row for row in service.receipt_history() if row['status']=='received']
    if not rows:
        st.info('반품 입고 내역이 없습니다.');return
    for row in rows:
        source=json.loads(row['source_snapshot'])
        row['customer']=source.get('customer','')
        row['reference']=(f"명세서 {row['statement_id']} / {row['statement_sequence']}행" if row['source_kind']=='statement' else f"출고 #{row['outbound_order_id']}")
    labels={'id':'번호','customer':'거래처','reference':'원본 내역','receipt_date':'입고일','company':'입고 사업장','product_name':'표준제품명','lot':'제조번호','exp_date':'유통기한','qty':'WMS 수량','location':'로케이션','status':'상태','memo':'메모'}
    frame=pd.DataFrame(rows)[list(labels)].rename(columns=labels)
    frame['상태']=frame['상태'].map({'received':'입고 완료','cancelled':'입고 취소'})
    frame.insert(0,'선택',False)
    revision=service._hash([(r['id'],r['status']) for r in rows])[:16]
    with st.form('return_history_cancel_'+revision):
        edited=st.data_editor(frame,hide_index=True,use_container_width=True,num_rows='fixed',
            key='return_history_selection_'+revision,disabled=list(labels.values()),
            column_config={'선택':st.column_config.CheckboxColumn('선택',help='취소할 입고에 체크하세요.')})
        submit=st.form_submit_button('선택 반품 입고 취소')
    selected=edited.loc[edited['선택'],'번호'].tolist()
    active={r['id'] for r in rows if r['status']=='received'}
    invalid=any(value not in active for value in selected)
    if invalid:st.warning('이미 취소된 내역은 다시 취소할 수 없습니다. 해당 행의 체크를 해제하세요.')
    st.caption('취소할 행을 체크한 뒤 버튼을 누르세요. 해당 로케이션의 재고를 차감하고 반품 입고 가능 수량을 복구합니다. 여러 건 중 취소할 수 없는 내역이 있으면 전체 취소가 적용되지 않습니다.')
    if submit and not invalid:
        try:service.cancel_returns(selected)
        except (ValueError,sqlite3.Error) as exc:st.error(str(exc))
        else:
            st.session_state['_customer_return_success']=f'반품 입고 {len(selected)}건을 취소했습니다.'
            st.rerun()



def page_customer_returns():
    if not can_access_page('반품 입고'):
        st.warning('반품 입고 권한이 없습니다.');return
    st.markdown('''<style>
    .st-key-return_search_panel, .st-key-return_common_panel {
        width:50vw;max-width:100%;
    }
    @media(max-width:900px) {
        .st-key-return_search_panel, .st-key-return_common_panel {width:100%;}
    }
    </style>''',unsafe_allow_html=True)
    st.title('반품 입고')
    st.caption('고객에게 판매했던 제품을 돌려받습니다.')
    if '_customer_return_success' in st.session_state:st.success(st.session_state.pop('_customer_return_success'))
    mode=st.radio('반품 원본',['WMS 출고 내역','거래명세서 반품','반품 입고 내역'],format_func=lambda value: {'WMS 출고 내역':'WMS 저장된 출고지시','거래명세서 반품':'발주관리 거래명세서'}.get(value,value),horizontal=True,key='_customer_return_mode')
    if mode=='반품 입고 내역':_history();return
    _search_entries(mode)
    _cart()


def _search_entries(mode):
    panel=st.container(key='return_search_panel')
    cols=panel.columns([1,1,2],gap='small') if mode=='거래명세서 반품' else panel.columns(2)
    customer=cols[0].text_input('거래처 검색',key='return_customer_search')
    product=cols[1].text_input('제품 검색',key='return_product_search')
    try:
        if mode=='WMS 출고 내역':
            dates=panel.columns(2)
            start=dates[0].date_input('출고 시작일',value=date.today()-timedelta(days=365),key='return_search_start')
            end=dates[1].date_input('출고 종료일',value=date.today(),key='return_search_end')
            if start>end:st.error('출고 기간을 확인하세요.');return
            sources=service.outbound_sources(customer=customer,product=product,start=start,end=end)
        else:
            statement_id=st.session_state.get('_customer_return_statement')
            if statement_id:
                st.caption(f'선택 거래명세서: {statement_id}')
                if st.button('전체 거래명세서 반품 보기'):
                    st.session_state.pop('_customer_return_statement',None);st.rerun()
            all_sources=service.statement_sources(statement_id)
            matched={r['purchase_order_id'] or 'statement:'+r['statement_id'] for r in all_sources if customer.casefold() in r['customer'].casefold() and product.casefold() in r['product_name'].casefold()}
            sources=[r for r in all_sources if (r['purchase_order_id'] or 'statement:'+r['statement_id']) in matched]
    except (ValueError,RuntimeError,sqlite3.Error) as exc:
        st.error(str(exc));return
    if not sources:st.info('조건에 맞는 내역이 없습니다.');return
    if mode=='거래명세서 반품':
        _statement_orders(sources,selector=cols[2])
        return
    options={r['source_key']:r for r in sources}
    selected=panel.selectbox('반품할 내역',list(options),index=None,format_func=lambda k:_source_label(options[k]),placeholder='제품·제조번호·유통기한을 확인하고 선택하세요',key='return_source_'+mode)
    if selected:_entry(options[selected])


def _order_label(rows):
    row=rows[0]
    try:day=date.fromisoformat(str(row['purchase_order_date'])[:10]).strftime('%Y년 %m월 %d일')
    except (ValueError,TypeError):day=str(row['purchase_order_date'] or '날짜 미기재')
    reference='주문번호 '+row['purchase_order_id'] if row['purchase_order_id'] else '주문 미연결 · 명세서 '+row['statement_id']
    available=sum(r['remaining_qty']>0 for r in rows)
    return f"{day} · {reference} · {row['customer']} · 반품 가능 {available}품목"


def _statement_table_rows(sources,company):
    catalog=service.product_catalog(company)
    result=[]
    for source in sources:
        standard=source['product_name']
        names=sorted({r['erp_name'] for r in catalog if r['standard_name']==standard and r['erp_name']})
        result.append({'선택':False,'명세서':source['statement_id'],'행':source['sequence'],'WMS 표준제품명':standard,'연결 제품명':names[0] if len(names)==1 else (standard if not names else ''), '제조번호':source['lot'],'유통기한':source['exp_date'],'단위':source.get('packaging_unit',''),'반품수량':source['total_qty'],'입고완료':source['returned_qty'],'입고가능':source['remaining_qty'],'입고수량':source['remaining_qty']})
    return result


def _prepare_statement_selection(sources,records,company):
    catalog=service.product_catalog(company)
    prepared=[]
    for source,row in zip(sources,records):
        if not row['선택']:continue
        quantity=service._qty(row['입고수량'])
        if quantity>source['remaining_qty']:raise ValueError('입고 가능 수량을 초과한 제품이 있습니다.')
        standard=str(row['WMS 표준제품명'] or '').strip();name=str(row['연결 제품명'] or '').strip()
        if not standard or not name:raise ValueError('선택 제품의 WMS 표준제품명과 연결 제품명을 입력하세요.')
        before=sorted({r['erp_name'] for r in catalog if r['standard_name']==standard and r['erp_name']})
        item=dict(kind='statement',key=source['source_key'],fingerprint=source['fingerprint'],source_qty=quantity,product_name=standard,company=company,factor='1',outbound_key=None,mapping_name=name,mapping_before=before,request_token=str(uuid.uuid4()))
        prepared.append(dict(item=item,customer=source['customer'],lot=source['lot'],exp_date=source['exp_date'],qty=quantity))
    if not prepared:raise ValueError('장바구니에 담을 제품에 체크해 주세요.')
    return prepared


def _statement_orders(sources, selector=None):
    groups={}
    for source in sources:
        key=source['purchase_order_id'] or 'statement:'+source['statement_id']
        groups.setdefault(key,[]).append(source)
    groups={key:rows for key,rows in groups.items() if any(r['remaining_qty']>0 for r in rows)}
    if st.session_state.get('return_statement_order') not in groups:
        st.session_state.pop('return_statement_order',None)
    if not groups:
        st.info('반품 입고 가능한 주문이 없습니다.')
        return
    selected=(selector if selector is not None else st).selectbox('반품할 주문',list(groups),index=None,format_func=lambda key:_order_label(groups[key]),placeholder='주문일·주문번호로 선택하세요',key='return_statement_order')
    if selected is None:return
    sources=groups[selected]
    company=st.selectbox('반품 입고 사업장',service.COMPANIES,index=0,key='return_statement_company')
    st.caption(f'체크한 제품만 담습니다. 연결 제품명은 {company}에서 사용하는 이름입니다. 최종 반품 입고 완료 시 제품매칭표에도 저장됩니다. 명세서 수량 그대로 입고합니다.')
    rows=_statement_table_rows(sources,company)
    revision=service._hash([selected,company,rows])[:16]
    state_key='return_order_rows_'+revision
    version_key='return_order_version_'+revision
    rows=st.session_state.get(state_key,rows)
    version=st.session_state.get(version_key,0)
    with st.form('return_order_form_'+revision):
        with st.container(horizontal=True, gap='small'):
            select_all=st.form_submit_button('모두 선택')
            clear_all=st.form_submit_button('선택 해제')
        edited=st.data_editor(pd.DataFrame(rows),hide_index=True,use_container_width=True,num_rows='fixed',key='return_order_editor_'+revision+'_'+str(version),
            disabled=['명세서','행','제조번호','유통기한','단위','반품수량','입고완료','입고가능'],
            column_config={'선택':st.column_config.CheckboxColumn('선택'), '연결 제품명':st.column_config.TextColumn(f'{company} 연결 제품명'), '입고수량':st.column_config.NumberColumn(min_value=0,step=1)})
        submit=st.form_submit_button('선택 제품 장바구니에 담기')
    if select_all or clear_all:
        records=edited.to_dict('records')
        for row in records:row['선택']=bool(select_all and row['입고가능']>0)
        st.session_state[state_key]=records
        st.session_state[version_key]=version+1
        st.rerun()
    if submit:
        st.session_state[state_key]=edited.to_dict('records')
        try:prepared=_prepare_statement_selection(sources,edited.to_dict('records'),company)
        except (ValueError,InvalidOperation) as exc:st.error(str(exc));return
        cart=list(st.session_state.get('_customer_return_cart',[]))
        for row in prepared:
            item=row['item']
            cart=[r for r in cart if (r['item']['kind'],r['item']['key'],r['item']['company'])!=(item['kind'],item['key'],company)]
            cart.append(row)
        st.session_state['_customer_return_cart']=cart
        st.session_state['_customer_return_success']=f'{len(prepared)}개 제품을 반품 목록에 담았습니다.'
        st.rerun()
