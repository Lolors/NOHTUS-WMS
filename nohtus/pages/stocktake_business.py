from datetime import datetime
from io import BytesIO

import pandas as pd

import nohtus.pages.stocktake as stocktake_page
import nohtus.services.stocktake as stocktake_service
from nohtus.db import connect, q
from nohtus.dates import display_date_only, normalize_exp_date
from nohtus.services.inventory import insert_transaction_log
from nohtus.services.export_waiting import ensure_export_waiting_tables


def full_inventory_excel_bytes_business(exclude_zero=True):
    where_sql = "WHERE qty<>0" if exclude_zero else ""
    df = q(
        f"""
        SELECT company, location, product_name, exp_date, qty
        FROM inventory
        {where_sql}
        ORDER BY company, location, product_name, exp_date
        """
    )

    out = pd.DataFrame()
    out["사업장"] = df["company"] if not df.empty else []
    out["로케이션"] = df["location"] if not df.empty else []
    out["제품명"] = df["product_name"] if not df.empty else []
    out["유통기한"] = df["exp_date"].apply(display_date_only) if not df.empty else []
    out["전산수량"] = df["qty"] if not df.empty else []
    out["실물수량"] = ""

    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        out.to_excel(writer, index=False, sheet_name="전체재고실사")
        ws = writer.book["전체재고실사"]
        widths = {"A": 14, "B": 16, "C": 34, "D": 16, "E": 12, "F": 12}
        for col, width in widths.items():
            ws.column_dimensions[col].width = width

        from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

        thin = Side(style="thin", color="000000")
        border = Border(left=thin, right=thin, top=thin, bottom=thin)
        header_fill = PatternFill("solid", fgColor="E5E7EB")
        for row in ws.iter_rows():
            for cell in row:
                cell.border = border
                cell.alignment = Alignment(vertical="center")
                if cell.row == 1:
                    cell.font = Font(bold=True)
                    cell.fill = header_fill
    bio.seek(0)
    return bio.getvalue()


def _update_inventory_and_product_mappings_business(inv_id, product_name, lot, exp_date, edited_mappings):
    product_name = str(product_name or "").strip()
    if not product_name:
        raise ValueError("제품명을 입력하세요.")

    lot = stocktake_page._normalize_master_text(lot)
    exp_date = normalize_exp_date(exp_date)
    mapping_rows = edited_mappings.copy()
    if "id" not in mapping_rows.columns:
        mapping_rows.insert(0, "id", None)

    with connect() as con:
        ensure_export_waiting_tables(con.cursor())
        current = con.execute(
            """
            SELECT product_name, company, COALESCE(warehouse_name,''),
                   COALESCE(location,''), qty,
                   COALESCE(lot,'-'), COALESCE(exp_date,'-')
            FROM inventory
            WHERE id=?
            """,
            (int(inv_id),),
        ).fetchone()
        if not current:
            raise ValueError("수정할 재고를 찾을 수 없습니다.")

        old_product_name = str(current[0] or "").strip()
        company = str(current[1] or "").strip()
        warehouse_name = str(current[2] or "").strip()
        location = str(current[3] or "").strip()
        current_qty = int(current[4] or 0)
        old_lot = stocktake_page._normalize_master_text(current[5])
        old_exp_date = normalize_exp_date(current[6])

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
            duplicate = con.execute(
                """
                SELECT id, qty
                FROM inventory
                WHERE id<>?
                  AND company=?
                  AND product_name=?
                  AND COALESCE(warehouse_name,'')=?
                  AND COALESCE(lot,'-')=?
                  AND COALESCE(exp_date,'-')=?
                  AND location=?
                ORDER BY id
                LIMIT 1
                """,
                (
                    int(inv_id),
                    company,
                    product_name,
                    warehouse_name,
                    lot,
                    exp_date,
                    location,
                ),
            ).fetchone()

            merged_qty = current_qty
            if duplicate:
                duplicate_id = int(duplicate[0])
                merged_qty += int(duplicate[1] or 0)
                # 병합되어 삭제될 P 재고를 가리키는 수출대기 연결은 유지되는 행으로 옮긴다.
                con.execute(
                    """UPDATE export_waiting_items
                       SET waiting_inventory_id=?
                       WHERE COALESCE(confirmed,0)=0 AND waiting_inventory_id=?""",
                    (int(inv_id), duplicate_id),
                )
                con.execute("DELETE FROM inventory WHERE id=?", (duplicate_id,))

            con.execute(
                """
                UPDATE inventory
                SET product_name=?, lot=?, exp_date=?, qty=?
                WHERE id=?
                """,
                (product_name, lot, exp_date, merged_qty, int(inv_id)),
            )

            # 실제 재고실사 화면이 사용하는 저장 경로에서 원본 재고 또는
            # P 재고 ID로 연결된 미확정 수출대기 품목만 정확히 갱신한다.
            con.execute(
                """
                UPDATE export_waiting_items
                SET product_name=?, lot=?, exp_date=?
                WHERE COALESCE(confirmed,0)=0
                  AND (source_inventory_id=? OR waiting_inventory_id=?)
                """,
                (product_name, lot, exp_date, int(inv_id), int(inv_id)),
            )

            # 과거 수출대기에는 P 재고 ID가 없을 수 있다. 이때 수량이나 제품명만으로
            # 후보 하나를 추정하면 같은 제품의 다른 제조번호를 잘못 고르거나, 후보가
            # 여러 개라는 이유로 아무것도 갱신하지 못한다. 저장 직전 P 재고의 전체
            # 서명(사업장·제품·창고·제조번호·유통기한)과 정확히 같은 미연결 품목을
            # 모두 현재 P 재고에 연결한다. 같은 서명의 품목들은 실제로 하나의 P
            # 재고행에 합산되는 동일 재고 묶음이므로 함께 갱신하는 것이 맞다.
            if location.upper() == "P":
                con.execute(
                    """
                    UPDATE export_waiting_items
                    SET waiting_inventory_id=?, product_name=?, lot=?, exp_date=?
                    WHERE COALESCE(confirmed,0)=0
                      AND waiting_inventory_id IS NULL
                      AND TRIM(COALESCE(company,''))=?
                      AND TRIM(COALESCE(product_name,''))=?
                      AND TRIM(COALESCE(warehouse_name,''))=?
                      AND TRIM(COALESCE(lot,'-'))=?
                      AND TRIM(COALESCE(exp_date,'-'))=?
                    """,
                    (
                        int(inv_id),
                        product_name,
                        lot,
                        exp_date,
                        company,
                        old_product_name,
                        warehouse_name,
                        old_lot,
                        old_exp_date,
                    ),
                )

            kept_ids = set()
            for _, mapping in mapping_rows.iterrows():
                values = {
                    db_column: stocktake_page._clean_mapping_text(mapping.get(label))
                    for label, db_column in stocktake_page.PRODUCT_MAPPING_DB_COLUMNS.items()
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
        except Exception:
            con.rollback()
            raise

    return product_name, lot, exp_date, len(mapping_rows)


def import_stock_survey_excel_business(uploaded_file, replace_current=True):
    normal_df, issue_df = stocktake_service.prepare_baseline_stock_dataframe(uploaded_file)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    inserted = 0
    skipped = int(len(issue_df)) if issue_df is not None else 0
    product_inserted = 0

    with connect() as con:
        cur = con.cursor()
        try:
            if replace_current:
                cur.execute("DELETE FROM inventory")
                cur.execute("DELETE FROM transactions WHERE tx_type='재고조사불러오기'")

            for _, r in normal_df.iterrows():
                company = str(r.get("사업장") or "").strip()
                code = str(r.get("ERP제품코드") or "").strip()
                product_raw = str(r.get("ERP제품명") or "").strip()
                product = str(r.get("표준제품명") or "").strip()
                lot = str(r.get("LOT/제조번호") or "").strip() or "-"
                exp = stocktake_service._excel_date_to_iso(r.get("유통기한"))
                loc = str(r.get("로케이션") or "").strip()
                qty = int(float(r.get("수량") or 0))
                if not company or not product or not loc or qty <= 0:
                    skipped += 1
                    continue

                exists = cur.execute(
                    "SELECT id FROM products WHERE standard_name=? ORDER BY id LIMIT 1",
                    (product,),
                ).fetchone()
                if not exists:
                    cur.execute(
                        """
                        INSERT INTO products(
                            product_code, standard_name, warehouse_name, aliases,
                            erp_nohtuspharm_name, erp_noh_name, erp_noh_code,
                            erp_nohtus_name, bidata_name
                        ) VALUES(?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            code if company == "노투스팜" else "",
                            product,
                            product_raw,
                            "",
                            product_raw if company == "노투스팜" else "",
                            product_raw if company == "NOH" else "",
                            code if company == "NOH" else "",
                            product_raw if company == "노투스" else "",
                            product_raw if company == "비자료" else "",
                        ),
                    )
                    product_inserted += 1
                else:
                    pid = int(exists[0])
                    if company == "노투스팜":
                        cur.execute(
                            "UPDATE products SET erp_nohtuspharm_name=COALESCE(NULLIF(erp_nohtuspharm_name,''), ?), product_code=COALESCE(NULLIF(product_code,''), ?) WHERE id=?",
                            (product_raw, code, pid),
                        )
                    elif company == "NOH":
                        cur.execute(
                            "UPDATE products SET erp_noh_name=COALESCE(NULLIF(erp_noh_name,''), ?), erp_noh_code=COALESCE(NULLIF(erp_noh_code,''), ?) WHERE id=?",
                            (product_raw, code, pid),
                        )
                    elif company == "노투스":
                        cur.execute(
                            "UPDATE products SET erp_nohtus_name=COALESCE(NULLIF(erp_nohtus_name,''), ?) WHERE id=?",
                            (product_raw, pid),
                        )
                    elif company == "비자료":
                        cur.execute(
                            "UPDATE products SET bidata_name=COALESCE(NULLIF(bidata_name,''), ?) WHERE id=?",
                            (product_raw, pid),
                        )

                existing_inventory = cur.execute(
                    """
                    SELECT id, qty
                    FROM inventory
                    WHERE company=?
                      AND product_name=?
                      AND COALESCE(warehouse_name,'')=?
                      AND COALESCE(lot,'-')=?
                      AND COALESCE(exp_date,'-')=?
                      AND location=?
                    ORDER BY id
                    LIMIT 1
                    """,
                    (company, product, product_raw, lot, exp, loc),
                ).fetchone()

                if existing_inventory:
                    inventory_id = int(existing_inventory[0])
                    merged_qty = int(existing_inventory[1] or 0) + qty
                    cur.execute(
                        "UPDATE inventory SET qty=?, updated_at=? WHERE id=?",
                        (merged_qty, now, inventory_id),
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO inventory(
                            company, product_name, warehouse_name, lot,
                            exp_date, location, qty, updated_at
                        ) VALUES(?,?,?,?,?,?,?,?)
                        """,
                        (company, product, product_raw, lot, exp, loc, qty, now),
                    )

                insert_transaction_log(
                    cur,
                    created_at=now,
                    tx_type="재고조사불러오기",
                    product_name=product,
                    warehouse_name=product_raw,
                    lot=lot,
                    exp_date=exp,
                    from_company=None,
                    from_location=None,
                    to_company=company,
                    to_location=loc,
                    qty=qty,
                    memo=f"기준재고 엑셀 업로드 / 원본명: {product_raw}",
                )
                inserted += 1

            con.commit()
        except Exception:
            con.rollback()
            raise

    return inserted, skipped, product_inserted, skipped


def page_stocktake():
    original_full_inventory_excel_bytes = stocktake_service.full_inventory_excel_bytes
    original_import_stock_survey_excel = stocktake_service.import_stock_survey_excel
    original_update_master = stocktake_page._update_inventory_and_product_mappings

    stocktake_service.full_inventory_excel_bytes = full_inventory_excel_bytes_business
    stocktake_service.import_stock_survey_excel = import_stock_survey_excel_business
    stocktake_page._update_inventory_and_product_mappings = _update_inventory_and_product_mappings_business
    try:
        return stocktake_page.page_stocktake()
    finally:
        stocktake_service.full_inventory_excel_bytes = original_full_inventory_excel_bytes
        stocktake_service.import_stock_survey_excel = original_import_stock_survey_excel
        stocktake_page._update_inventory_and_product_mappings = original_update_master
