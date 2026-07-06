from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from nohtus.db import connect
from nohtus.pages.history import page_history as _page_history
from nohtus.services.inventory import backfill_missing_transaction_final_stock


def _normalize_created_at(value):
    text = str(value or "").strip()
    if not text:
        raise ValueError("일시는 비워둘 수 없습니다.")
    parsed = pd.to_datetime(text, errors="coerce")
    if pd.isna(parsed):
        raise ValueError(f"일시 형식을 확인하세요: {text}")
    return parsed.strftime("%Y-%m-%d %H:%M:%S")


def _display_row_to_tx_id(cur, row, used_ids):
    created_at = str(row.get("일시") or "").strip()
    tx_type = str(row.get("이력유형") or "").strip()
    product_name = str(row.get("제품명") or "").strip()
    lot = str(row.get("LOT") or "").strip()
    exp_date = str(row.get("유통기한") or "").strip()
    memo = str(row.get("메모") or "").strip()
    if not created_at or not tx_type or not product_name:
        return None
    rows = cur.execute(
        """
        SELECT id
        FROM transactions
        WHERE created_at=?
          AND tx_type=?
          AND product_name=?
          AND IFNULL(lot, '')=?
          AND IFNULL(exp_date, '')=?
          AND IFNULL(memo, '')=?
        ORDER BY id DESC
        """,
        (created_at, tx_type, product_name, lot, exp_date, memo),
    ).fetchall()
    for raw in rows:
        tx_id = int(raw[0])
        if tx_id not in used_ids:
            used_ids.add(tx_id)
            return tx_id
    return None


def _update_history_dates(original_df, edited_df):
    if not isinstance(original_df, pd.DataFrame) or not isinstance(edited_df, pd.DataFrame):
        return 0
    if "일시" not in original_df.columns or "일시" not in edited_df.columns:
        return 0

    changed_indexes = []
    for idx in range(min(len(original_df), len(edited_df))):
        before = str(original_df.iloc[idx].get("일시") or "").strip()
        after = str(edited_df.iloc[idx].get("일시") or "").strip()
        if before != after:
            changed_indexes.append(idx)
    if not changed_indexes:
        return 0

    with connect() as con:
        cur = con.cursor()
        used_ids = set()
        row_to_id = {}
        for idx in range(len(original_df)):
            tx_id = _display_row_to_tx_id(cur, original_df.iloc[idx], used_ids)
            if tx_id is not None:
                row_to_id[idx] = tx_id

        updated = 0
        now_ids = []
        for idx in changed_indexes:
            tx_id = row_to_id.get(idx)
            if tx_id is None:
                continue
            new_created_at = _normalize_created_at(edited_df.iloc[idx].get("일시"))
            cur.execute("UPDATE transactions SET created_at=? WHERE id=?", (new_created_at, tx_id))
            updated += 1
            now_ids.append(tx_id)
        con.commit()
    if changed_indexes and updated == 0:
        raise ValueError("수정할 이력 행을 찾지 못했습니다. 같은 내용의 중복 이력이 있으면 조건을 좁혀 다시 시도하세요.")
    return updated


def page_history():
    original_data_editor = st.data_editor

    def patched_data_editor(data, *args, **kwargs):
        if kwargs.get("key") == "history_admin_delete_editor" and isinstance(data, pd.DataFrame):
            disabled = kwargs.get("disabled")
            if isinstance(disabled, list):
                kwargs["disabled"] = [c for c in disabled if c != "일시"]
            edited = original_data_editor(data, *args, **kwargs)
            try:
                updated = _update_history_dates(data, edited)
                if updated:
                    st.success(f"이력 일시 {updated}건을 수정했습니다.")
                    st.rerun()
            except Exception as e:
                st.error(str(e))
            return edited
        return original_data_editor(data, *args, **kwargs)

    st.data_editor = patched_data_editor
    try:
        try:
            updated = backfill_missing_transaction_final_stock()
            if updated:
                st.caption(f"최종재고 누락 이력 {updated:,}건을 보정했습니다.")
        except Exception as e:
            st.warning(f"최종재고 보정 중 오류가 발생했습니다: {e}")
        return _page_history()
    finally:
        st.data_editor = original_data_editor
