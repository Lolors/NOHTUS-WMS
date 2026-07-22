"""Location map service with product-photo and export-waiting grouping support."""

from __future__ import annotations

import json
from pathlib import Path

from nohtus.db import q
from nohtus.services.export_waiting import ensure_export_waiting_tables
from . import location_map_legacy as _legacy

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def get_product_image_path(product_name):
    df = q(
        """
        SELECT image_path
        FROM products
        WHERE standard_name=?
          AND COALESCE(image_path, '') <> ''
        LIMIT 1
        """,
        (product_name,),
    )
    if df.empty:
        return ""
    value = str(df.iloc[0].get("image_path") or "").strip()
    if not value:
        return ""
    path = Path(value)
    if not path.is_absolute():
        path = _PROJECT_ROOT / path
    return str(path) if path.is_file() else ""


def _export_waiting_groups():
    try:
        ensure_export_waiting_tables()
        rows = q(
            """
            SELECT o.id AS order_id, o.country, o.buyer, o.transport_method, o.title,
                   i.company, i.product_name, i.warehouse_name, i.lot, i.exp_date,
                   i.qty, i.waiting_location
            FROM export_waiting_orders o
            JOIN export_waiting_items i ON i.order_id=o.id
            WHERE o.status IN ('waiting','partial')
              AND i.waiting_location='P'
              AND COALESCE(i.confirmed,0)=0
            ORDER BY o.country, o.created_at, o.id, i.id
            """
        )
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
    """Render the map without preloading product image bytes.

    Product photos are available in the product search view. The map detail panel
    intentionally keeps a lightweight placeholder so opening the map does not read
    and embed every uploaded image into one large HTML payload.
    """
    export_waiting = json.dumps(_export_waiting_groups(), ensure_ascii=False)
    original_html = _legacy.components.html

    def enhanced_html(html, *args, **kwargs):
        html = html.replace(
            "const txData = DATA.tx || [];",
            f"const rawTxData = DATA.tx || [];\nconst txData = rawTxData.filter(t => !String(t.tx_type || '').includes('재고조사불러오기') && !String(t.memo || '').includes('재고조사불러오기'));\nconst exportWaitingItems = {export_waiting};",
            1,
        )
        html = html.replace(
            "function productCardsHtml(rows){",
            """function exportWaitingCardsHtml(fallbackRows){
  const orders={};
  exportWaitingItems.forEach(item=>{
    const key=String(item.order_id||'');
    if(!key) return;
    if(!orders[key]) orders[key]={country:item.country||'-',buyer:item.buyer||'미지정',transport_method:item.transport_method||'미지정',items:[]};
    orders[key].items.push(item);
  });
  const entries=Object.values(orders).sort((a,b)=>
    String(a.country||'').localeCompare(String(b.country||''),'ko') ||
    String(a.buyer||'').localeCompare(String(b.buyer||''),'ko') ||
    String(a.transport_method||'').localeCompare(String(b.transport_method||''),'ko')
  );
  if(!entries.length) return productCardsHtml(fallbackRows||[]);
  return entries.map(order=>{
    const total=order.items.reduce((sum,item)=>sum+(Number(item.qty)||0),0);
    const productGroups={};
    order.items.forEach(item=>{
      const name=item.product_name||'-';
      if(!productGroups[name]) productGroups[name]=[];
      productGroups[name].push(item);
    });
    const products=Object.entries(productGroups).map(([name,items])=>{
      const qty=items.reduce((sum,item)=>sum+(Number(item.qty)||0),0);
      const lines=items.map(item=>`<div class="lot-exp">${esc(item.company||'-')} · ${Number(item.qty)||0}EA&nbsp;&nbsp;${esc(item.lot||'-')} | ${esc(cleanDate(item.exp_date||'-'))}</div>`).join('');
      return `<div class="export-product-row"><div class="card-top"><span class="product-title">${esc(name)}</span><span class="qty-text">${qty} EA</span></div>${lines}</div>`;
    }).join('');
    return `<div class="detail-card export-order-card"><div class="export-order-title">${esc(order.country)}-${esc(order.buyer)}-${esc(order.transport_method)}</div><div class="muted">남은 수출대기 총수량: ${total} EA</div>${products}</div>`;
  }).join('');
}
function productCardsHtml(rows){""",
            1,
        )
        html = html.replace(
            "html+=productCardsHtml(grouped[lvl]);",
            "html+=(loc==='P' ? exportWaitingCardsHtml(grouped[lvl]) : productCardsHtml(grouped[lvl]));",
            1,
        )
        html = html.replace(
            "</style>",
            ".export-order-card{border:1.5px solid #c7d2fe;background:#f8faff;padding:14px;margin-bottom:14px}.export-order-title{font-size:18px;font-weight:800;color:#1e3a8a;margin-bottom:5px}.export-product-row{border-top:1px solid #dbeafe;margin-top:12px;padding-top:12px}.export-product-row:first-of-type{border-top:0;margin-top:8px;padding-top:0}</style>",
            1,
        )
        return original_html(html, *args, **kwargs)

    _legacy.components.html = enhanced_html
    try:
        return _legacy.render_location_map()
    finally:
        _legacy.components.html = original_html
