from __future__ import annotations

import pandas as pd

import nohtus.pages.closing_date_fix as closing_date_fix
from nohtus.services.export_waiting import ensure_export_waiting_tables


def _patched_export_waiting_rows(original_q, ds):
    """마감에는 당일 신규 등록 전체와 당일 수정된 실제 추가·증가분만 표시한다."""
    ensure_export_waiting_tables()
    date_text = str(ds or "")

    # 당일 새로 등록한 수출대기는 현재 목록 전체를 마감 대상으로 본다.
    created_rows = original_q(
        """
        SELECT o.title AS 출고지시서제목,
               -o.id AS 출고지시서ID,
               i.source_inventory_id AS 재고ID,
               i.company AS 사업장,
               i.source_location AS 로케이션,
               i.product_name AS 표준제품명,
               COALESCE(i.lot, '-') AS 제조번호,
               COALESCE(i.exp_date, '-') AS 유통기한,
               i.qty AS 출고수량
        FROM export_waiting_orders o
        JOIN export_waiting_items i ON o.id=i.order_id
        WHERE substr(COALESCE(o.created_at, ''), 1, 10)=?
          AND o.status IN ('waiting', 'partial', 'confirmed')
        ORDER BY i.company, i.source_location, i.product_name,
                 i.lot, i.exp_date, o.id, i.id
        """,
        (date_text,),
    )

    # 과거에 등록된 수출대기를 오늘 수정한 경우에는
    # P로 새로 이동한 품목·증가 수량만 마감 대상으로 가져온다.
    # P에서 원래 로케이션으로 되돌아간 삭제·감소 수량은 체크리스트에서 제외한다.
    changed_rows = original_q(
        """
        SELECT o.title AS 출고지시서제목,
               -o.id AS 출고지시서ID,
               NULL AS 재고ID,
               COALESCE(NULLIF(TRIM(t.from_company),''), t.to_company) AS 사업장,
               COALESCE(NULLIF(TRIM(t.from_location),''), '-') AS 로케이션,
               t.product_name AS 표준제품명,
               COALESCE(t.lot, '-') AS 제조번호,
               COALESCE(t.exp_date, '-') AS 유통기한,
               ABS(COALESCE(t.qty, 0)) AS 출고수량
        FROM transactions t
        JOIN export_waiting_orders o
          ON COALESCE(t.memo,'') LIKE '%수출번호: ' || o.export_no || '%'
         AND o.id = (
             SELECT MAX(o2.id)
             FROM export_waiting_orders o2
             WHERE COALESCE(t.memo,'') LIKE '%수출번호: ' || o2.export_no || '%'
         )
        WHERE substr(COALESCE(t.created_at,''), 1, 10)=?
          AND t.tx_type='위치이동'
          AND COALESCE(t.memo,'') LIKE '수출대기 수정 /%'
          AND TRIM(COALESCE(t.to_location,''))='P'
          AND substr(COALESCE(o.created_at,''), 1, 10)<>?
        ORDER BY t.id
        """,
        (date_text, date_text),
    )

    frames = []
    if created_rows is not None and not created_rows.empty:
        frames.append(created_rows)
    if changed_rows is not None and not changed_rows.empty:
        frames.append(changed_rows)
    if not frames:
        return pd.DataFrame(
            columns=[
                "출고지시서제목", "출고지시서ID", "재고ID", "사업장", "로케이션",
                "표준제품명", "제조번호", "유통기한", "출고수량",
            ]
        )
    return pd.concat(frames, ignore_index=True)


closing_date_fix._export_waiting_rows = _patched_export_waiting_rows
