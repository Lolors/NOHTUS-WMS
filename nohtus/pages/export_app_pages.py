"""수출관리(EXPORT) 앱의 9개 화면을 WMS 페이지 함수로 감싼 래퍼."""

from nohtus.export_app import db as export_db
from nohtus.export_app.views import (
    공유문서,
    국내배송,
    기간별_통계,
    내_폴더,
    박스_패킹_edit,
    수출_주문_입력_및_수정,
    실출고_입력,
    오버뷰,
    주문_검색_및_수정,
)


def page_export_dashboard():
    with export_db.connection_session():
        오버뷰.render()


def page_export_order_entry():
    with export_db.connection_session():
        수출_주문_입력_및_수정.render()


def page_export_order_search():
    with export_db.connection_session():
        주문_검색_및_수정.render()


def page_export_shipment_intake():
    with export_db.connection_session():
        실출고_입력.render()


def page_export_packing():
    with export_db.connection_session():
        박스_패킹_edit.render()


def page_export_domestic_delivery():
    with export_db.connection_session():
        국내배송.render()


def page_export_shared_documents():
    with export_db.connection_session():
        공유문서.render()


def page_export_statistics():
    with export_db.connection_session():
        기간별_통계.render()


def page_export_my_folder():
    with export_db.connection_session():
        내_폴더.render()
