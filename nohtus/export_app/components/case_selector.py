from __future__ import annotations

from collections.abc import Iterable

import streamlit as st


STAGE_LABELS = {
    '출고 대기': '패킹 대기',
}


def _text(value: object, fallback: str = '') -> str:
    text = str(value or '').strip()
    return text or fallback


def _stage_text(value: object, fallback: str = '') -> str:
    text = _text(value, fallback)
    return STAGE_LABELS.get(text, text)


def _set_valid_state(key: str, options: list, preferred=None) -> None:
    if not options:
        return
    current = st.session_state.get(key)
    if current in options:
        return
    st.session_state[key] = preferred if preferred in options else options[0]


def select_export_case(
    cases: Iterable,
    *,
    key_prefix: str,
    saved_case_id: int | None = None,
    show_stage: bool = True,
    show_transport: bool = False,
    case_label: str = 'export_no_transport',
    fixed_stage: str | None = None,
) -> int:
    """Select an export case through country, optional stage/transport, buyer, and case filters.

    case_label controls how the final case dropdown's options are formatted:
    'export_no_transport' (default) shows export_no + transport_mode; 'product_summary'
    shows export_no + a short summary of the order's product names instead.
    """
    case_list = list(cases)
    if fixed_stage is not None:
        normalized_stage = _text(fixed_stage)
        case_list = [case for case in case_list if _text(case['stage']) == normalized_stage]

    if not case_list:
        raise ValueError('선택할 수출 건이 없습니다.')

    case_by_id = {int(case['id']): case for case in case_list}
    saved_case = case_by_id.get(int(saved_case_id)) if saved_case_id is not None else None

    country_key = f'{key_prefix}_country'
    stage_key = f'{key_prefix}_stage'
    buyer_key = f'{key_prefix}_buyer'
    transport_key = f'{key_prefix}_transport'
    case_key = f'{key_prefix}_case'

    countries = sorted({_text(case['country'], '국가 미입력') for case in case_list})
    preferred_country = _text(saved_case['country'], '국가 미입력') if saved_case else None
    _set_valid_state(country_key, countries, preferred_country)

    column_count = 2 + int(show_stage) + int(show_transport) + 1
    columns = st.columns([1.2] + [1.2] * (column_count - 2) + [3.0])
    column_iter = iter(columns)
    country_col = next(column_iter)
    stage_col = next(column_iter) if show_stage else None
    buyer_col = next(column_iter)
    transport_col = next(column_iter) if show_transport else None
    case_col = next(column_iter)

    selected_country = country_col.selectbox('국가', countries, key=country_key)

    country_cases = [
        case for case in case_list
        if _text(case['country'], '국가 미입력') == selected_country
    ]

    if show_stage:
        stage_values = sorted({_text(case['stage'], '단계 미입력') for case in country_cases})
        preferred_stage = _text(saved_case['stage'], '단계 미입력') if saved_case in country_cases else None
        _set_valid_state(stage_key, stage_values, preferred_stage)
        selected_stage = stage_col.selectbox(
            '단계',
            stage_values,
            key=stage_key,
            format_func=lambda stage: _stage_text(stage, '단계 미입력'),
        )
        filtered_cases = [
            case for case in country_cases
            if _text(case['stage'], '단계 미입력') == selected_stage
        ]
    else:
        filtered_cases = country_cases

    buyers = sorted({_text(case['buyer'], '바이어 미입력') for case in filtered_cases})
    preferred_buyer = _text(saved_case['buyer'], '바이어 미입력') if saved_case in filtered_cases else None
    _set_valid_state(buyer_key, buyers, preferred_buyer)
    selected_buyer = buyer_col.selectbox('바이어', buyers, key=buyer_key)

    buyer_cases = [
        case for case in filtered_cases
        if _text(case['buyer'], '바이어 미입력') == selected_buyer
    ]

    if show_transport:
        transport_values = sorted({_text(case['transport_mode'], '운송방식 미입력') for case in buyer_cases})
        preferred_transport = (
            _text(saved_case['transport_mode'], '운송방식 미입력') if saved_case in buyer_cases else None
        )
        _set_valid_state(transport_key, transport_values, preferred_transport)
        selected_transport = transport_col.selectbox('운송방식', transport_values, key=transport_key)
        transport_cases = [
            case for case in buyer_cases
            if _text(case['transport_mode'], '운송방식 미입력') == selected_transport
        ]
    else:
        transport_cases = buyer_cases

    transport_cases.sort(key=lambda case: (_text(case['export_no']).casefold(), int(case['id'])))
    case_ids = [int(case['id']) for case in transport_cases]
    preferred_case_id = int(saved_case['id']) if saved_case in transport_cases else None
    _set_valid_state(case_key, case_ids, preferred_case_id)

    def _format_case(case_id: int) -> str:
        case = case_by_id[int(case_id)]
        if case_label == 'product_summary':
            from nohtus.export_app.services.dashboard_view_service import order_products_summary
            return ' · '.join(
                part for part in [_text(case['export_no']), order_products_summary(int(case_id))] if part
            )
        return ' · '.join(
            part for part in [_text(case['export_no']), _text(case['transport_mode'])] if part
        )

    selected_case_id = case_col.selectbox(
        '주문목록 요약' if case_label == 'product_summary' else '수출 건',
        case_ids,
        key=case_key,
        format_func=_format_case,
    )
    return int(selected_case_id)