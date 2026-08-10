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
    fixed_stage: str | None = None,
) -> int:
    """Select an export case through country, optional stage, buyer, and case filters."""
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
    case_key = f'{key_prefix}_case'

    countries = sorted({_text(case['country'], '국가 미입력') for case in case_list})
    preferred_country = _text(saved_case['country'], '국가 미입력') if saved_case else None
    _set_valid_state(country_key, countries, preferred_country)

    if show_stage:
        country_col, stage_col, buyer_col, case_col = st.columns([1.2, 1.2, 1.5, 3.0])
    else:
        country_col, buyer_col, case_col = st.columns([1.2, 1.5, 3.0])
        stage_col = None

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
    buyer_cases.sort(key=lambda case: (_text(case['export_no']).casefold(), int(case['id'])))
    case_ids = [int(case['id']) for case in buyer_cases]
    preferred_case_id = int(saved_case['id']) if saved_case in buyer_cases else None
    _set_valid_state(case_key, case_ids, preferred_case_id)

    selected_case_id = case_col.selectbox(
        '수출 건',
        case_ids,
        key=case_key,
        format_func=lambda case_id: ' · '.join(
            part
            for part in [
                _text(case_by_id[int(case_id)]['export_no']),
                _text(case_by_id[int(case_id)]['transport_mode']),
            ]
            if part
        ),
    )
    return int(selected_case_id)