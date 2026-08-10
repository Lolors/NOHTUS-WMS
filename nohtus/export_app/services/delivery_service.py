from __future__ import annotations

from nohtus.export_app import db
from nohtus.export_app.services import order_service
from nohtus.export_app.utils.dates import now_text


def save_delivery(
    case_id: int,
    *,
    method: str,
    actual_ship_date: str,
    tracking_no: str = '',
    driver_name: str = '',
    driver_phone: str = '',
    consignee_name: str = '',
    consignee_address: str = '',
) -> None:
    db.execute(
        """UPDATE export_cases
           SET domestic_method=?,tracking_no=?,driver_name=?,driver_phone=?,
               consignee_name=?,consignee_address=?,actual_ship_date=?,
               stage='국내배송',status='완료',updated_at=?
           WHERE id=?""",
        (
            method,
            tracking_no.strip(),
            driver_name.strip(),
            driver_phone.strip(),
            consignee_name.strip(),
            consignee_address.strip(),
            actual_ship_date,
            now_text(),
            case_id,
        ),
    )
    order_service.clear_editable_cases_cache()
