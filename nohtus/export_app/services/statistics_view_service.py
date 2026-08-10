from __future__ import annotations

from datetime import date, timedelta

import pandas as pd


def month_start(value: date) -> date:
    return value.replace(day=1)


def previous_month_range(today: date) -> tuple[date, date]:
    end = month_start(today) - timedelta(days=1)
    return month_start(end), end


def preset_range(preset: str, today: date) -> tuple[date, date]:
    if preset == '지난 달':
        return previous_month_range(today)
    if preset == '최근 3개월':
        current_start = month_start(today)
        previous_end = current_start - timedelta(days=1)
        second_previous_end = month_start(previous_end) - timedelta(days=1)
        return month_start(second_previous_end), today
    if preset == '올해':
        return date(today.year, 1, 1), today
    return month_start(today), today


def integer_quantity(value: object) -> int:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return 0


def integer_quantities(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    if '출고수량' in result.columns:
        result['출고수량'] = result['출고수량'].map(integer_quantity)
    return result


def quantity_before_unit(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    if '출고수량' not in result.columns or '단위' not in result.columns:
        return result
    columns = [column for column in result.columns if column not in {'출고수량', '단위'}]
    insert_at = len(columns)
    for index, column in enumerate(columns):
        if column == '출고건수':
            insert_at = index
            break
    columns[insert_at:insert_at] = ['출고수량', '단위']
    return result[columns]


def integer_quantity_table(frame: pd.DataFrame) -> pd.DataFrame:
    return quantity_before_unit(integer_quantities(frame))


def quantity_text(frame: pd.DataFrame) -> str:
    if frame.empty:
        return '0'
    totals = frame.groupby('단위', as_index=False)['출고수량'].sum()
    return ' · '.join(
        f"{integer_quantity(row['출고수량']):,} {row['단위']}"
        for _, row in totals.iterrows()
    )


def csv_bytes(frame: pd.DataFrame) -> bytes:
    return integer_quantity_table(frame).to_csv(index=False).encode('utf-8-sig')
