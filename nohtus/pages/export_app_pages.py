"""수출관리(EXPORT) 앱의 9개 화면을 WMS 페이지 함수로 감싼 래퍼."""

import streamlit as st

from nohtus.export_app import db as export_db
# views가 update_confirmed_export_waiting_items를 import하기 전에 수정 이력 패치를 적용한다.
import nohtus.services.export_confirm_history_patch  # noqa: F401
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
    수출확정_매출_등록,
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
    """저장 재고는 Streamlit 표의 기본 행 삭제 기능으로 편집한다."""
    original_data_editor = st.data_editor
    original_button = st.button

    def patched_data_editor(data, *args, **kwargs):
        key = str(kwargs.get("key") or "")
        if key.startswith("saved_wms_editor_"):
            kwargs["num_rows"] = "dynamic"
            # 기존 선택 체크 컬럼은 내부 호환을 위해 데이터에는 남기되 화면에서는 숨긴다.
            column_config = dict(kwargs.get("column_config") or {})
            column_config["선택"] = None
            kwargs["column_config"] = column_config
            column_order = list(kwargs.get("column_order") or [])
            kwargs["column_order"] = [column for column in column_order if column != "선택"]
        return original_data_editor(data, *args, **kwargs)

    def patched_button(label, *args, **kwargs):
        if str(label).strip() == "선택 행 삭제" and str(kwargs.get("key") or "").startswith("delete_saved_rows_"):
            return False
        return original_button(label, *args, **kwargs)

    st.data_editor = patched_data_editor
    st.button = patched_button
    try:
        with export_db.connection_session():
            실출고_입력.render()
    finally:
        st.data_editor = original_data_editor
        st.button = original_button


def page_export_sales_registration():
    with export_db.connection_session():
        수출확정_매출_등록.render()


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
