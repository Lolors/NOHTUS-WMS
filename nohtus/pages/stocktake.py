"""Stocktake page for NOHTUS WMS.

Migrated from app.py. This module intentionally imports Streamlit because it
contains page rendering code.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from io import BytesIO

import pandas as pd
import streamlit as st

from nohtus.db import connect, q
from nohtus.dates import display_date_only, normalize_exp_date
from nohtus.services.inventory import adjust_inventory

PRODUCT_MAPPING_COLUMNS = [
    "노투스팜 ERP명",
    "노투스팜 ERP 제품코드",
    "NOH ERP명",
    "NOH ERP 제품코드",
    "노투스 ERP명",
    "비자료명",
    "별칭",
]

PRODUCT_MAPPING_DB_COLUMNS = {
    "노투스팜 ERP명": "erp_nohtuspharm_name",
    "노투스팜 ERP 제품코드": "product_code",
    "NOH ERP명": "erp_noh_name",
    "NOH ERP 제품코드": "erp_noh_code",
    "노투스 ERP명": "erp_nohtus_name",
    "비자료명": "bidata_name",
    "별칭": "aliases",
}


def _normalize_master_text(value):
    text = str(value or "").strip()
    return text if text else "-"


def _clean_mapping_text(value):
    if pd.isna(value):
        return ""
    text = str(value or "").strip()
    return "" if text.lower() == "nan" else text


def _load_product_mapping_rows(product_name):
    mapping_df = q(
        """
        SELECT id, erp_nohtuspharm_name, product_code, erp_noh_name,
               erp_noh_code, erp_nohtus_name, bidata_name, aliases
        FROM products
        WHERE TRIM(standard_name)=?
        ORDER BY id
        """,
        (str(product_name or "").strip(),),
    )
    if mapping_df.empty:
        return pd.DataFrame([{column: "" for column in PRODUCT_MAPPING_COLUMNS}])

    return mapping_df.rename(
        columns={
            "erp_nohtuspharm_name": "노투스팜 ERP명",
            "product_code": "노투스팜 ERP 제품코드",
            "erp_noh_name": "NOH ERP명",
            "erp_noh_code": "NOH ERP 제품코드",
            "erp_nohtus_name": "노투스 ERP명",
            "bidata_name": "비자료명",
            "aliases": "별칭",
        }
    )[["id", *PRODUCT_MAPPING_COLUMNS]]


def _update_inventory_and_product_mappings(
    inv_id, product_name, lot, exp_date, edited_mappings
):
    product_name = str(product_name or "").strip()
    if not product_name:
        raise ValueError("제품명을 입력하세요.")

    lot = _normalize_master_text(lot)
    exp_date = normalize_exp_date(exp_date)
    mapping_rows = edited_mappings.copy()
    if "id" not in mapping_rows.columns:
        mapping_rows.insert(0, "id", None)

    with connect() as con:
        current = con.execute(
            "SELECT product_name, company, location, warehouse_name, qty FROM inventory WHERE id=?",
            (int(inv_id),),
        ).fetchone()
        if not current:
            raise ValueError("수정할 재고를 찾을 수 없습니다.")
        old_product_name = str(current[0] or "").strip()
        row_company, row_location, row_warehouse, row_qty = current[1], current[2], current[3], current[4]

        existing_rows = con.execute(
            """
            SELECT id, warehouse_name, image_path
            FROM products
            WHERE TRIM(standard_name)=?
            ORDER BY id
            """,
            (old_product_name,),
        ).fetchall()
        existing_by_id = {
            int(row[0]): {
                "warehouse_name": str(row[1] or ""),
                "image_path": str(row[2] or ""),
            }
            for row in existing_rows
        }

        try:
            # 새로 입력한 제품명/LOT/유통기한이 같은 사업장·전산상명칭·로케이션의
            # 다른 재고행과 완전히 똑같아지면(유니크 제약 충돌), 그건 "이미 있는
            # 같은 배치"라는 뜻이므로 오류로 막지 말고 그 행에 수량을 합친다.
            # 이 행 자체는 남겨두되(다른 곳에서 이 재고ID를 참조할 수 있으므로)
            # 수량만 0으로 비우고 제품명/LOT/유통기한은 옛 값 그대로 둔다.
            merge_target = con.execute(
                """
                SELECT id, qty FROM inventory
                WHERE id<>? AND TRIM(COALESCE(product_name,''))=?
                  AND TRIM(COALESCE(company,''))=TRIM(COALESCE(?,''))
                  AND TRIM(COALESCE(warehouse_name,''))=TRIM(COALESCE(?,''))
                  AND TRIM(COALESCE(lot,''))=?
                  AND TRIM(COALESCE(exp_date,''))=?
                  AND TRIM(COALESCE(location,''))=TRIM(COALESCE(?,''))
                """,
                (int(inv_id), product_name, row_company, row_warehouse, lot, exp_date, row_location),
            ).fetchone()

            if merge_target:
                target_id, target_qty = int(merge_target[0]), int(merge_target[1] or 0)
                con.execute(
                    "UPDATE inventory SET qty=? WHERE id=?",
                    (target_qty + int(row_qty or 0), target_id),
                )
                con.execute("UPDATE inventory SET qty=0 WHERE id=?", (int(inv_id),))
            else:
                con.execute(
                    """
                    UPDATE inventory
                    SET product_name=?, lot=?, exp_date=?
                    WHERE id=?
                    """,
                    (product_name, lot, exp_date, int(inv_id)),
                )

            # Stock already saved to 수출대기 (moved to location P) keeps its own
            # product_name/lot/exp_date snapshot in export_waiting_items rather
            # than reading live inventory — without this it would stay frozen
            # at whatever it was the moment it was saved there. Match on either
            # id column since a P row can be tracked as the original source or
            # as the inventory row currently sitting at P.
            con.execute(
                """
                UPDATE export_waiting_items
                SET product_name=?, lot=?, exp_date=?
                WHERE waiting_inventory_id=? OR source_inventory_id=?
                """,
                (product_name, lot, exp_date, int(inv_id), int(inv_id)),
            )

            kept_ids = set()
            for _, mapping in mapping_rows.iterrows():
                values = {
                    db_column: _clean_mapping_text(mapping.get(label))
                    for label, db_column in PRODUCT_MAPPING_DB_COLUMNS.items()
                }
                raw_id = mapping.get("id")
                mapping_id = None
                if not pd.isna(raw_id) and str(raw_id).strip():
                    try:
                        mapping_id = int(raw_id)
                    except (TypeError, ValueError):
                        mapping_id = None

                if mapping_id in existing_by_id:
                    kept_ids.add(mapping_id)
                    preserved = existing_by_id[mapping_id]
                    con.execute(
                        """
                        UPDATE products
                        SET standard_name=?, warehouse_name=?, aliases=?,
                            erp_nohtuspharm_name=?, product_code=?,
                            erp_noh_name=?, erp_noh_code=?,
                            erp_nohtus_name=?, bidata_name=?
                        WHERE id=?
                        """,
                        (
                            product_name,
                            preserved["warehouse_name"] or product_name,
                            values["aliases"],
                            values["erp_nohtuspharm_name"],
                            values["product_code"],
                            values["erp_noh_name"],
                            values["erp_noh_code"],
                            values["erp_nohtus_name"],
                            values["bidata_name"],
                            mapping_id,
                        ),
                    )
                else:
                    con.execute(
                        """
                        INSERT INTO products(
                            product_code, standard_name, warehouse_name, aliases,
                            erp_nohtuspharm_name, erp_nohtus_name, erp_noh_name,
                            erp_noh_code, bidata_name, image_path
                        ) VALUES(?,?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            values["product_code"],
                            product_name,
                            product_name,
                            values["aliases"],
                            values["erp_nohtuspharm_name"],
                            values["erp_nohtus_name"],
                            values["erp_noh_name"],
                            values["erp_noh_code"],
                            values["bidata_name"],
                            "",
                        ),
                    )

            delete_ids = [mapping_id for mapping_id in existing_by_id if mapping_id not in kept_ids]
            if delete_ids:
                placeholders = ",".join("?" for _ in delete_ids)
                con.execute(f"DELETE FROM products WHERE id IN ({placeholders})", delete_ids)

            con.commit()
        except sqlite3.IntegrityError as exc:
            con.rollback()
            raise ValueError("수정 결과와 동일한 재고 또는 제품매칭 정보가 이미 존재합니다.") from exc
        except Exception:
            con.rollback()
            raise

    propagation_error = _propagate_master_edit_to_shipment_items(int(inv_id), product_name, lot, exp_date)

    return product_name, lot, exp_date, len(mapping_rows), propagation_error, bool(merge_target)


def _propagate_master_edit_to_shipment_items(inv_id, product_name, lot, exp_date):
    """수출대기 제품에 이미 입고 연결된 행이 있으면 제품명/LOT/유통기한을 같이 맞춘다.

    수출 DB(shipment_items)는 별도 연결이라 위 재고/제품매칭 트랜잭션과 하나로
    묶을 수 없다. 이 재고 행을 근거로 입고 연결된 행(source_inventory_id)만
    골라서 스냅샷 텍스트를 갱신한다. 재고/제품매칭 수정 자체는 이미 반영된
    뒤이므로, 여기서 실패해도 예외를 던지지 않고 경고 메시지만 돌려준다.
    """
    from nohtus.export_app import db as export_db
    from nohtus.export_app.utils.dates import now_text

    try:
        export_db.execute(
            """
            UPDATE shipment_items
            SET product_name=?, lot_no=?, expiry_date=?, updated_at=?
            WHERE source_inventory_id=?
            """,
            (product_name, lot, exp_date, now_text(), inv_id),
        )
    except Exception as exc:
        return f"제품마스터는 수정됐지만 수출대기 제품 반영에 실패했습니다: {exc}"
    return ""


@st.dialog("제품마스터 수정", width="large")
def _render_inventory_master_dialog(inv_id, product_name, lot, exp_date):
    st.caption("선택한 재고 기본정보와 해당 표준제품명의 제품매칭표를 한 번에 수정합니다.")

    st.markdown("#### 제품 기본정보")
    basic_left, basic_mid, basic_right = st.columns(3)
    with basic_left:
        new_product_name = st.text_input("제품명", value=str(product_name or ""), key=f"stock_master_product_{inv_id}")
    with basic_mid:
        new_lot = st.text_input("LOT/제조번호", value=str(lot or "-"), key=f"stock_master_lot_{inv_id}")
    with basic_right:
        new_exp = st.text_input(
            "유통기한",
            value=str(exp_date or "-"),
            placeholder="예) 2028-03-30 / 미입력 시 '-'",
            key=f"stock_master_exp_{inv_id}",
        )

    st.markdown("#### 제품매칭표")
    st.caption("행을 추가하거나 삭제할 수 있습니다. 같은 표준제품명에 연결된 매칭 행 전체가 저장됩니다.")
    mapping_df = _load_product_mapping_rows(product_name)
    edited_mappings = st.data_editor(
        mapping_df,
        hide_index=True,
        use_container_width=True,
        num_rows="dynamic",
        key=f"stock_master_mapping_editor_{inv_id}",
        column_config={
            "id": st.column_config.NumberColumn("ID", disabled=True),
            "노투스팜 ERP 제품코드": st.column_config.TextColumn("노투스팜 ERP 제품코드"),
            "NOH ERP 제품코드": st.column_config.TextColumn("NOH ERP 제품코드"),
        },
        disabled=["id"],
    )

    if st.button(
        "제품 기본정보 + 제품매칭표 저장",
        type="primary",
        use_container_width=True,
        key=f"stock_master_save_{inv_id}",
    ):
        try:
            saved_product, saved_lot, saved_exp, mapping_count, propagation_error, merged = _update_inventory_and_product_mappings(
                int(inv_id), new_product_name, new_lot, new_exp, edited_mappings
            )
            if merged:
                success_msg = (
                    f"이미 같은 사업장/로케이션/LOT/유통기한의 재고가 있어 그쪽에 수량을 합쳤습니다: "
                    f"{saved_product} / {saved_lot} / {display_date_only(saved_exp)} / 매칭 {mapping_count}행"
                )
            else:
                success_msg = (
                    f"제품마스터 수정 완료: {saved_product} / {saved_lot} / "
                    f"{display_date_only(saved_exp)} / 매칭 {mapping_count}행"
                )
            if propagation_error:
                success_msg += f" ({propagation_error})"
            st.session_state["_stock_master_success_msg"] = success_msg
            st.session_state["_stock_master_focus_product"] = saved_product
            st.rerun()
        except Exception as exc:
            st.error(str(exc))


def _allocate_erp_quantity_by_detail(actual_quantities, erp_quantity):
    """실제 상세수량을 최대한 확정하고 ERP 잔량은 한 상세행에 배정한다."""
    actual = pd.to_numeric(pd.Series(actual_quantities), errors="coerce").fillna(0).astype(int)
    allocated = pd.Series(0, index=actual.index, dtype="int64")
    if actual.empty:
        return allocated

    remaining = int(erp_quantity)
    # 작은 상세수량부터 1:1로 확정한다. 가장 큰 행은 총량 차이를 흡수하는
    # 대표행으로 남겨 유통기한별 실제수량을 합산하지 않는다.
    ordered_indexes = actual.sort_values(kind="stable").index.tolist()
    for index in ordered_indexes[:-1]:
        quantity = int(actual.loc[index])
        if quantity < 0 or remaining < quantity:
            continue
        allocated.loc[index] = quantity
        remaining -= quantity

    allocated.loc[ordered_indexes[-1]] += remaining
    return allocated


def _build_stocktake_result(ignored_result=None):
    """기준재고 수량을 채우고 무시 목록 제품은 ERP 비교 수량으로 대체한다."""
    from nohtus.services.stocktake import current_baseline_stock_excel_bytes

    baseline = pd.read_excel(
        BytesIO(current_baseline_stock_excel_bytes(exclude_zero=False)),
        sheet_name="기준재고업로드",
        dtype={"ERP제품코드": str},
    )
    baseline["ERP제품코드"] = baseline["ERP제품코드"].fillna("").astype(str)

    quantity = pd.to_numeric(baseline["수량"], errors="coerce").fillna(0)
    baseline["전산수량"] = quantity.astype(int)
    baseline["실제수량"] = quantity.astype(int)
    baseline["차이"] = 0

    if ignored_result is not None and not ignored_result.empty:
        source = ignored_result.copy()
        required_columns = {"사업장", "표준제품명", "WMS수량", "ERP수량"}
        if required_columns.issubset(source.columns):
            source = source[
                source["사업장"].fillna("").astype(str).str.strip() != "지엠메딕"
            ].copy()
            source["WMS수량"] = pd.to_numeric(source["WMS수량"], errors="coerce")
            source["ERP수량"] = pd.to_numeric(source["ERP수량"], errors="coerce")
            source = source.dropna(subset=["WMS수량", "ERP수량"])

            baseline_company = baseline["사업장"].fillna("").astype(str).str.strip()
            baseline_product = baseline["표준제품명"].fillna("").astype(str).str.strip()

            missing_rows = []
            for _, compared in source.iterrows():
                company_value = compared["사업장"]
                product_value = compared["표준제품명"]
                company = "" if pd.isna(company_value) else str(company_value).strip()
                product = "" if pd.isna(product_value) else str(product_value).strip()
                matched_indexes = baseline.index[
                    (baseline_company == company) & (baseline_product == product)
                ]
                erp_quantity = int(compared["ERP수량"])
                wms_quantity = int(compared["WMS수량"])

                if matched_indexes.empty:
                    # 무시 목록 제품이 현재 재고 테이블에 행이 없어도(예: 재고 소진)
                    # 무시 목록 관리 화면의 모든 항목이 기준 재고 엑셀에 나타나도록 추가한다.
                    missing_rows.append(
                        {
                            "사업장": company,
                            "ERP제품코드": "",
                            "ERP제품명": product,
                            "표준제품명": product,
                            "LOT/제조번호": "-",
                            "유통기한": "-",
                            "로케이션": "",
                            "전산수량": erp_quantity,
                            "실제수량": wms_quantity,
                            "차이": wms_quantity - erp_quantity,
                        }
                    )
                    continue

                actual_quantities = pd.to_numeric(
                    baseline.loc[matched_indexes, "실제수량"], errors="coerce"
                ).fillna(0).astype(int)
                allocated = _allocate_erp_quantity_by_detail(
                    actual_quantities, erp_quantity
                )
                baseline.loc[matched_indexes, "전산수량"] = allocated
                baseline.loc[matched_indexes, "실제수량"] = actual_quantities
                baseline.loc[matched_indexes, "차이"] = actual_quantities - allocated

            if missing_rows:
                baseline = pd.concat(
                    [baseline, pd.DataFrame(missing_rows, columns=baseline.columns)],
                    ignore_index=True,
                )

    computerized = pd.to_numeric(baseline["전산수량"], errors="coerce")
    actual = pd.to_numeric(baseline["실제수량"], errors="coerce")
    baseline = baseline[
        ~(computerized.eq(0) & actual.eq(0))
    ].copy()
    baseline = baseline.drop(columns=["수량"])

    columns = list(baseline.columns)
    if "사업장" in columns and "로케이션" in columns:
        columns.remove("로케이션")
        columns.insert(columns.index("사업장") + 1, "로케이션")
        baseline = baseline[columns]

    return baseline


def _stocktake_result_excel_bytes(stocktake_result):
    from nohtus.services.stocktake import _baseline_stock_excel_bytes_from_dataframe

    return _baseline_stock_excel_bytes_from_dataframe(stocktake_result)


def _render_stock_comparison():
    from nohtus.services.stock_compare import (
        add_ignored_problems,
        compare_stock_files,
        comparison_excel_bytes,
        filter_ignored_problems,
        list_ignored_problems,
        remove_ignored_problems,
        update_ignored_problem_reasons,
    )

    st.subheader("WMS · ERP · 실사재고 비교")
    ignore_message = st.session_state.pop("_stock_compare_ignore_message", None)
    if ignore_message:
        st.success(ignore_message)
    st.caption(
        "ERP는 사업장·제품별 총수량으로 비교하고, 지엠메딕 실사재고는 "
        "노투스팜의 지엠메딕 로케이션 재고를 제품·유통기한별로 비교합니다."
    )

    erp_left, erp_mid, erp_right = st.columns(3, gap="large")
    with erp_left:
        nohtuspharm_file = st.file_uploader(
            "노투스팜 ERP 재고", type=["xlsx", "xls"], key="stock_compare_nohtuspharm"
        )
    with erp_mid:
        noh_file = st.file_uploader(
            "NOH ERP 재고", type=["xlsx", "xls"], key="stock_compare_noh"
        )
    with erp_right:
        nohtus_file = st.file_uploader(
            "노투스 ERP 재고", type=["xlsx", "xls"], key="stock_compare_nohtus"
        )

    gm_left, gm_blank = st.columns([1, 2], gap="large")
    with gm_left:
        gmmedic_file = st.file_uploader(
            "지엠메딕 실사재고", type=["xlsx", "xls"], key="stock_compare_gmmedic"
        )

    uploaded = [nohtuspharm_file, noh_file, nohtus_file, gmmedic_file]

    def run_stock_comparison():
        for file in uploaded:
            if file is not None:
                file.seek(0)
        st.session_state["stock_compare_result"] = compare_stock_files(
            nohtuspharm_file=nohtuspharm_file,
            noh_file=noh_file,
            nohtus_file=nohtus_file,
            gmmedic_file=gmmedic_file,
        )
        # 비교 대상 행이 달라질 수 있으므로 이전 표의 체크 상태는 버린다.
        st.session_state.pop("stock_compare_problem_editor", None)
        st.session_state.pop("stock_compare_ignored_editor", None)

    compare_col, refresh_col = st.columns(2, gap="large")
    with compare_col:
        compare_clicked = st.button(
            "재고 비교하기",
            type="primary",
            use_container_width=True,
            disabled=not any(uploaded),
            key="stock_compare_run",
        )
    with refresh_col:
        refresh_clicked = st.button(
            "비교결과 새로고침",
            use_container_width=True,
            disabled=not any(uploaded) or "stock_compare_result" not in st.session_state,
            key="stock_compare_refresh",
            help="업로드한 파일은 그대로 두고 현재 WMS 재고를 다시 읽어 비교합니다.",
        )

    if compare_clicked or refresh_clicked:
        try:
            run_stock_comparison()
            if refresh_clicked:
                st.success("최신 WMS 재고로 비교결과를 새로고침했습니다.")
        except Exception as exc:
            st.session_state.pop("stock_compare_result", None)
            st.error(f"비교 실패: {exc}")

    result = st.session_state.get("stock_compare_result")
    if not result:
        return

    # 저장된 원본 문제를 현재 무시 목록 기준으로 매번 다시 필터링한다.
    # 무시 등록/해제 후에도 파일을 다시 비교하지 않고 즉시 목록에 반영된다.
    problems = filter_ignored_problems(
        result.get("all_problems", result["problems"])
    )
    erp_result = result["erp"]
    gm_result = result["gmmedic"]

    total_erp = len(erp_result)
    erp_errors = int((erp_result["상태"] == "불일치").sum()) if total_erp else 0
    total_gm = len(gm_result)
    gm_errors = int((gm_result["상태"] == "불일치").sum()) if total_gm else 0

    metric1, metric2, metric3, metric4 = st.columns(4)
    metric1.metric("ERP 비교 품목", f"{total_erp:,}건")
    metric2.metric("ERP 불일치", f"{erp_errors:,}건")
    metric3.metric("지엠메딕 비교 항목", f"{total_gm:,}건")
    metric4.metric("전체 문제", f"{len(problems):,}건")

    st.markdown("#### 문제목록")
    if problems.empty:
        st.success("업로드한 파일 기준으로 확인이 필요한 문제가 없습니다.")
    else:
        st.error(f"확인이 필요한 문제가 {len(problems):,}건 있습니다.")
        problem_editor = problems.copy()
        problem_editor.insert(0, "무시", False)
        edited_problems = st.data_editor(
            problem_editor,
            hide_index=True,
            use_container_width=True,
            key="stock_compare_problem_editor",
            disabled=[column for column in problem_editor.columns if column != "무시"],
            column_config={
                "무시": st.column_config.CheckboxColumn(
                    "무시", help="의도적으로 유지할 차이라면 체크하세요."
                ),
                "WMS수량": st.column_config.NumberColumn(format="%d"),
                "비교수량": st.column_config.NumberColumn(format="%d"),
                "차이": st.column_config.NumberColumn(format="%+d"),
            },
        )
        selected_problems = edited_problems[edited_problems["무시"] == True]
        ignore_reason = st.text_input(
            "차이 원인",
            placeholder="선택한 항목에 공통으로 적용할 차이 원인을 입력하세요.",
            key="stock_compare_ignore_reason",
        )
        if st.button(
            "선택 항목 문제목록에서 무시",
            disabled=selected_problems.empty or not str(ignore_reason or "").strip(),
            use_container_width=True,
            key="stock_compare_ignore_selected",
        ):
            added = add_ignored_problems(selected_problems, ignore_reason)
            st.session_state["_stock_compare_ignore_message"] = (
                f"{added:,}개 항목을 '{str(ignore_reason).strip()}' 원인으로 무시 목록에 등록했습니다."
            )
            st.rerun()

    ignored_problems = list_ignored_problems()
    ignored_result_source = pd.DataFrame()
    with st.expander(f"무시 목록 관리 ({len(ignored_problems):,}건)"):
        st.caption(
            "현재 ERP 비교결과에 포함된 무시 항목은 WMS 수량·ERP 수량·차이를 함께 표시합니다. "
            "해제하면 다음 비교부터 문제목록에 다시 나타납니다."
        )
        if ignored_problems.empty:
            st.info("현재 무시 중인 항목이 없습니다.")
        else:
            ignored_editor = ignored_problems.copy()
            quantity_columns = [
                "사업장", "표준제품명", "WMS수량", "ERP수량", "차이",
            ]
            quantity_value_columns = ["WMS수량", "ERP수량", "차이"]
            for column in quantity_value_columns:
                ignored_editor[column] = pd.NA
            if not erp_result.empty:
                def quantity_key(row):
                    company = str(row.get("사업장", "") or "").strip()
                    product = str(row.get("표준제품명", "") or "").strip()
                    return company, product

                quantity_lookup = {}
                for _, current_row in erp_result[quantity_columns].iterrows():
                    quantity_lookup[quantity_key(current_row)] = tuple(
                        current_row[column] for column in quantity_value_columns
                    )

                for index, ignored_row in ignored_editor.iterrows():
                    quantities = quantity_lookup.get(quantity_key(ignored_row))
                    if quantities is not None:
                        ignored_editor.loc[index, quantity_value_columns] = quantities
            ignored_result_source = ignored_editor.copy()
            ignored_editor.insert(0, "해제", False)
            ignored_editor = ignored_editor[[
                "해제",
                "사업장",
                "표준제품명",
                "WMS수량",
                "ERP수량",
                "차이",
                "차이원인",
                "ID",
            ]]
            edited_ignored = st.data_editor(
                ignored_editor,
                hide_index=True,
                use_container_width=True,
                key="stock_compare_ignored_editor",
                disabled=[
                    column
                    for column in ignored_editor.columns
                    if column not in {"해제", "차이원인"}
                ],
                column_config={
                    "해제": st.column_config.CheckboxColumn("해제"),
                    "WMS수량": st.column_config.NumberColumn("WMS 수량", format="%d"),
                    "ERP수량": st.column_config.NumberColumn("ERP 수량", format="%d"),
                    "차이": st.column_config.NumberColumn("수량 차이", format="%+d"),
                    "차이원인": st.column_config.TextColumn(
                        "차이 원인",
                        help="기존 사유를 수정한 뒤 아래 저장 버튼을 누르세요.",
                        required=True,
                    ),
                    "ID": None,
                },
            )
            original_reasons = {
                int(row["ID"]): str(row["차이원인"] or "").strip()
                for _, row in ignored_editor.iterrows()
            }
            reason_updates = {}
            has_blank_reason = False
            for _, row in edited_ignored.iterrows():
                ignore_id = int(row["ID"])
                value = row["차이원인"]
                edited_reason = "" if pd.isna(value) else str(value).strip()
                if edited_reason != original_reasons[ignore_id]:
                    if edited_reason:
                        reason_updates[ignore_id] = edited_reason
                    else:
                        has_blank_reason = True

            if has_blank_reason:
                st.warning("차이 원인은 비워둘 수 없습니다.")
            if st.button(
                "수정한 사유 저장",
                disabled=not reason_updates or has_blank_reason,
                use_container_width=True,
                key="stock_compare_save_ignored_reasons",
            ):
                updated = update_ignored_problem_reasons(reason_updates)
                st.session_state["_stock_compare_ignore_message"] = (
                    f"{updated:,}개 항목의 차이 원인을 수정했습니다."
                )
                st.session_state.pop("stock_compare_ignored_editor", None)
                st.rerun()

            selected_ignored = edited_ignored[edited_ignored["해제"] == True]
            if st.button(
                "선택 항목 무시 해제",
                disabled=selected_ignored.empty,
                use_container_width=True,
                key="stock_compare_unignore_selected",
            ):
                removed = remove_ignored_problems(selected_ignored["ID"].tolist())
                st.session_state["_stock_compare_ignore_message"] = (
                    f"{removed:,}개 항목의 무시를 해제했습니다."
                )
                st.rerun()

    tab_erp, tab_gm = st.tabs(["ERP 비교결과", "지엠메딕 실사 비교결과"])
    with tab_erp:
        if erp_result.empty:
            st.info("ERP 파일을 업로드하지 않았습니다.")
        else:
            st.dataframe(
                erp_result,
                hide_index=True,
                use_container_width=True,
                column_config={
                    "WMS수량": st.column_config.NumberColumn(format="%d"),
                    "ERP수량": st.column_config.NumberColumn(format="%d"),
                    "차이": st.column_config.NumberColumn(format="%+d"),
                },
            )
    with tab_gm:
        if gm_result.empty:
            st.info("지엠메딕 실사재고 파일을 업로드하지 않았습니다.")
        else:
            st.dataframe(
                gm_result,
                hide_index=True,
                use_container_width=True,
                column_config={
                    "WMS수량": st.column_config.NumberColumn(format="%d"),
                    "실사수량": st.column_config.NumberColumn(format="%d"),
                    "차이": st.column_config.NumberColumn(format="%+d"),
                },
            )

    st.download_button(
        "비교결과 엑셀 다운로드",
        data=comparison_excel_bytes(erp_result, gm_result, problems),
        file_name=f"NOHTUS_재고비교결과_{date.today().strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
        key="stock_compare_download",
    )

    st.markdown("#### 수량 대조용 기준 재고")
    st.caption(
        "일반 제품은 전산수량과 실제수량을 똑같이 표시합니다. "
        "무시 목록 제품은 유통기한별 수량을 그대로 보여주고, "
        "ERP수량을 각 유통기한에 맞게 나누어 표시합니다."
    )
    stocktake_result = _build_stocktake_result(ignored_result_source)
    if stocktake_result.empty:
        st.info("현재 기준 재고가 없습니다.")
    else:
        st.dataframe(
            stocktake_result,
            hide_index=True,
            use_container_width=True,
            column_config={
                "전산수량": st.column_config.NumberColumn(format="%d"),
                "실제수량": st.column_config.NumberColumn(format="%d"),
                "차이": st.column_config.NumberColumn(format="%+d"),
            },
        )
        st.download_button(
            "수량 대조용 기준 재고 엑셀 다운로드",
            data=_stocktake_result_excel_bytes(stocktake_result),
            file_name=f"NOHTUS_수량대조용_기준재고_{date.today().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key="stocktake_result_download",
        )


def _render_stock_adjustment():
    st.subheader("재고조정")

    focus_product = st.session_state.pop("_stock_master_focus_product", None)
    if focus_product:
        st.session_state["stock_adjust_search"] = focus_product
        st.session_state["stock_adjust_product"] = focus_product

    master_msg = st.session_state.pop("_stock_master_success_msg", None)
    if master_msg:
        st.success(master_msg)

    adj_df = q("""
        SELECT id, location, company, product_name, warehouse_name, lot, exp_date, qty
        FROM inventory
        WHERE 1=1
        ORDER BY product_name, lot, exp_date, location
    """)
    if adj_df.empty:
        st.info("조정할 현재 재고가 없습니다.")
        return

    adjust_area, _adjust_blank = st.columns([7, 3], gap="large")
    with adjust_area:
        form_left, form_right = st.columns(2, gap="large")

        with form_left:
            search = st.text_input("조정 대상 제품 검색", placeholder="제품명/전산상 명칭/LOT/로케이션 일부를 입력하세요", key="stock_adjust_search")
            filtered = adj_df.copy()
            if search.strip():
                term = search.strip().lower()
                filtered = filtered[
                    filtered["product_name"].fillna("").str.lower().str.contains(term, regex=False)
                    | filtered["warehouse_name"].fillna("").str.lower().str.contains(term, regex=False)
                    | filtered["lot"].fillna("").str.lower().str.contains(term, regex=False)
                    | filtered["location"].fillna("").str.lower().str.contains(term, regex=False)
                ]

            if filtered.empty:
                st.warning("검색어와 일치하는 재고가 없습니다.")
                return

            products = filtered["product_name"].dropna().astype(str).drop_duplicates().tolist()
            product = st.selectbox("제품명", products, key="stock_adjust_product")
            lot_df = filtered[filtered["product_name"] == product].copy()

            lots = lot_df["lot"].fillna("-").astype(str).drop_duplicates().tolist()
            lot = st.selectbox("LOT/제조번호", lots, key=f"stock_adjust_lot_{product}")

            exp_df = lot_df[lot_df["lot"].fillna("-").astype(str) == lot].copy()
            exps = exp_df["exp_date"].fillna("-").astype(str).drop_duplicates().tolist()
            exp = st.selectbox("유통기한", exps, key=f"stock_adjust_exp_{product}_{lot}", format_func=display_date_only)

        target_df = exp_df[exp_df["exp_date"].fillna("-").astype(str) == exp].copy()
        labels = []
        id_by_label = {}
        for r in target_df.itertuples():
            label = f"{r.location} / {r.company} / 현재 {int(r.qty)}EA"
            labels.append(label)
            id_by_label[label] = int(r.id)

        with form_right:
            selected = st.selectbox("조정 대상 로케이션", labels, key=f"stock_adjust_inv_{product}_{lot}_{exp}")
            inv_id = id_by_label[selected]
            row = target_df[target_df["id"] == inv_id].iloc[0]

            actual = st.number_input("실물수량", min_value=0, value=int(row["qty"]), step=1, key=f"stock_adjust_actual_{inv_id}")
            reason = st.selectbox("사유", ["실사차이", "파손", "유통기한만료", "오출고", "기타"], key=f"stock_adjust_reason_{inv_id}")
            memo = st.text_input("메모", placeholder="필요 시 입력", key=f"stock_adjust_memo_{inv_id}")

        st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
        btn_left, btn_mid, btn_right = st.columns([1, 1, 1])
        with btn_mid:
            if st.button("재고조정 저장", type="primary", use_container_width=True, key=f"stock_adjust_submit_{inv_id}"):
                try:
                    before, after, diff = adjust_inventory(int(inv_id), int(actual), reason, memo)
                    st.session_state["_stock_adjust_success_msg"] = f"재고조정 완료: {before}EA → {after}EA ({diff:+d}EA)"
                    st.rerun()
                except Exception as e:
                    st.error(str(e))
        with btn_right:
            if st.button("제품마스터 수정", use_container_width=True, key=f"stock_master_open_{inv_id}"):
                _render_inventory_master_dialog(
                    int(inv_id),
                    row["product_name"],
                    row["lot"],
                    row["exp_date"],
                )

        st.markdown("#### 선택 재고")
        show = target_df[["id", "location", "company", "product_name", "warehouse_name", "lot", "exp_date", "qty"]].copy()
        show = show.rename(columns={
            "id": "ID", "location": "로케이션", "company": "사업장", "product_name": "표준제품명",
            "warehouse_name": "전산상명칭", "lot": "제조번호", "exp_date": "유통기한", "qty": "수량"
        })
        show["유통기한"] = show["유통기한"].apply(display_date_only)
        st.dataframe(show, hide_index=True, use_container_width=True)

    stock_adjust_msg = st.session_state.pop("_stock_adjust_success_msg", None)
    if stock_adjust_msg:
        st.success(stock_adjust_msg)


def _render_stocktake_files():
    from nohtus.services.stocktake import (
        current_baseline_stock_excel_bytes,
        full_inventory_excel_bytes,
        import_stock_survey_excel,
        material_inventory_excel_bytes,
    )

    st.subheader("재고실사 및 기준재고")
    file_area, _file_blank = st.columns([6, 4], gap="large")
    with file_area:
        file_left, file_right = st.columns(2, gap="large")
        with file_left:
            st.markdown("#### 재고 실사용 엑셀")
            exclude_zero = bool(st.session_state.get("stocktake_exclude_zero", True))
            exclude_g = bool(st.session_state.get("stocktake_exclude_series_g", True))
            exclude_x = bool(st.session_state.get("stocktake_exclude_series_x", True))
            exclude_t = bool(st.session_state.get("stocktake_exclude_series_t", True))
            exclude_n = bool(st.session_state.get("stocktake_exclude_series_n", True))
            exclude_series = {
                series
                for series, checked in (
                    ("G", exclude_g), ("X", exclude_x), ("T", exclude_t), ("N", exclude_n),
                )
                if checked
            }
            excel_data = full_inventory_excel_bytes(exclude_zero=exclude_zero, exclude_series=exclude_series)
            st.download_button(
                "재고 실사용 엑셀 내려받기",
                data=excel_data,
                file_name=f"NOHTUS_전체재고실사_{date.today().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
            st.checkbox(
                "재고가 0인 경우는 포함하지 않기",
                value=exclude_zero,
                key="stocktake_exclude_zero",
            )
            st.caption("체크된 계열은 실사용 엑셀에서 제외됩니다.")
            series_col1, series_col2, series_col3, series_col4 = st.columns(4)
            series_col1.checkbox("G계열(부자재)", value=exclude_g, key="stocktake_exclude_series_g")
            series_col2.checkbox("X계열(폐기)", value=exclude_x, key="stocktake_exclude_series_x")
            series_col3.checkbox("T계열(파렛트)", value=exclude_t, key="stocktake_exclude_series_t")
            series_col4.checkbox("기타 위치(창고 외부)", value=exclude_n, key="stocktake_exclude_series_n")

            st.markdown("#### 부자재 재고표")
            material_excel_data = material_inventory_excel_bytes(exclude_zero=exclude_zero)
            st.download_button(
                "부자재 재고표 내려받기",
                data=material_excel_data,
                file_name=f"NOHTUS_부자재재고실사_{date.today().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
            st.caption("부자재 관리에 등록된 제품만 따로 모은 재고표입니다.")

        with file_right:
            st.markdown("#### 기준재고")
            st.download_button(
                "현재 기준 재고 양식 다운로드",
                data=current_baseline_stock_excel_bytes(exclude_zero=False),
                file_name=f"NOHTUS_현재기준재고양식_{date.today().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
            survey_file = st.file_uploader("기준재고 엑셀 선택", type=["xlsx"], key="stock_survey_upload")
            replace_current = st.checkbox("기존 현재재고를 삭제하고 업로드 파일로 교체", value=True, key="stock_survey_replace_current")
            if survey_file is not None:
                st.warning("업로드 실행 시 현재재고가 바뀔 수 있습니다. 운영 DB에서는 파일을 한 번 더 확인하세요.")
                if st.button("기준재고 DB 반영", type="primary", use_container_width=True):
                    try:
                        survey_file.seek(0)
                        inserted, skipped, prod_inserted, ambiguous_skipped = import_stock_survey_excel(survey_file, replace_current=replace_current)
                        st.success(f"반영 완료: 재고 {inserted}건 / 제품매칭표 신규 {prod_inserted}건 / 제외 {skipped}건")
                        st.rerun()
                    except Exception as e:
                        st.error(f"반영 실패: {e}")


def page_stocktake():
    st.title("재고 실사")
    st.caption("WMS 재고를 ERP 및 외부창고 실사재고와 비교하고, 필요한 재고를 직접 조정하거나 실사용 엑셀을 관리합니다.")

    tab_adjust, tab_compare, tab_files = st.tabs(["재고조정", "데이터 비교", "재고실사 및 기준재고"])

    with tab_adjust:
        _render_stock_adjustment()

    with tab_compare:
        _render_stock_comparison()

    with tab_files:
        _render_stocktake_files()
