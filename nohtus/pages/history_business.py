from __future__ import annotations

import streamlit as st

from nohtus.pages.history import page_history as _page_history
from nohtus.services.inventory import backfill_missing_transaction_final_stock


def page_history():
    try:
        updated = backfill_missing_transaction_final_stock()
        if updated:
            st.caption(f"최종재고 누락 이력 {updated:,}건을 보정했습니다.")
    except Exception as e:
        st.warning(f"최종재고 보정 중 오류가 발생했습니다: {e}")
    return _page_history()
