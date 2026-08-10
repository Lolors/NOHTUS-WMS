"""수출관리(EXPORT) 앱을 WMS 프로세스에 연결하는 1회성 초기화.

EXPORT 자체 app.py의 main()이 하던 일 중 화면 렌더링과 무관한 부분
(DB 스키마 준비, 서비스 간 함수 참조 배선)만 옮겨온다.
"""

from nohtus.export_app import db as export_db
from nohtus.export_app.services import (
    folder_name_policy,
    folder_service,
    order_save_guard,
    order_service,
    packing_edit_service,
    packing_service,
    product_name_match_service,
    shipment_service,
    stage_service,
)


def init_export_app():
    export_db.init_db()

    folder_name_policy.install(folder_service)
    order_service.normalize_product_name = product_name_match_service.normalize_for_match
    order_save_guard.install()
    packing_service.list_items = shipment_service.list_case_items
    packing_service.next_box_no = packing_edit_service.next_available_box_no
    shipment_service.sync_case_stage = stage_service.sync_case_stage
    shipment_service.sync_active_case_stages = stage_service.sync_active_case_stages
    packing_service._sync_packing_stage = stage_service.sync_case_stage
