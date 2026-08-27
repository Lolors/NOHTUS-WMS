from __future__ import annotations

import pandas as pd
import streamlit as st


UNIT_OPTIONS = ['BOX', 'PK', 'EA']


def order_editor(dataframe, *, key: str, dynamic: bool = True):
    dataframe = dataframe.copy()
    if '1단위당 EA' not in dataframe.columns:
        dataframe['1단위당 EA'] = 1.0
    if '제품명' in dataframe.columns:
        dataframe['제품명'] = dataframe['제품명'].fillna('').astype('string')
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
            # 빈 입력행을 시작점으로 쓰므로 required=True를 지정하면 다른
            # 텍스트/숫자 셀을 먼저 편집해 Enter를 누를 때 행 전체가 무효화된다.
            # 제품명 필수 검증은 저장 시점(order_service.save_order_items)에 처리한다.
            '제품명': st.column_config.TextColumn('제품명'),
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
    dataframe = dataframe.copy()
    # DB 값이 전부 비어 있으면 Streamlit이 열을 숫자/unknown 형식으로
    # 추론해 첫 텍스트 입력을 되돌리는 경우가 있으므로 입력 열 형식을 고정한다.
    for column in ('출고처', '제품명', '제조번호', '유효기간'):
        if column not in dataframe.columns:
            dataframe[column] = pd.Series('', index=dataframe.index, dtype='string')
        else:
            dataframe[column] = dataframe[column].fillna('').astype('string')
    return st.data_editor(
        dataframe,
        num_rows='dynamic',
        hide_index=True,
        use_container_width=True,
        key=key,
        column_order=['출고처', '제품명', '제조번호', '유효기간', '수량', '단위', '매입가', 'CTN 번호'],
        column_config={
            '출고처': st.column_config.TextColumn('출고처'),
            # 빈 입력행을 시작점으로 쓰므로 required=True를 지정하면 다른
            # 텍스트 셀을 먼저 편집해 Enter를 누를 때 행 전체가 무효화된다.
            # 제품명 필수 검증은 저장 시점에 처리한다.
            '제품명': st.column_config.TextColumn('제품명'),
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
