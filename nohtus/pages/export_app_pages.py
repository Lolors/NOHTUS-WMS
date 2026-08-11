"""수출관리(EXPORT) 앱의 9개 화면을 WMS 페이지 함수로 감싼 래퍼."""

import re

import streamlit as st

from nohtus.export_app import db as export_db
# views가 update_confirmed_export_waiting_items를 import하기 전에 수정 이력 패치를 적용한다.
import nohtus.services.export_confirm_history_patch  # noqa: F401
# 수출대기 저장의 추가/수량수정/행삭제를 WMS 수출대기 상태와 안전하게 동기화한다.
import nohtus.export_app.services.wms_link_edit_patch  # noqa: F401
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
    """수출대기 제품과 새로 추가할 재고를 시각적으로 구분해 편집한다."""
    original_data_editor = st.data_editor
    original_button = st.button
    original_markdown = st.markdown
    original_caption = st.caption
    original_selectbox = st.selectbox
    original_form = st.form
    original_form_submit_button = st.form_submit_button

    ui_state = {
        "order_fulfilled": False,
        "picker_expander_active": False,
    }

    original_markdown(
        """
        <style>
        .export-saved-section,
        .export-picker-section {
            border-radius: 12px;
            padding: 14px 16px 12px;
            margin: 18px 0 8px;
            border: 1px solid rgba(49, 51, 63, 0.10);
        }
        .export-saved-section {
            background: #eef6ff;
            border-color: #cfe3fb;
        }
        .export-picker-section {
            background: #f7f8fa;
            border-color: #e2e5ea;
        }
        .export-section-title-row {
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 5px;
        }
        .export-section-title {
            font-size: 1.08rem;
            font-weight: 750;
            color: #222b3a;
        }
        .export-status-badge {
            display: inline-flex;
            align-items: center;
            padding: 3px 8px;
            border-radius: 999px;
            background: #d7ebff;
            color: #0b5cad;
            font-size: 0.76rem;
            font-weight: 700;
            white-space: nowrap;
        }
        .export-section-help {
            color: #667085;
            font-size: 0.88rem;
            line-height: 1.45;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    def patched_data_editor(data, *args, **kwargs):
        key = str(kwargs.get("key") or "")
        if key.startswith("saved_wms_editor_"):
            # 행 삭제 기능은 유지하되, 사용자가 요청한 선택 체크박스도 그대로 보인다.
            kwargs["num_rows"] = "dynamic"
        return original_data_editor(data, *args, **kwargs)

    def patched_button(label, *args, **kwargs):
        # 저장된 재고 삭제는 data_editor의 행 삭제 기능으로 처리한다.
        if str(label).strip() == "선택 행 삭제" and str(kwargs.get("key") or "").startswith("delete_saved_rows_"):
            return False
        return original_button(label, *args, **kwargs)

    def patched_markdown(body, *args, **kwargs):
        if isinstance(body, str):
            text = body.strip()
            if text == "### 수출대기 저장제품":
                body = "### 수출대기 제품"
            elif text == "##### 저장된 재고":
                return original_markdown(
                    """
                    <div class="export-saved-section">
                      <div class="export-section-title-row">
                        <span class="export-section-title">수출대기 제품</span>
                        <span class="export-status-badge">현재 저장됨</span>
                      </div>
                      <div class="export-section-help">
                        현재 이 주문에 연결된 재고입니다. 선택수량을 수정하거나 표의 행 삭제 기능으로 제거한 뒤 출고 저장을 누르세요.
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            elif text == "##### 재고 선택":
                return original_markdown(
                    """
                    <div class="export-picker-section">
                      <div class="export-section-title-row">
                        <span class="export-section-title">추가할 재고 선택</span>
                      </div>
                      <div class="export-section-help">
                        새로 추가할 재고를 검색하고 선택수량을 입력하세요. 주문 수량이 이미 충족된 경우 아래 선택 표는 기본으로 접혀 있습니다.
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        return original_markdown(body, *args, **kwargs)

    def patched_caption(body, *args, **kwargs):
        text = str(body or "")
        # 위 섹션 설명은 제목 카드 안에서 더 직접적으로 보여준다.
        if "삭제할 행은 선택한 뒤 아래의 선택 행 삭제" in text:
            return None
        return original_caption(body, *args, **kwargs)

    def patched_selectbox(label, options, *args, **kwargs):
        value = original_selectbox(label, options, *args, **kwargs)
        if str(kwargs.get("key") or "").startswith("linked_selected_order_"):
            # 표시 문자열: '🟢 제품명 · 10 / 10 EA'
            match = re.search(r"·\s*([\d,.]+)\s*/\s*([\d,.]+)", str(value or ""))
            if match:
                try:
                    linked = float(match.group(1).replace(",", ""))
                    ordered = float(match.group(2).replace(",", ""))
                    ui_state["order_fulfilled"] = ordered > 0 and linked >= ordered
                except ValueError:
                    ui_state["order_fulfilled"] = False
            else:
                ui_state["order_fulfilled"] = False
        return value

    def patched_form(key, *args, **kwargs):
        key_text = str(key or "")
        if key_text.startswith("wms_pick_form_") and ui_state["order_fulfilled"]:
            ui_state["picker_expander_active"] = True
            return st.expander("추가할 재고 선택 표 · 주문수량 충족", expanded=False)
        ui_state["picker_expander_active"] = False
        return original_form(key, *args, **kwargs)

    def patched_form_submit_button(label, *args, **kwargs):
        if ui_state["picker_expander_active"]:
            ui_state["picker_expander_active"] = False
            return original_button(label, *args, **kwargs)
        return original_form_submit_button(label, *args, **kwargs)

    st.data_editor = patched_data_editor
    st.button = patched_button
    st.markdown = patched_markdown
    st.caption = patched_caption
    st.selectbox = patched_selectbox
    st.form = patched_form
    st.form_submit_button = patched_form_submit_button
    try:
        with export_db.connection_session():
            실출고_입력.render()
    finally:
        st.data_editor = original_data_editor
        st.button = original_button
        st.markdown = original_markdown
        st.caption = original_caption
        st.selectbox = original_selectbox
        st.form = original_form
        st.form_submit_button = original_form_submit_button


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
