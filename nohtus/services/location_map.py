"""Location map service with product-photo support."""

from __future__ import annotations

import base64
import json
import mimetypes
from pathlib import Path

from nohtus.db import q
from . import location_map_legacy as _legacy

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def get_product_image_path(product_name):
    df = q("SELECT image_path FROM products WHERE standard_name=?", (product_name,))
    if df.empty:
        return ""
    value = str(df.iloc[0].get("image_path") or "").strip()
    if not value:
        return ""
    path = Path(value)
    if not path.is_absolute():
        path = _PROJECT_ROOT / path
    return str(path) if path.is_file() else ""


def _product_image_data_uris():
    images = {}
    rows = q("SELECT standard_name, image_path FROM products WHERE COALESCE(image_path, '') <> ''")
    if rows.empty:
        return images
    for row in rows.itertuples():
        name = str(row.standard_name or "").strip()
        path = Path(str(row.image_path or "").strip())
        if not path.is_absolute():
            path = _PROJECT_ROOT / path
        if not name or not path.is_file():
            continue
        mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
        try:
            encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        except OSError:
            continue
        images[name] = f"data:{mime};base64,{encoded}"
    return images


def render_location_map():
    product_images = json.dumps(_product_image_data_uris(), ensure_ascii=False)
    original_html = _legacy.components.html

    def photo_html(html, *args, **kwargs):
        html = html.replace(
            "const txData = DATA.tx || [];",
            f"const txData = DATA.tx || [];\nconst productImages = {product_images};",
            1,
        )
        html = html.replace(
            ".prod-box{border-top:1px solid #e2e8f0;margin-top:14px;padding-top:14px;text-align:center;} .photo-box{width:150px;height:150px;margin:0 auto 10px;border:1px dashed #cbd5e1;border-radius:16px;background:#f8fafc;display:flex;align-items:center;justify-content:center;color:#94a3b8;font-weight:700;}",
            ".prod-box{border-top:1px solid #e2e8f0;margin-top:14px;padding-top:14px;text-align:center;} .photo-box{width:150px;height:150px;margin:0 auto 10px;border:1px dashed #cbd5e1;border-radius:16px;background:#f8fafc;display:flex;align-items:center;justify-content:center;color:#94a3b8;font-weight:700;overflow:hidden;} .photo-box img{width:100%;height:100%;object-fit:contain;display:block;}",
            1,
        )
        html = html.replace(
            '<div class="photo-box">📷</div>',
            '<div class="photo-box">${productImages[name] ? `<img src="${productImages[name]}" alt="${esc(name)}">` : "📷"}</div>',
            1,
        )
        return original_html(html, *args, **kwargs)

    _legacy.components.html = photo_html
    try:
        return _legacy.render_location_map()
    finally:
        _legacy.components.html = original_html
