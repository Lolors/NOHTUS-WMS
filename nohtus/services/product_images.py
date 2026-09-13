"""제품 이미지 경로 조회 (streamlit 미의존)."""

from __future__ import annotations

from pathlib import Path

from nohtus.db import q

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def get_product_image_path(product_name):
    df = q("SELECT image_path FROM products WHERE standard_name=? AND COALESCE(image_path, '') <> '' LIMIT 1", (product_name,))
    if df.empty:
        return ""
    value = str(df.iloc[0].get("image_path") or "").strip()
    if not value:
        return ""
    path = Path(value)
    if not path.is_absolute():
        path = _PROJECT_ROOT / path
    return str(path) if path.is_file() else ""
