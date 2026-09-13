"""Location map service with product-photo and export-waiting grouping support."""

from __future__ import annotations

import base64
import json
import logging
import mimetypes
from pathlib import Path

import streamlit as st

from nohtus.db import q
from nohtus.db import read_cache_token as _wms_read_cache_token
from nohtus.services.export_waiting import ensure_export_waiting_tables
from nohtus.services.product_images import get_product_image_path
from . import location_map_legacy as _legacy
from .location_map_new_layout import apply_new_layout

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_THUMB_DIR = _PROJECT_ROOT / "data" / "product_images" / "thumbs"

__all__ = ["get_product_image_path", "render_location_map", "product_thumbnail_uris_for"]

_logger = logging.getLogger(__name__)


def _patch(html, target, replacement, label):
    """location_map_legacy.py의 출력에 문자열 치환으로 기능을 덧붙인다.

    target이 원본에서 사라지면(예: legacy 템플릿 리팩토링) str.replace()는
    조용히 아무 일도 안 하고 넘어가버린다 — 실제로 이렇게 수출대기 P존
    카드 그룹핑 패치가 한동안 죽어 있었다. 매치 여부를 로그로 남겨서
    다음엔 조용히 묻히지 않게 한다.
    """
    if target not in html:
        _logger.warning("location_map enhanced_html: patch %r target not found, skipped", label)
        return html
    return html.replace(target, replacement, 1)


def _product_thumbnail_data_uris():
    images = {}
    rows = q("SELECT standard_name, MAX(image_path) AS image_path FROM products WHERE COALESCE(image_path, '') <> '' GROUP BY standard_name")
    if rows.empty:
        return images
    encoded_by_path = {}
    for row in rows.itertuples():
        name = str(row.standard_name or "").strip()
        raw_path = str(row.image_path or "").strip()
        if not name or not raw_path:
            continue
        original = Path(raw_path)
        if not original.is_absolute():
            original = _PROJECT_ROOT / original
        thumb = _THUMB_DIR / f"{original.stem}.jpg"
        path = thumb if thumb.is_file() else None
        if path is None:
            continue
        cache_key = str(path.resolve())
        data_uri = encoded_by_path.get(cache_key)
        if data_uri is None:
            mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
            try:
                encoded = base64.b64encode(path.read_bytes()).decode("ascii")
            except OSError:
                continue
            data_uri = f"data:{mime};base64,{encoded}"
            encoded_by_path[cache_key] = data_uri
        images[name] = data_uri
    return images


@st.cache_data(show_spinner=False, persist='disk', max_entries=1024)
def _cached_image_data_uri(path_str: str, cache_token) -> str:
    path = Path(path_str)
    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    try:
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    except OSError:
        return ""
    return f"data:{mime};base64,{encoded}"


def product_thumbnail_uris_for(product_names) -> dict:
    unique_names = list(dict.fromkeys(str(name).strip() for name in product_names if str(name or "").strip()))
    if not unique_names:
        return {}
    placeholders = ",".join("?" for _ in unique_names)
    rows = q(f"SELECT standard_name, image_path FROM products WHERE standard_name IN ({placeholders}) AND COALESCE(image_path,'')<>''", tuple(unique_names))
    if rows.empty:
        return {}
    cache_token = _wms_read_cache_token()
    result = {}
    for row in rows.itertuples():
        name = str(row.standard_name or "").strip()
        raw_path = str(row.image_path or "").strip()
        if not name or not raw_path:
            continue
        original = Path(raw_path)
        if not original.is_absolute():
            original = _PROJECT_ROOT / original
        thumb = _THUMB_DIR / f"{original.stem}.jpg"
        chosen = thumb if thumb.is_file() else (original if original.is_file() else None)
        if chosen is not None:
            result[name] = _cached_image_data_uri(str(chosen), cache_token)
    return result


def _export_waiting_groups():
    try:
        ensure_export_waiting_tables()
        rows = q("""
            SELECT o.id AS order_id, o.country, o.buyer, o.transport_method, o.title,
                   i.company, i.product_name, i.warehouse_name, i.lot, i.exp_date,
                   i.qty, i.waiting_location
            FROM export_waiting_orders o
            JOIN export_waiting_items i ON i.order_id=o.id
            WHERE o.status IN ('waiting','partial') AND i.waiting_location='P' AND COALESCE(i.confirmed,0)=0
            ORDER BY o.country, o.created_at, o.id, i.id
        """)
    except Exception:
        return []
    if rows.empty:
        return []
    result = []
    for row in rows.to_dict("records"):
        clean = {}
        for key, value in row.items():
            if value is None:
                clean[key] = ""
            elif key in {"order_id", "qty"}:
                clean[key] = int(value or 0)
            else:
                clean[key] = str(value)
        result.append(clean)
    return result


def render_location_map():
    product_images = json.dumps(_product_thumbnail_data_uris(), ensure_ascii=False)
    export_waiting = json.dumps(_export_waiting_groups(), ensure_ascii=False)
    original_html = _legacy.components.html

    def enhanced_html(html, *args, **kwargs):
        html = _patch(
            html,
            "const txData = DATA.tx || [];",
            f"const rawTxData = DATA.tx || [];\nconst txData = rawTxData.filter(t => !String(t.tx_type || '').includes('재고조사불러오기') && !String(t.memo || '').includes('재고조사불러오기'));\nconst productImages = {product_images};\nconst exportWaitingItems = {export_waiting};",
            "inject productImages/exportWaitingItems",
        )
        html = _patch(
            html,
            ".prod-box{border-top:1px solid #e2e8f0;margin-top:14px;padding-top:14px;text-align:center;} .photo-box{width:150px;height:150px;margin:0 auto 10px;border:1px dashed #cbd5e1;border-radius:16px;background:#f8fafc;display:flex;align-items:center;justify-content:center;color:#94a3b8;font-weight:700;}",
            ".prod-box{border-top:1px solid #e2e8f0;margin-top:14px;padding-top:14px;text-align:center;} .photo-box{width:150px;height:150px;margin:0 auto 10px;border:1px dashed #cbd5e1;border-radius:16px;background:#f8fafc;display:flex;align-items:center;justify-content:center;color:#94a3b8;font-weight:700;overflow:hidden;} .photo-box img{width:100%;height:100%;object-fit:cover;object-position:center;display:block;}",
            "photo-box overflow css",
        )
        html = _patch(
            html,
            '<div class="photo-box">📷</div>',
            '<div class="photo-box">${productImages[name] ? `<img src="${productImages[name]}" alt="${esc(name)}">` : "📷"}</div>',
            "photo-box image markup",
        )
        html = _patch(
            html,
            "function productCardsHtml(rows){",
            """function exportWaitingCardsHtml(fallbackRows){
  const orders={};
  exportWaitingItems.forEach(item=>{const key=String(item.order_id||'');if(!key)return;if(!orders[key])orders[key]={country:item.country||'-',buyer:item.buyer||'미지정',transport_method:item.transport_method||'미지정',items:[]};orders[key].items.push(item);});
  const entries=Object.values(orders).sort((a,b)=>String(a.country||'').localeCompare(String(b.country||''),'ko')||String(a.buyer||'').localeCompare(String(b.buyer||''),'ko')||String(a.transport_method||'').localeCompare(String(b.transport_method||''),'ko'));
  if(!entries.length)return productCardsHtml(fallbackRows||[]);
  return entries.map(order=>{const total=order.items.reduce((sum,item)=>sum+(Number(item.qty)||0),0);const productGroups={};order.items.forEach(item=>{const name=item.product_name||'-';if(!productGroups[name])productGroups[name]=[];productGroups[name].push(item);});const products=Object.entries(productGroups).map(([name,items])=>{const qty=items.reduce((sum,item)=>sum+(Number(item.qty)||0),0);const lines=items.map(item=>`<div class="lot-exp">${esc(item.company||'-')} · ${Number(item.qty)||0}EA&nbsp;&nbsp;${esc(item.lot||'-')} | ${esc(cleanDate(item.exp_date||'-'))}</div>`).join('');return `<div class="export-product-row"><div class="card-top"><span class="product-title">${esc(name)}</span><span class="qty-text">${qty} EA</span></div>${lines}</div>`;}).join('');return `<div class="detail-card export-order-card"><div class="export-order-title">${esc(order.country)}-${esc(order.buyer)}-${esc(order.transport_method)}</div><div class="muted">남은 수출대기 총수량: ${total} EA</div>${products}</div>`;}).join('');
}
function productCardsHtml(rows){""",
            "define exportWaitingCardsHtml",
        )
        html = _patch(
            html,
            "html+=productCardsHtml(rows);",
            "html+=(loc==='P' ? exportWaitingCardsHtml(rows) : productCardsHtml(rows));",
            "wire P-zone card grouping into showDetail",
        )
        html = _patch(
            html,
            "</style>",
            ".export-order-card{border:1.5px solid #c7d2fe;background:#f8faff;padding:14px;margin-bottom:14px}.export-order-title{font-size:18px;font-weight:800;color:#1e3a8a;margin-bottom:5px}.export-product-row{border-top:1px solid #dbeafe;margin-top:12px;padding-top:12px}.export-product-row:first-of-type{border-top:0;margin-top:8px;padding-top:0}</style>",
            "export-order-card css",
        )
        html = apply_new_layout(html)
        return original_html(html, *args, **kwargs)

    _legacy.components.html = enhanced_html
    try:
        return _legacy.render_location_map()
    finally:
        _legacy.components.html = original_html
