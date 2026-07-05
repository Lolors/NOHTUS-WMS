from io import BytesIO

import pandas as pd

import nohtus.pages.stocktake as stocktake_page
import nohtus.services.stocktake as stocktake_service
from nohtus.db import q
from nohtus.dates import display_date_only


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


def page_stocktake():
    original_full_inventory_excel_bytes = stocktake_service.full_inventory_excel_bytes
    stocktake_service.full_inventory_excel_bytes = full_inventory_excel_bytes_business
    try:
        return stocktake_page.page_stocktake()
    finally:
        stocktake_service.full_inventory_excel_bytes = original_full_inventory_excel_bytes
