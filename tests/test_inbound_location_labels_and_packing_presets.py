from pathlib import Path
import unittest


class InboundLocationAndPackingPresetTests(unittest.TestCase):
    def test_inbound_n_is_last_and_displayed_as_other_location(self) -> None:
        source = Path("nohtus/ui/location_picker.py").read_text(encoding="utf-8")

        self.assertIn('[area for area in AREA_CONFIG if area != "N"]', source)
        self.assertIn('"기타 위치" if value == "N" else value', source)

    def test_box_preset_management_uses_button_and_modal(self) -> None:
        source = Path("nohtus/export_app/views/박스_패킹_edit.py").read_text(encoding="utf-8")

        self.assertIn("st.columns([5.6, 4.4]", source)
        self.assertIn("@dialog('프리셋 관리', width='small')", source)
        self.assertIn("preset_select_col, preset_manage_col = st.columns([7, 3])", source)
        self.assertIn("preset_manage_col.button('프리셋 관리'", source)
        self.assertIn("preset_save_col, _preset_save_space = st.columns([1, 1])", source)
        self.assertIn("st.markdown('###### 현재 규격을 프리셋으로 저장')", source)
        self.assertIn("'현재 규격 프리셋 저장'", source)
        self.assertIn("st.markdown('#### 새 프리셋 추가')", source)
        self.assertIn("'가로(cm)'", source)
        self.assertIn("'세로(cm)'", source)
        self.assertIn("'높이(cm)'", source)
        self.assertIn("'무게(kg)'", source)
        self.assertIn("st.markdown('#### 기존 프리셋 수정·삭제')", source)
        self.assertNotIn("with st.expander('프리셋 관리')", source)
        self.assertIn("'관리할 프리셋'", source)
        self.assertIn("'프리셋 수정'", source)
        self.assertIn("'프리셋 삭제'", source)
        self.assertIn("on_change=apply_selected_preset", source)
        self.assertNotIn("'현재 CTN에 적용'", source)
        self.assertIn("format='%d'", source)

    def test_current_ctn_layout_and_management_labels(self) -> None:
        source = Path("nohtus/export_app/views/박스_패킹_edit.py").read_text(encoding="utf-8")

        self.assertIn("dimension_columns = st.columns(4)", source)
        self.assertIn("box_manage_left, box_manage_middle, box_manage_right = st.columns(3", source)
        self.assertIn("with st.expander('박스 번호 변경')", source)
        self.assertIn("with st.expander('선택 제품 박스에서 빼기')", source)
        self.assertIn("with box_manage_middle:", source)
        self.assertIn("with st.expander('CTN 삭제')", source)
        self.assertIn("with box_manage_right:", source)
        self.assertIn("with st.expander('CTN 구성 복제')", source)
        self.assertNotIn("CTN No. 변경", source)
        self.assertNotIn("선택 제품 CTN에서 빼기", source)
        self.assertNotIn("다음 CTN에도 연속 적용", source)
        self.assertNotIn("continuous_box_preset", source)

        save_position = source.index("CTN 저장 후 다음 CTN")
        preset_position = source.index("st.markdown('#### 박스 프리셋')")
        self.assertLess(save_position, preset_position)

    def test_packing_title_and_metric_labels(self) -> None:
        source = Path("nohtus/export_app/views/박스_패킹_edit.py").read_text(encoding="utf-8")

        self.assertIn("st.title('박스 패킹')", source)
        self.assertNotIn("st.title('CTN 패킹')", source)
        self.assertIn('div[data-testid="stMetric"] [data-testid="stMetricLabel"]', source)
        self.assertIn("justify-content:center !important", source)
