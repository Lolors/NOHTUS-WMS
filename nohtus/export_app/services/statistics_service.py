from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from nohtus.export_app import db


STATISTICS_COLUMNS = [
    'case_id',
    '출고일자',
    '수출번호',
    '국가',
    '바이어',
    '제품명',
    '제조번호',
    '유통기한',
    '출고수량',
    '단위',
    'CTN 번호',
]


@st.cache_data(show_spinner=False, persist='disk', max_entries=64)
def _cached_shipment_rows(
    start_date: date,
    end_date: date,
    cache_token: tuple[int, int, int, int],
) -> pd.DataFrame:
    """Return actual shipment rows for completed and historical export cases."""
    rows = db.rows(
        '''
        SELECT
            c.id AS case_id,
            substr(c.actual_ship_date, 1, 10) AS ship_date,
            c.export_no,
            COALESCE(c.country, '') AS country,
            COALESCE(c.buyer, '') AS buyer,
            COALESCE(NULLIF(TRIM(s.product_name), ''), '') AS product_name,
            COALESCE(s.lot_no, '') AS lot_no,
            COALESCE(s.expiry_date, '') AS expiry_date,
            COALESCE(s.requested_qty, 0) AS shipped_qty,
            COALESCE(NULLIF(TRIM(o.unit), ''), 'EA') AS unit,
            s.box_no
        FROM export_cases c
        JOIN shipment_items s
          ON s.case_id = c.id
        LEFT JOIN order_items o
          ON o.id = s.order_item_id
         AND o.case_id = c.id
        WHERE c.status != '취소'
          AND TRIM(COALESCE(c.actual_ship_date, '')) != ''
          AND date(substr(c.actual_ship_date, 1, 10)) BETWEEN date(?) AND date(?)
          AND COALESCE(s.requested_qty, 0) > 0
        ORDER BY date(substr(c.actual_ship_date, 1, 10)) DESC, c.id DESC, s.id
        ''',
        (start_date.isoformat(), end_date.isoformat()),
    )

    if not rows:
        return pd.DataFrame(columns=STATISTICS_COLUMNS)

    frame = pd.DataFrame(
        [
            {
                'case_id': int(row['case_id']),
                '출고일자': str(row['ship_date'] or ''),
                '수출번호': str(row['export_no'] or ''),
                '국가': str(row['country'] or '').strip() or '미입력',
                '바이어': str(row['buyer'] or '').strip(),
                '제품명': str(row['product_name'] or '').strip() or '미입력',
                '제조번호': str(row['lot_no'] or '').strip(),
                '유통기한': str(row['expiry_date'] or '').strip(),
                '출고수량': float(row['shipped_qty'] or 0),
                '단위': str(row['unit'] or 'EA').strip() or 'EA',
                'CTN 번호': int(row['box_no']) if row['box_no'] is not None else pd.NA,
            }
            for row in rows
        ]
    )
    return frame[STATISTICS_COLUMNS]


def shipment_rows(start_date: date, end_date: date) -> pd.DataFrame:
    return _cached_shipment_rows(start_date, end_date, db.read_cache_token()).copy()


def normalize_text(value: object) -> str:
    return ''.join(str(value or '').strip().casefold().split())


def filter_rows(
    frame: pd.DataFrame,
    countries: list[str] | None = None,
    product_query: str = '',
) -> pd.DataFrame:
    filtered = frame.copy()

    if countries:
        filtered = filtered[filtered['국가'].isin(countries)]

    normalized_query = normalize_text(product_query)
    if normalized_query:
        filtered = filtered[
            filtered['제품명'].map(normalize_text).str.contains(normalized_query, regex=False)
        ]

    return filtered.reset_index(drop=True)


def packed_ctn_rows(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or 'CTN 번호' not in frame.columns:
        return pd.DataFrame(columns=['case_id', '출고일자', '국가', 'CTN 번호'])
    packed = frame.dropna(subset=['CTN 번호']).copy()
    if packed.empty:
        return pd.DataFrame(columns=['case_id', '출고일자', '국가', 'CTN 번호'])
    return packed.drop_duplicates(subset=['case_id', 'CTN 번호'])


def country_ctn_summary(frame: pd.DataFrame) -> pd.DataFrame:
    packed = packed_ctn_rows(frame)
    if packed.empty:
        return pd.DataFrame(columns=['국가', 'CTN 수량'])
    return (
        packed.groupby('국가', as_index=False)
        .size()
        .rename(columns={'size': 'CTN 수량'})
        .sort_values(['CTN 수량', '국가'], ascending=[False, True])
        .reset_index(drop=True)
    )


def monthly_ctn_summary(frame: pd.DataFrame) -> pd.DataFrame:
    packed = packed_ctn_rows(frame)
    if packed.empty:
        return pd.DataFrame(columns=['월', 'CTN 수량'])
    packed['월'] = packed['출고일자'].str.slice(0, 7)
    return (
        packed.groupby('월', as_index=False)
        .size()
        .rename(columns={'size': 'CTN 수량'})
        .sort_values('월')
        .reset_index(drop=True)
    )


def country_product_summary(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=['국가', '제품명', '단위', '출고수량', '출고건수'])

    summary = (
        frame.groupby(['국가', '제품명', '단위'], as_index=False)
        .agg(
            출고수량=('출고수량', 'sum'),
            출고건수=('case_id', 'nunique'),
        )
        .sort_values(['국가', '출고수량', '제품명'], ascending=[True, False, True])
        .reset_index(drop=True)
    )
    return summary


def product_country_summary(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=['제품명', '국가', '단위', '출고수량', '출고건수'])

    summary = (
        frame.groupby(['제품명', '국가', '단위'], as_index=False)
        .agg(
            출고수량=('출고수량', 'sum'),
            출고건수=('case_id', 'nunique'),
        )
        .sort_values(['제품명', '출고수량', '국가'], ascending=[True, False, True])
        .reset_index(drop=True)
    )
    return summary


def monthly_summary(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=['월', '단위', '출고수량'])

    monthly = frame.copy()
    monthly['월'] = monthly['출고일자'].str.slice(0, 7)
    return (
        monthly.groupby(['월', '단위'], as_index=False)['출고수량']
        .sum()
        .sort_values(['월', '단위'])
        .reset_index(drop=True)
    )
