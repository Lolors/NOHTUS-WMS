from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from nohtus.export_app.services import export_confirm_service
from nohtus.export_app.views.주문_검색_및_수정 import render_wms_confirmation_section

RECENT_DAYS = 30


def render() -> None:
    st.title('수출확정 매출 등록')
    st.markdown(
        """
        <style>
        [class*="st-key-export_sales_registration_orders"] {
            width: 70vw !important;
            max-width: 70vw !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.caption(
        '수출대기 저장이 끝난 품목의 ERP 매출 사업장과 수출처를 선택해 확정합니다. '
        '표준제품명 옆의 출고사업장 ERP명을 참고해 ERP에서 제품을 검색하세요.'
    )

    orders = export_confirm_service.list_active_orders()
    if orders.empty:
        st.info('조회할 수출대기 저장 건이 없습니다.')
        return

    # 확정 건은 시간이 지날수록 계속 쌓이므로 기본은 최근 1개월만 보여준다.
    # 아직 매출 등록이 필요한 수출대기/일부 확정 건은 오래됐어도 항상 보여준다.
    show_recent_only = st.checkbox(
        f'최근 {RECENT_DAYS}일 확정 건만 보기',
        value=True,
        key='export_sales_registration_recent_only',
    )
    if show_recent_only:
        cutoff = (date.today() - timedelta(days=RECENT_DAYS)).isoformat()
        needs_action = orders['status'].isin(['waiting', 'partial'])
        is_recent = orders['order_date'].fillna('').astype(str).str[:10] >= cutoff
        orders = orders[needs_action | is_recent]
        if orders.empty:
            st.info(f'최근 {RECENT_DAYS}일 내 확정 건이 없습니다. 체크박스를 해제하면 전체를 볼 수 있습니다.')
            return

    duplicate_export_nos = orders['export_no'][orders['export_no'].duplicated(keep=False)].dropna().unique()
    if len(duplicate_export_nos):
        st.error(
            '같은 수출번호에 진행 중인 실재고 연결 건이 여러 개입니다: '
            + ', '.join(map(str, duplicate_export_nos))
            + '. 주문을 병합하거나 새 수출번호를 사용하세요.'
        )

    def confirmation_label(count: int, label: str) -> str:
        return str(label) if int(count) == 1 else f'{int(count)}곳'

    table = pd.DataFrame({
        '_id': orders['id'].astype(int),
        '상태': orders['status'].map({
            'waiting': '수출대기',
            'partial': '일부 확정',
            'confirmed': '수출확정',
        }).fillna(orders['status']),
        '수출번호': orders['export_no'],
        '국가': orders['country'],
        '바이어': orders['buyer'].fillna(''),
        '운송방식': orders['transport_method'].fillna(''),
        '주문 요약': orders['order_summary'],
        '확정사업장': [confirmation_label(count, label) for count, label in zip(
            orders['confirmed_company_count'], orders['confirmed_company_label']
        )],
        '확정매출처': [confirmation_label(count, label) for count, label in zip(
            orders['confirmed_customer_count'], orders['confirmed_customer_label']
        )],
    })

    def status_cell_color(value: object) -> str:
        return {
            '수출확정': 'background-color: #dcfce7; color: #166534; font-weight: 700;',
            '수출대기': 'background-color: #dff3ff; color: #075f85; font-weight: 700;',
        }.get(str(value), '')

    styled_table = table.style.map(status_cell_color, subset=['상태'])
    event = st.dataframe(
        styled_table,
        hide_index=True,
        use_container_width=True,
        on_select='rerun',
        selection_mode='single-row',
        column_config={'_id': None},
        key='export_sales_registration_orders',
    )
    if not event.selection.rows:
        st.info('매출 등록할 수출번호를 선택하세요.')
        return

    selected = table.iloc[int(event.selection.rows[0])]
    export_no = str(selected['수출번호'] or '').strip()
    if export_no in set(map(str, duplicate_export_nos)):
        st.warning('중복된 수출번호는 병합하거나 새 번호로 변경한 뒤 확정할 수 있습니다.')
        return

    render_wms_confirmation_section(
        export_no,
        shipment_date_label='등록일자',
        shipment_date_help='이번에 선택한 품목에 적용할 등록일자를 선택하세요.',
    )
