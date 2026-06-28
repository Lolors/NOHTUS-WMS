"""Runtime compatibility patches for NOHTUS WMS.

Streamlit imports this module automatically when the app starts from the
repository root. Keep patches narrow and defensive.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

try:
    import streamlit as st
except Exception:  # pragma: no cover - only relevant at Streamlit runtime
    st = None


_DB_PATH = Path(__file__).parent / "data" / "nohtus.db"


def _load_inbound_product_labels() -> dict[str, str]:
    """Return display labels that include ERP names while values stay standard names."""
    if not _DB_PATH.exists():
        return {}
    try:
        with sqlite3.connect(_DB_PATH) as con:
            rows = con.execute(
                """
                SELECT standard_name, warehouse_name, aliases,
                       erp_nohtuspharm_name, erp_nohtus_name, erp_noh_name, bidata_name
                FROM products
                ORDER BY standard_name
                """
            ).fetchall()
    except Exception:
        return {}

    labels: dict[str, str] = {}
    for row in rows:
        standard = str(row[0] or "").strip()
        if not standard:
            continue
        extras = []
        seen = {standard}
        for value in row[1:]:
            text = str(value or "").strip()
            if text and text.lower() != "nan" and text not in seen:
                extras.append(text)
                seen.add(text)
        labels[standard] = f"{standard} / {' / '.join(extras)}" if extras else standard
    return labels


def _patch_inbound_selectbox() -> None:
    if st is None or getattr(st, "_nohtus_inbound_erp_search_patched", False):
        return

    original_selectbox = st.selectbox

    def patched_selectbox(label, options, *args, **kwargs):
        key = kwargs.get("key")
        if label == "제품" and key == "inbound_product":
            labels = _load_inbound_product_labels()
            original_format_func = kwargs.get("format_func")

            def inbound_format_func(value):
                if value == "":
                    if original_format_func:
                        return original_format_func(value)
                    return "제품명을 입력하거나 선택하세요"
                return labels.get(str(value), str(value))

            kwargs["format_func"] = inbound_format_func
        return original_selectbox(label, options, *args, **kwargs)

    st.selectbox = patched_selectbox
    st._nohtus_inbound_erp_search_patched = True


_patch_inbound_selectbox()
