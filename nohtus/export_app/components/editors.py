from __future__ import annotations

import streamlit as st


UNIT_OPTIONS = ['BOX', 'PK', 'EA']


def order_editor(dataframe, *, key: str, dynamic: bool = True):
    dataframe = dataframe.copy()
    if '1단위당 EA' not in dataframe.columns:
        dataframe['1단위당 EA'] = 1.0
    return st.data_editor(
        dataframe,
        num_rows='dynamic' if dynamic else 'fixed',
        hide_index=True,
        use_container_width=True,
        key=key,
        column_order=['행번호', '제품명', '수량', '단위', '1단위당 EA', '매입가'],
        disabled=['행번호'],
        column_config={
            '_id': None,
            '행번호': st.column_config.NumberColumn('행', format='%d', width='small'),
            '제품명': st.column_config.TextColumn('제품명', required=True),
            '수량': st.column_config.NumberColumn('수량', min_value=0.0, step=1.0, width=30),
            '단위': st.column_config.SelectboxColumn(
                '단위',
                options=UNIT_OPTIONS,
                default='EA',
                required=True,
                width=30,
            ),
            '1단위당 EA': st.column_config.NumberColumn(
                '1단위당 EA',
                min_value=0.000001,
                step=1.0,
                default=1.0,
                help='예: 1 BOX가 50 EA이면 50을 입력하세요. EA 단위는 1입니다.',
            ),
            '매입가': st.column_config.NumberColumn(
                '매입가',
                min_value=0.0,
                step=100.0,
                format='₩ %,.0f',
                help='제품 1개(입력 단위 기준)의 매입 단가입니다.',
            ),
        },
    )


def historical_order_editor(dataframe, *, key: str):
    return st.data_editor(
        dataframe,
        num_rows='dynamic',
        hide_index=True,
        use_container_width=True,
        key=key,
        column_order=['출고처', '제품명', '제조번호', '유효기간', '수량', '단위', '매입가', 'CTN 번호'],
        column_config={
            '출고처': st.column_config.TextColumn('출고처'),
            '제품명': st.column_config.TextColumn('제품명', required=True),
            '제조번호': st.column_config.TextColumn('제조번호'),
            '유효기간': st.column_config.TextColumn('유효기간', help='예: 2028-06-30'),
            '수량': st.column_config.NumberColumn('수량', min_value=0.0, step=1.0),
            '단위': st.column_config.SelectboxColumn(
                '단위',
                options=UNIT_OPTIONS,
                default='EA',
                required=True,
            ),
            '매입가': st.column_config.NumberColumn(
                '매입가',
                min_value=0.0,
                step=100.0,
                format='₩ %,.0f',
            ),
            'CTN 번호': st.column_config.NumberColumn('CTN 번호', min_value=1, step=1),
        },
    )


def historical_box_editor(dataframe, *, key: str):
    return st.data_editor(
        dataframe,
        num_rows='dynamic',
        hide_index=True,
        use_container_width=True,
        key=key,
        column_order=['CTN 번호', '가로 (cm)', '세로 (cm)', '높이 (cm)', 'GW (kg)'],
        column_config={
            'CTN 번호': st.column_config.NumberColumn('CTN 번호', min_value=1, step=1, required=True),
            '가로 (cm)': st.column_config.NumberColumn('가로 (cm)', min_value=0.0, step=0.1),
            '세로 (cm)': st.column_config.NumberColumn('세로 (cm)', min_value=0.0, step=0.1),
            '높이 (cm)': st.column_config.NumberColumn('높이 (cm)', min_value=0.0, step=0.1),
            'GW (kg)': st.column_config.NumberColumn('GW (kg)', min_value=0.0, step=0.1),
        },
    )


def shipment_editor(dataframe, *, key: str):
    return st.data_editor(
        dataframe,
        num_rows='dynamic',
        hide_index=True,
        use_container_width=True,
        key=key,
        column_config={
            '_id': None,
        },
    )
