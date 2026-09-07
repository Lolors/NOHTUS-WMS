"""거래명세서 상세 조회와 안전한 개별 삭제 기능을 추가하는 실행 런처."""

from datetime import datetime
from pathlib import Path

import pandas as pd

import app_order_id_yy as current

purchase = current.purchase
base_app = current.base_app


def _backup_purchase_files():
    """삭제 직전 거래명세서 관련 CSV를 백업합니다."""
    backup_dir = Path(base_app.DATA) / "backup"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    for source in [
        purchase.STATEMENTS_FILE,
        purchase.STATEMENT_ITEMS_FILE,
        purchase.PRICE_HISTORY_FILE,
    ]:
        if source.exists():
            target = backup_dir / f"{source.stem}_{stamp}{source.suffix}"
            target.write_bytes(source.read_bytes())


def delete_statement(statement_id):
    """선택한 거래명세서 1건과 연결 품목/가격이력만 삭제합니다."""
    statement_id = str(statement_id).strip()
    statements, statement_items, price_history, _ = purchase.load_purchase_data()

    id_series = statements["명세서ID"].astype(str).str.strip()
    matched_count = int((id_series == statement_id).sum())

    if not statement_id:
        raise ValueError("명세서ID가 비어 있어 삭제할 수 없습니다.")
    if matched_count == 0:
        raise ValueError("선택한 거래명세서를 찾을 수 없습니다.")
    if matched_count > 1:
        raise ValueError(
            f"같은 명세서ID가 {matched_count}건 존재하여 안전을 위해 삭제를 중단했습니다."
        )

    _backup_purchase_files()

    statements = statements[id_series != statement_id].copy()
    statement_items = statement_items[
        statement_items["명세서ID"].astype(str).str.strip() != statement_id
    ].copy()
    price_history = price_history[
        price_history["명세서ID"].astype(str).str.strip() != statement_id
    ].copy()

    purchase.save_table(
        purchase.STATEMENTS_FILE,
        statements,
        purchase.STATEMENT_COLUMNS,
    )
    purchase.save_table(
        purchase.STATEMENT_ITEMS_FILE,
        statement_items,
        purchase.STATEMENT_ITEM_COLUMNS,
    )
    purchase.save_table(
        purchase.PRICE_HISTORY_FILE,
        price_history,
        purchase.PRICE_HISTORY_COLUMNS,
    )


def page_statement_list_with_detail():
    """거래명세서 목록, 상세 품목, 안전한 삭제 기능을 제공합니다."""
    statements, statement_items, _, _ = purchase.load_purchase_data()
    base_app.st.markdown("## 거래명세서 내역")

    if statements.empty:
        base_app.st.info("등록된 거래명세서가 없습니다.")
        return

    statements = statements.copy()
    statements["명세서ID"] = statements["명세서ID"].astype(str).str.strip()

    duplicate_mask = statements["명세서ID"].duplicated(keep=False) | (statements["명세서ID"] == "")
    duplicate_ids = statements.loc[duplicate_mask, "명세서ID"].tolist()
    if duplicate_ids:
        display_ids = [value if value else "(빈 ID)" for value in duplicate_ids]
        base_app.st.error(
            "중복되거나 비어 있는 명세서ID가 발견되었습니다. "
            "해당 명세서는 안전을 위해 삭제할 수 없습니다: "
            + ", ".join(display_ids)
        )

    detail = purchase.statement_detail_frame(statements, statement_items)
    detail = detail.sort_values(
        ["명세서일자", "등록일시"],
        ascending=False,
    ).reset_index(drop=True)

    summary = detail[[
        "명세서ID", "발주ID", "거래처명", "명세서번호", "명세서일자",
        "상품매입금액", "운송비", "총매입금액", "운송비상태",
    ]].copy()
    for col in ["상품매입금액", "운송비", "총매입금액"]:
        summary[col] = summary[col].apply(lambda value: f"{purchase.to_int(value):,}")

    base_app.st.dataframe(summary, use_container_width=True, hide_index=True)

    ids = detail["명세서ID"].astype(str).str.strip().tolist()
    unique_ids = list(dict.fromkeys(ids))
    row_map = {}
    for _, row in detail.iterrows():
        sid = str(row.get("명세서ID", "")).strip()
        if sid not in row_map:
            row_map[sid] = row.to_dict()

    selected_id = base_app.st.selectbox(
        "상세 확인할 거래명세서",
        unique_ids,
        format_func=lambda sid: (
            f'[{row_map[sid].get("거래처명", "")}] '
            f'{row_map[sid].get("명세서번호", "")}번 | '
            f'{row_map[sid].get("명세서일자", "")} | {sid}'
        ),
    )

    header = row_map[selected_id]
    items = statement_items[
        statement_items["명세서ID"].astype(str).str.strip() == str(selected_id).strip()
    ].copy()

    base_app.st.markdown("### 거래명세서 상세")
    c1, c2, c3, c4 = base_app.st.columns(4)
    c1.metric("거래처", str(header.get("거래처명", "")))
    c2.metric("명세서 번호", f'{header.get("명세서번호", "")}번')
    c3.metric("총 입고수량", f'{purchase.to_int(header.get("총입고수량", 0)):,}개')
    c4.metric("총 매입금액", f'{purchase.to_int(header.get("총매입금액", 0)):,}원')

    if items.empty:
        base_app.st.info("이 거래명세서에 저장된 품목이 없습니다.")
    else:
        for col in ["입고수량", "매입단가", "상품금액", "출고단가"]:
            items[col] = items[col].apply(purchase.to_int)

        item_view = items[[
            "정식제품명", "규격", "단위", "입고수량", "매입단가", "상품금액",
        ]].copy()
        item_view = item_view.rename(columns={
            "입고수량": "수량",
            "매입단가": "단가",
        })
        base_app.st.dataframe(item_view, use_container_width=True, hide_index=True)

    selected_count = int(
        (statements["명세서ID"].astype(str).str.strip() == str(selected_id).strip()).sum()
    )
    safe_to_delete = bool(selected_id) and selected_count == 1

    base_app.st.markdown("### 거래명세서 삭제")
    if not safe_to_delete:
        base_app.st.error(
            "선택한 명세서ID가 중복되었거나 비어 있어 삭제할 수 없습니다. "
            "다른 거래명세서가 함께 삭제되는 것을 방지하기 위한 안전장치입니다."
        )

    confirm = base_app.st.checkbox(
        "선택한 거래명세서 1건만 삭제합니다.",
        key=f"delete_statement_confirm_{selected_id}",
        disabled=not safe_to_delete,
    )
    if base_app.st.button(
        "선택한 거래명세서 삭제",
        type="primary",
        use_container_width=True,
        disabled=(not confirm) or (not safe_to_delete),
    ):
        try:
            delete_statement(selected_id)
        except ValueError as exc:
            base_app.st.error(str(exc))
            return
        base_app.st.success("선택한 거래명세서 1건과 연결 품목 및 가격이력만 삭제했습니다.")
        base_app.st.rerun()


purchase.page_statement_list = page_statement_list_with_detail


if __name__ == "__main__":
    purchase.main()
