"""Runtime compatibility patches for NOHTUS WMS.

Streamlit imports this module automatically when the app starts from the
repository root. Keep patches narrow and defensive.
"""

from __future__ import annotations

import sqlite3
import sys
from datetime import datetime
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


def _patch_move_inventory(app_globals: dict) -> bool:
    if app_globals.get("_nohtus_move_erp_name_patched"):
        return True
    needed = ["connect", "product_mapping_name_for", "insert_transaction_log"]
    if not all(callable(app_globals.get(name)) for name in needed):
        return False

    connect = app_globals["connect"]
    product_mapping_name_for = app_globals["product_mapping_name_for"]
    insert_transaction_log = app_globals["insert_transaction_log"]

    def patched_move_inventory(src_id, to_company, to_location, qty, memo=""):
        """Move stock and recalculate the destination ERP/display name.

        사업장 이동 시 전산상명칭(warehouse_name)을 출발 사업장의 ERP명이 아니라
        도착 사업장의 ERP명/비자료명으로 다시 저장한다.
        """
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with connect() as con:
            cur = con.cursor()
            src = cur.execute("SELECT * FROM inventory WHERE id=?", (src_id,)).fetchone()
            cols = [d[0] for d in cur.description]
            src = dict(zip(cols, src)) if src else None
            if not src:
                raise ValueError("출발 재고를 찾을 수 없습니다.")
            qty_int = int(qty)
            if qty_int <= 0 or qty_int > int(src["qty"] or 0):
                raise ValueError("이동 수량이 현재 재고보다 많거나 올바르지 않습니다.")

            product_name = src["product_name"]
            dest_warehouse = product_mapping_name_for(to_company, product_name) or product_name

            cur.execute(
                "UPDATE inventory SET qty=?, updated_at=? WHERE id=?",
                (int(src["qty"] or 0) - qty_int, now, src_id),
            )
            row = cur.execute(
                """
                SELECT id, qty FROM inventory
                WHERE company=? AND product_name=? AND IFNULL(warehouse_name,'')=?
                  AND lot=? AND exp_date=? AND location=?
                """,
                (to_company, product_name, dest_warehouse or "", src["lot"], src["exp_date"], to_location),
            ).fetchone()
            if row:
                cur.execute(
                    "UPDATE inventory SET qty=?, updated_at=? WHERE id=?",
                    (int(row[1] or 0) + qty_int, now, row[0]),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO inventory(company,product_name,warehouse_name,lot,exp_date,location,qty,updated_at)
                    VALUES(?,?,?,?,?,?,?,?)
                    """,
                    (to_company, product_name, dest_warehouse, src["lot"], src["exp_date"], to_location, qty_int, now),
                )

            tx_type = "사업장+위치이동"
            if src["company"] == to_company and src["location"] != to_location:
                tx_type = "위치이동"
            elif src["company"] != to_company and src["location"] == to_location:
                tx_type = "사업장이동"
            if to_company == "비자료":
                tx_type = "비자료전환"

            move_memo = str(memo or "").strip()
            old_wh = str(src.get("warehouse_name") or "").strip()
            if old_wh != str(dest_warehouse or "").strip():
                erp_note = f"전산상명칭 변경: {old_wh or '-'} → {dest_warehouse or '-'}"
                move_memo = f"{move_memo} / {erp_note}" if move_memo else erp_note

            insert_transaction_log(
                cur,
                created_at=now,
                tx_type=tx_type,
                product_name=product_name,
                warehouse_name=dest_warehouse,
                lot=src["lot"],
                exp_date=src["exp_date"],
                from_company=src["company"],
                from_location=src["location"],
                to_company=to_company,
                to_location=to_location,
                qty=qty_int,
                memo=move_memo,
            )
            con.commit()

    app_globals["move_inventory"] = patched_move_inventory
    app_globals["_nohtus_move_erp_name_patched"] = True
    return True


def _patch_page_master(app_globals: dict) -> bool:
    if app_globals.get("_nohtus_inventory_lot_exp_edit_patched"):
        return True
    page_master = app_globals.get("page_master")
    if not callable(page_master):
        return False
    required = ["q", "connect", "normalize_blank", "normalize_exp_date", "insert_transaction_log"]
    if not all(callable(app_globals.get(name)) for name in required):
        return False

    q = app_globals["q"]
    connect = app_globals["connect"]
    normalize_blank = app_globals["normalize_blank"]
    normalize_exp_date = app_globals["normalize_exp_date"]
    insert_transaction_log = app_globals["insert_transaction_log"]

    def render_inventory_lot_exp_editor():
        if st is None:
            return
        st.markdown("---")
        with st.expander("재고 제조번호/유통기한 수정", expanded=False):
            st.caption("기존 재고 정보 자체가 잘못 입력된 경우 제조번호 또는 유통기한만 정정합니다. 수량은 변경하지 않습니다.")
            term = st.text_input(
                "재고 검색",
                placeholder="제품명, 전산상명칭, 제조번호, 유통기한, 로케이션 일부 입력",
                key="inv_meta_edit_term",
            )
            params = []
            where = "WHERE qty <> 0"
            if term.strip():
                like = f"%{term.strip()}%"
                where += " AND (product_name LIKE ? OR IFNULL(warehouse_name,'') LIKE ? OR IFNULL(lot,'') LIKE ? OR IFNULL(exp_date,'') LIKE ? OR location LIKE ?)"
                params.extend([like, like, like, like, like])
            inv = q(
                f"""
                SELECT id, company, product_name, warehouse_name, lot, exp_date, location, qty
                FROM inventory
                {where}
                ORDER BY product_name, company, location, lot, exp_date
                LIMIT 300
                """,
                tuple(params),
            )
            if inv.empty:
                st.info("수정할 재고가 없습니다.")
                return

            labels = []
            for r in inv.itertuples(index=False):
                wh = getattr(r, "warehouse_name") or "-"
                labels.append(
                    f"#{int(getattr(r, 'id'))} / {getattr(r, 'company')} / {getattr(r, 'location')} / "
                    f"{getattr(r, 'product_name')} / {wh} / LOT:{getattr(r, 'lot') or '-'} / "
                    f"EXP:{getattr(r, 'exp_date') or '-'} / {int(getattr(r, 'qty') or 0)}EA"
                )
            selected = st.selectbox("수정할 재고 선택", labels, key="inv_meta_edit_select")
            row = inv.iloc[labels.index(selected)]

            with st.form("inv_meta_edit_form"):
                new_lot = st.text_input("제조번호/LOT", value=str(row.get("lot") or "-"))
                new_exp = st.text_input("유통기한", value=str(row.get("exp_date") or "-"), placeholder="예: 28/3/2, 2028-03-02")
                memo = st.text_input("수정 사유/메모", value="")
                submitted = st.form_submit_button("제조번호/유통기한 수정 저장", use_container_width=True)

            if not submitted:
                return

            lot2 = normalize_blank(new_lot)
            exp2 = normalize_exp_date(new_exp)
            old_lot = str(row.get("lot") or "-")
            old_exp = str(row.get("exp_date") or "-")
            if lot2 == old_lot and exp2 == old_exp:
                st.info("변경된 내용이 없습니다.")
                return

            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            inv_id = int(row.get("id"))
            qty = int(row.get("qty") or 0)
            with connect() as con:
                cur = con.cursor()
                target = cur.execute(
                    """
                    SELECT id, qty FROM inventory
                    WHERE id<>? AND company=? AND product_name=? AND IFNULL(warehouse_name,'')=?
                      AND lot=? AND exp_date=? AND location=?
                    """,
                    (
                        inv_id,
                        row.get("company"),
                        row.get("product_name"),
                        row.get("warehouse_name") or "",
                        lot2,
                        exp2,
                        row.get("location"),
                    ),
                ).fetchone()
                if target:
                    cur.execute("UPDATE inventory SET qty=?, updated_at=? WHERE id=?", (int(target[1] or 0) + qty, now, target[0]))
                    cur.execute("DELETE FROM inventory WHERE id=?", (inv_id,))
                    merge_note = f" / 동일 재고행 #{int(target[0])}에 수량 합산"
                else:
                    cur.execute("UPDATE inventory SET lot=?, exp_date=?, updated_at=? WHERE id=?", (lot2, exp2, now, inv_id))
                    merge_note = ""

                reason = f"재고정보수정: LOT {old_lot} → {lot2}, 유통기한 {old_exp} → {exp2}"
                if memo.strip():
                    reason += f" / {memo.strip()}"
                reason += merge_note
                insert_transaction_log(
                    cur,
                    created_at=now,
                    tx_type="재고정보수정",
                    product_name=row.get("product_name"),
                    warehouse_name=row.get("warehouse_name"),
                    lot=lot2,
                    exp_date=exp2,
                    from_company=row.get("company"),
                    from_location=row.get("location"),
                    to_company=row.get("company"),
                    to_location=row.get("location"),
                    qty=0,
                    memo=reason,
                )
                con.commit()
            st.success("재고 제조번호/유통기한 수정 완료")
            st.rerun()

    def patched_page_master(*args, **kwargs):
        page_master(*args, **kwargs)
        render_inventory_lot_exp_editor()

    app_globals["page_master"] = patched_page_master
    app_globals["_nohtus_inventory_lot_exp_edit_patched"] = True
    return True


def _install_app_function_patches() -> None:
    """Patch app.py functions after Streamlit has defined them, before menu dispatch."""
    if st is None or getattr(st, "_nohtus_app_function_trace_installed", False):
        return

    def tracer(frame, event, arg):  # pragma: no cover - Streamlit runtime only
        if event == "line" and frame.f_globals.get("APP_TITLE") == "NOHTUS WMS":
            move_done = _patch_move_inventory(frame.f_globals)
            master_done = _patch_page_master(frame.f_globals)
            if move_done and master_done:
                sys.settrace(None)
                return None
        return tracer

    sys.settrace(tracer)
    st._nohtus_app_function_trace_installed = True


_patch_inbound_selectbox()
_install_app_function_patches()
