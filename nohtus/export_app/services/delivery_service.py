from __future__ import annotations

from nohtus.export_app import db
from nohtus.export_app.services import order_service
from nohtus.export_app.utils.dates import now_text


def search_address_book(query: str = '', limit: int = 30) -> list[dict]:
    """과거 국내배송에 실제로 쓰인 수하인명/주소를 최근 사용순으로 검색한다.

    별도 주소록 테이블이 없어서 export_cases에 이미 저장된 수하인 정보를
    (이름, 주소) 쌍으로 중복 제거해 재사용한다."""
    rows = db.rows(
        """
        SELECT TRIM(consignee_name) AS name, TRIM(consignee_address) AS address,
               MAX(updated_at) AS last_used
        FROM export_cases
        WHERE TRIM(COALESCE(consignee_name, '')) != ''
          AND TRIM(COALESCE(consignee_address, '')) != ''
        GROUP BY TRIM(consignee_name), TRIM(consignee_address)
        ORDER BY last_used DESC
        """
    )
    entries = [{'name': row['name'], 'address': row['address']} for row in rows]

    needle = query.strip().casefold()
    if needle:
        entries = [entry for entry in entries if needle in entry['name'].casefold()]

    return entries[:limit]


def save_delivery_draft(
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
    """완료 처리 없이 배송 정보만 미리 저장한다."""
    db.execute(
        """UPDATE export_cases
           SET domestic_method=?,tracking_no=?,driver_name=?,driver_phone=?,
               consignee_name=?,consignee_address=?,actual_ship_date=?,
               updated_at=?
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
