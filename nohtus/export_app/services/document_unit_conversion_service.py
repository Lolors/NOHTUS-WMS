from __future__ import annotations

from nohtus.export_app import db


def list_case_conversions(case_id: int) -> list[dict]:
    rows = db.rows(
        '''SELECT o.id, o.product_name,
                  COALESCE(SUM(s.requested_qty), o.quantity, 0) AS internal_ea_qty,
                  COALESCE(NULLIF(TRIM(o.document_unit), ''), NULLIF(TRIM(o.unit), ''), 'EA') AS document_unit,
                  CASE
                    WHEN COALESCE(o.ea_per_document_unit, 0) > 0 THEN o.ea_per_document_unit
                    ELSE 1
                  END AS ea_per_document_unit
           FROM order_items o
           LEFT JOIN shipment_items s
             ON s.case_id=o.case_id
            AND s.order_item_id=o.id
           WHERE o.case_id=?
           GROUP BY o.id, o.product_name, o.quantity, o.unit,
                    o.document_unit, o.ea_per_document_unit
           ORDER BY o.id''',
        (int(case_id),),
    )
    return [dict(row) for row in rows]


def save_case_conversions(case_id: int, rows) -> None:
    updates: list[tuple[str, float, int, int]] = []
    for raw in rows:
        order_item_id = int(raw.get('_id') or raw.get('id') or 0)
        document_unit = str(raw.get('문서 단위') or raw.get('document_unit') or '').strip().upper()
        try:
            ea_per_unit = float(raw.get('1 문서단위당 EA') or raw.get('ea_per_document_unit') or 0)
        except (TypeError, ValueError):
            ea_per_unit = 0
        if order_item_id <= 0:
            continue
        if not document_unit:
            raise ValueError('문서 단위를 입력하세요.')
        if ea_per_unit <= 0:
            raise ValueError('1 문서단위당 EA는 0보다 커야 합니다.')
        updates.append((document_unit, ea_per_unit, order_item_id, int(case_id)))

    if updates:
        db.executemany(
            '''UPDATE order_items
               SET document_unit=?, ea_per_document_unit=?
               WHERE id=? AND case_id=?''',
            updates,
        )
