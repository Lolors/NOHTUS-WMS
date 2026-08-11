from __future__ import annotations

import pandas as pd
import streamlit as st

from nohtus.export_app.services import dashboard_view_service


def render() -> None:
    st.title('수출 현황')
    st.markdown(
        """
        <style>
        [class*="st-key-export_dashboard_active_orders_panel"] {
            width: 60vw !important;
            max-width: 60vw !important;
        }
        @media (max-width: 900px) {
            [class*="st-key-export_dashboard_active_orders_panel"] {
                width: 100% !important;
                max-width: 100% !important;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.caption('진행 중인 수출 건 현황과 확인이 필요한 내용을 관리합니다.')

    st.markdown('### 진행 중인 수출 건')
    st.caption('국내배송 전이거나, 국내배송으로 넘어간 지 7일 이내인 건만 표시합니다.')
    cases = dashboard_view_service.active_and_recent_cases()
    if not cases:
        st.info('현재 표시할 수출 건이 없습니다.')
    else:
        case_ids = [int(case['id']) for case in cases]
        progress_by_case = dashboard_view_service.intake_progress_percentages(case_ids)
        status_rows = [
            {
                '국가': case['country'] or '-',
                '바이어': case['buyer'] or '미지정',
                '운송방식': case['transport_mode'] or '미지정',
                '단계': dashboard_view_service.stage_label(case['stage']),
                '입고 진행률': f"{progress_by_case.get(int(case['id']), 0.0):.0f}%",
                '주문목록': dashboard_view_service.summarize_product_names(case['product_names']),
            }
            for case in cases
        ]
        status_df = pd.DataFrame(status_rows)
        styled_status = status_df.style.apply(
            lambda row: [dashboard_view_service.stage_style(row['단계'])] * len(row),
            axis=1,
        )
        with st.container(key='export_dashboard_active_orders_panel'):
            st.dataframe(
                styled_status,
                hide_index=True,
                use_container_width=True,
                key='export_dashboard_active_orders',
            )
