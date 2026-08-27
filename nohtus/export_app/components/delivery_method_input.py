from __future__ import annotations

import streamlit as st


DELIVERY_TYPE_OPTIONS = ['택배', '퀵', '핸드캐리']
COURIER_OPTIONS = ['로젠택배', 'CJ택배', 'DHL', '우체국택배']


def delivery_method_input(*, saved_method: str = '', key_prefix: str) -> str:
    """Render delivery type and courier choices, returning the stored method value."""
    normalized = str(saved_method or '').strip()
    if normalized in COURIER_OPTIONS or normalized == '택배':
        saved_type = '택배'
    elif normalized in {'퀵', '퀵배송'}:
        saved_type = '퀵'
    elif normalized == '핸드캐리':
        saved_type = '핸드캐리'
    else:
        saved_type = '택배'

    delivery_type = st.radio(
        '배송 방식',
        DELIVERY_TYPE_OPTIONS,
        index=DELIVERY_TYPE_OPTIONS.index(saved_type),
        horizontal=True,
        key=f'{key_prefix}_type',
    )
    if delivery_type == '택배':
        saved_courier = normalized if normalized in COURIER_OPTIONS else COURIER_OPTIONS[0]
        return st.selectbox(
            '택배사',
            COURIER_OPTIONS,
            index=COURIER_OPTIONS.index(saved_courier),
            key=f'{key_prefix}_courier',
        )
    if delivery_type == '퀵':
        return '퀵배송'
    return '핸드캐리'


def is_courier_delivery(method: str) -> bool:
    return str(method or '').strip() in COURIER_OPTIONS
