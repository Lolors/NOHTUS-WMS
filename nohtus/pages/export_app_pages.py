"""수출관리(EXPORT) 앱의 9개 화면을 WMS 페이지 함수로 감싼 래퍼."""

import re

import streamlit as st

from nohtus.export_app import db as export_db
from nohtus.export_app.services import packing_service
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
    original_progress = st.progress
    original_success = st.success

    ui_state = {
        "order_fulfilled": False,
        "picker_placeholder": None,
        "picker_outer": None,
        "suppress_progress": False,
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

    def _close_picker_outer():
        outer = ui_state.get("picker_outer")
        if outer is None:
            return
        ui_state["picker_outer"] = None
        try:
            outer.__exit__(None, None, None)
        except Exception:
            pass

    class _FormContext:
        def __init__(self, inner, close_picker=False):
            self.inner = inner
            self.close_picker = close_picker

        def __enter__(self):
            return self.inner.__enter__()

        def __exit__(self, exc_type, exc, tb):
            try:
                return self.inner.__exit__(exc_type, exc, tb)
            finally:
                if self.close_picker:
                    _close_picker_outer()

    def patched_data_editor(data, *args, **kwargs):
        key = str(kwargs.get("key") or "")
        if key.startswith("saved_wms_editor_"):
            kwargs["num_rows"] = "dynamic"
        return original_data_editor(data, *args, **kwargs)

    def patched_button(label, *args, **kwargs):
        if str(label).strip() == "선택 행 삭제" and str(kwargs.get("key") or "").startswith("delete_saved_rows_"):
            return False
        return original_button(label, *args, **kwargs)

    def patched_markdown(body, *args, **kwargs):
        if isinstance(body, str):
            text = body.strip()
            if text == "### 수출대기 저장제품":
                body = "### 수출대기 제품"
            elif text == "##### 저장된 재고":
                if not ui_state["order_fulfilled"] and ui_state["picker_placeholder"] is None:
                    ui_state["picker_placeholder"] = st.empty()
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
                if ui_state["order_fulfilled"]:
                    outer = st.expander("추가할 재고 선택 · 주문수량 충족", expanded=False)
                else:
                    placeholder = ui_state.get("picker_placeholder")
                    outer = placeholder.container() if placeholder is not None else st.container()
                ui_state["picker_outer"] = outer
                outer.__enter__()
                return original_markdown(
                    """
                    <div class="export-picker-section">
                      <div class="export-section-title-row">
                        <span class="export-section-title">추가할 재고 선택</span>
                      </div>
                      <div class="export-section-help">
                        새로 추가할 재고를 검색하고 선택수량을 입력하세요. 부족한 수량이 있으면 이 영역이 수출대기 제품보다 먼저 표시됩니다.
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            elif text == "#### 전체 저장 진행률":
                ui_state["suppress_progress"] = True
                return None
        return original_markdown(body, *args, **kwargs)

    def patched_caption(body, *args, **kwargs):
        text = str(body or "")
        if "삭제할 행은 선택한 뒤 아래의 선택 행 삭제" in text:
            return None
        if ui_state["suppress_progress"] and "품목별 저장률의 평균" in text:
            return None
        return original_caption(body, *args, **kwargs)

    def patched_selectbox(label, options, *args, **kwargs):
        value = original_selectbox(label, options, *args, **kwargs)
        if str(kwargs.get("key") or "").startswith("linked_selected_order_"):
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
        inner = original_form(key, *args, **kwargs)
        key_text = str(key or "")
        return _FormContext(
            inner,
            close_picker=key_text.startswith("wms_pick_form_") and ui_state.get("picker_outer") is not None,
        )

    def patched_progress(*args, **kwargs):
        if ui_state["suppress_progress"]:
            return None
        return original_progress(*args, **kwargs)

    def patched_success(body, *args, **kwargs):
        if ui_state["suppress_progress"] and "모든 주문품목" in str(body or ""):
            return None
        return original_success(body, *args, **kwargs)

    st.data_editor = patched_data_editor
    st.button = patched_button
    st.markdown = patched_markdown
    st.caption = patched_caption
    st.selectbox = patched_selectbox
    st.form = patched_form
    st.progress = patched_progress
    st.success = patched_success
    try:
        with export_db.connection_session():
            실출고_입력.render()
    finally:
        _close_picker_outer()
        st.data_editor = original_data_editor
        st.button = original_button
        st.markdown = original_markdown
        st.caption = original_caption
        st.selectbox = original_selectbox
        st.form = original_form
        st.progress = original_progress
        st.success = original_success


def page_export_sales_registration():
    with export_db.connection_session():
        수출확정_매출_등록.render()


def page_export_packing():
    from nohtus.export_app.components.streamlit_compat import dialog

    original_selectbox = st.selectbox
    original_markdown = st.markdown
    original_expander = st.expander
    original_form_submit_button = st.form_submit_button
    original_toggle = st.toggle

    ui_state = {
        "preset_save_slot": None,
        "continuous_apply_slot": None,
    }

    def preset_label(name: object, presets: dict, last_values: dict | None) -> str:
        text = str(name)
        values = last_values if text == '마지막 사용값' else presets.get(text)
        if not values:
            return text
        try:
            length = float(values.get('length_cm', 0))
            width = float(values.get('width_cm', 0))
            height = float(values.get('height_cm', 0))
            weight = float(values.get('weight_kg', 0))
        except (TypeError, ValueError, AttributeError):
            return text
        return f'{text} ({length:g}x{width:g}x{height:g}) {weight:g}kg'

    @dialog('프리셋 관리', width='large')
    def preset_manager_dialog() -> None:
        st.caption('박스 규격과 무게를 직접 입력해 새 프리셋을 추가합니다.')
        existing = packing_service.list_box_presets()
        if existing:
            st.caption('현재 프리셋: ' + ', '.join(sorted(existing)))

        with st.form('box_preset_manager_add_form'):
            preset_name = st.text_input('프리셋 이름', placeholder='예: 덱스레보')
            size_cols = st.columns(3)
            length = size_cols[0].number_input('가로(cm)', min_value=0.0, step=0.1)
            width = size_cols[1].number_input('세로(cm)', min_value=0.0, step=0.1)
            height = size_cols[2].number_input('높이(cm)', min_value=0.0, step=0.1)
            weight = st.number_input('무게(kg)', min_value=0.0, step=0.1)
            save_preset = original_form_submit_button('프리셋 추가', type='primary', use_container_width=True)

        if save_preset:
            try:
                packing_service.save_box_preset(
                    preset_name,
                    float(length),
                    float(width),
                    float(height),
                    float(weight),
                )
            except ValueError as exc:
                st.error(str(exc))
            else:
                st.success(f'{preset_name.strip()} 프리셋을 추가했습니다.')
                st.rerun()

    def patched_markdown(body, *args, **kwargs):
        result = original_markdown(body, *args, **kwargs)
        if isinstance(body, str) and body.strip() == '#### 박스 프리셋':
            left_spacer, save_col, right_spacer = st.columns([1.5, 7, 1.5])
            with save_col:
                ui_state['preset_save_slot'] = st.container()
        return result

    def patched_selectbox(label, options, *args, **kwargs):
        key = str(kwargs.get('key') or '')
        if str(label).strip() == '프리셋' and key.startswith('box_preset_select_'):
            presets = packing_service.list_box_presets()
            last_values = packing_service.get_last_box_values()
            kwargs['format_func'] = lambda value: preset_label(value, presets, last_values)
            select_col, manage_col = st.columns([7, 3])
            with select_col:
                selected = original_selectbox(label, options, *args, **kwargs)
            with manage_col:
                st.markdown('<div style="height: 1.72rem"></div>', unsafe_allow_html=True)
                if st.button(
                    '프리셋 관리',
                    use_container_width=True,
                    key=f'open_box_preset_manager_{key}',
                ):
                    preset_manager_dialog()
            return selected
        return original_selectbox(label, options, *args, **kwargs)

    def patched_expander(label, *args, **kwargs):
        text = str(label).strip()
        if text == '현재 규격을 새 프리셋으로 저장':
            slot = ui_state.get('preset_save_slot')
            if slot is not None:
                with slot:
                    return original_expander(label, *args, **kwargs)
        if text == 'CTN 삭제':
            original_markdown('#### CTN 삭제')
            return st.container()
        return original_expander(label, *args, **kwargs)

    def patched_form_submit_button(label, *args, **kwargs):
        result = original_form_submit_button(label, *args, **kwargs)
        if str(label).strip() == 'CTN 저장 후 다음 CTN':
            ui_state['continuous_apply_slot'] = st.empty()
        return result

    def patched_toggle(label, *args, **kwargs):
        key = str(kwargs.get('key') or '')
        if str(label).strip() == '다음 CTN에도 연속 적용' and key.startswith('continuous_box_preset_'):
            slot = ui_state.get('continuous_apply_slot')
            if slot is not None:
                with slot:
                    return original_toggle('이 규격을 다음 CTN에도 연속 적용', *args, **kwargs)
            return original_toggle('이 규격을 다음 CTN에도 연속 적용', *args, **kwargs)
        return original_toggle(label, *args, **kwargs)

    st.selectbox = patched_selectbox
    st.markdown = patched_markdown
    st.expander = patched_expander
    st.form_submit_button = patched_form_submit_button
    st.toggle = patched_toggle
    try:
        with export_db.connection_session():
            박스_패킹_edit.render()
    finally:
        st.selectbox = original_selectbox
        st.markdown = original_markdown
        st.expander = original_expander
        st.form_submit_button = original_form_submit_button
        st.toggle = original_toggle


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
