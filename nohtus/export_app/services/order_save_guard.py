from __future__ import annotations

from html import escape
import re
import unicodedata

import pandas as pd
import streamlit as st

from nohtus.export_app import db
from nohtus.export_app.services import order_service
from nohtus.export_app.utils.dates import now_text


_original_save_order_items = order_service.save_order_items


def _clean_text(value: object) -> str:
    if value is None or pd.isna(value):
        return ''
    return str(value).strip()


def _safe_number(value: object, default: float = 0.0) -> float:
    if value is None or pd.isna(value) or value == '':
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_row_number(value: object, fallback: int) -> int:
    if value is None or pd.isna(value) or value == '':
        return fallback
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def with_row_numbers(frame: pd.DataFrame) -> pd.DataFrame:
    numbered = frame.copy().reset_index(drop=True)
    numbered['행번호'] = range(1, len(numbered) + 1)
    columns = ['행번호'] + [column for column in numbered.columns if column != '행번호']
    return numbered[columns]


def _normalized_name(value: object) -> str:
    name = _clean_text(value)
    if not name:
        return ''
    # 주문행 중복 여부는 검색/유사 제품 매칭보다 보수적으로 판단해야 한다.
    # 괄호와 숫자는 포장 규격을 나타내므로 제거하지 않는다. 예를 들어
    # ``니들 (1EA)``와 ``니들(20EA)``는 서로 다른 주문 제품이다.
    normalized = unicodedata.normalize('NFKC', name)
    normalized = normalized.replace('\u200b', '').replace('\ufeff', '')
    return re.sub(r'\s+', '', normalized).casefold()


def duplicate_groups(cleaned: pd.DataFrame) -> list[list[int]]:
    grouped: dict[str, list[int]] = {}
    for position, (_, row) in enumerate(cleaned.iterrows()):
        key = _normalized_name(row.get('제품명'))
        if key:
            grouped.setdefault(key, []).append(position)
    return [positions for positions in grouped.values() if len(positions) > 1]


def find_duplicate_rows(cleaned: pd.DataFrame) -> list[dict[str, object]]:
    """Return every editor row whose normalized product name appears more than once."""
    rows: list[dict[str, object]] = []
    for positions in duplicate_groups(cleaned):
        for position in positions:
            row = cleaned.iloc[position]
            rows.append({
                '행': _safe_row_number(row.get('행번호'), position + 1),
                '제품명': _clean_text(row.get('제품명')),
            })
    return rows


def merge_duplicate_rows(cleaned: pd.DataFrame) -> pd.DataFrame:
    """Keep the first duplicate row, sum quantities, and remove later rows."""
    merged = cleaned.copy().reset_index(drop=True)
    remove_positions: set[int] = set()

    for positions in duplicate_groups(merged):
        first_position = positions[0]
        total_quantity = sum(_safe_number(merged.iloc[position].get('수량')) for position in positions)
        merged.at[first_position, '수량'] = total_quantity
        remove_positions.update(positions[1:])

    if remove_positions:
        merged = merged.drop(index=sorted(remove_positions)).reset_index(drop=True)

    merged = merged.drop(columns=['행번호'], errors='ignore')
    return with_row_numbers(merged)


def render_duplicate_notice(rows: list[dict[str, object]]) -> None:
    """Show compact duplicate feedback directly beneath the order editor."""
    if not rows:
        return

    grouped: dict[str, list[int]] = {}
    for row in rows:
        name = _clean_text(row.get('제품명'))
        position = int(row.get('행', 0))
        grouped.setdefault(name, []).append(position)

    chips = ''.join(
        (
            '<span style="display:inline-flex;align-items:center;gap:0.35rem;'
            'padding:0.28rem 0.55rem;margin:0.18rem 0.22rem 0 0;'
            'border:1px solid #f3a8c5;border-radius:999px;'
            'background:#ffd6e7;color:#7a173f;font-weight:650;">'
            f'{escape(name)} · {", ".join(f"{position}행" for position in positions)}'
            '</span>'
        )
        for name, positions in grouped.items()
    )

    st.markdown(
        (
            '<div style="margin:0.35rem 0 0.5rem;padding:0.72rem 0.82rem;'
            'border:1px solid #f3a8c5;border-radius:0.65rem;background:#fff0f6;">'
            '<div style="color:#7a173f;font-weight:750;margin-bottom:0.28rem;">'
            '같은 제품명이 주문 목록에 중복되어 있습니다.'
            '</div>'
            '<div style="color:#8f3157;font-size:0.9rem;margin-bottom:0.25rem;">'
            '먼저 생성된 행의 제품명·단위·매입가를 유지하고 수량만 합칠 수 있습니다.'
            '</div>'
            f'<div>{chips}</div>'
            '</div>'
        ),
        unsafe_allow_html=True,
    )


def _database_snapshot(case_id: int) -> list[tuple]:
    rows = db.rows(
        '''SELECT id, product_name, quantity, unit, purchase_price
           FROM order_items
           WHERE case_id=?
           ORDER BY id''',
        (case_id,),
    )
    return [
        (
            int(row['id']),
            str(row['product_name'] or '').strip(),
            float(row['quantity'] or 0),
            str(row['unit'] or 'EA').strip() or 'EA',
            float(row['purchase_price'] or 0),
        )
        for row in rows
    ]


def reset_intake_order_editor_state(case_id: int) -> None:
    """Discard a stale intake-order draft so the editor reloads from the database."""
    draft_key = f'shipment_order_draft_{case_id}'
    version_key = f'shipment_order_editor_version_{case_id}'
    st.session_state.pop(draft_key, None)
    st.session_state[version_key] = int(st.session_state.get(version_key, 0)) + 1


def _after_order_change(case_id: int) -> None:
    case = db.row('SELECT stage, status, case_type FROM export_cases WHERE id=?', (case_id,))
    if (
        case
        and case['case_type'] != 'historical'
        and str(case['stage'] or '').strip() in {'패킹 완료', '국내배송'}
    ):
        db.execute(
            "UPDATE export_cases SET stage='패킹 대기', status='진행중', updated_at=? WHERE id=?",
            (now_text(), case_id),
        )
    from nohtus.export_app.services import shipment_service
    shipment_service.cleanup_invalid_links(case_id)
    shipment_service.sync_case_stage(case_id)

    reset_intake_order_editor_state(case_id)


def save_order_items(case_id: int, edited) -> None:
    """Validate, normalize, save, and synchronize downstream order views."""
    cleaned = edited.copy().drop(columns=['행번호'], errors='ignore')

    if '매입가' not in cleaned.columns:
        cleaned['매입가'] = 0.0
    cleaned['매입가'] = cleaned['매입가'].map(lambda value: _safe_number(value, 0.0))

    if '수량' in cleaned.columns:
        cleaned['수량'] = cleaned['수량'].map(lambda value: _safe_number(value, 0.0))

    duplicate_rows = find_duplicate_rows(cleaned)
    if duplicate_rows:
        render_duplicate_notice(duplicate_rows)
        st.stop()

    before = _database_snapshot(case_id)
    _original_save_order_items(case_id, cleaned)
    after = _database_snapshot(case_id)

    if before != after:
        _after_order_change(case_id)


def install() -> None:
    order_service.save_order_items = save_order_items
