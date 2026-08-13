from pathlib import Path
import unittest


class BomFinishedProductSearchTests(unittest.TestCase):
    def test_existing_bom_products_are_searchable(self) -> None:
        source = Path("nohtus/pages/material_management.py").read_text(encoding="utf-8")

        self.assertIn('"BOM 완제품 검색"', source)
        self.assertIn('placeholder="완제품명 일부를 입력하세요"', source)
        self.assertIn("filtered_existing = [name for name in existing", source)
        self.assertIn('st.session_state["bom_active_finished"] = selected_existing', source)
        self.assertIn('st.info("검색 결과가 없습니다.")', source)

    def test_bom_composition_table_uses_half_width(self) -> None:
        source = Path("nohtus/pages/material_management.py").read_text(encoding="utf-8")

        self.assertIn("bom_list_col, _bom_list_space = st.columns([65, 35])", source)
        self.assertIn("with bom_list_col:", source)

    def test_bom_quantity_label_is_short(self) -> None:
        source = Path("nohtus/pages/material_management.py").read_text(encoding="utf-8")

        self.assertNotIn("완제품 1개당 소요량", source)
        self.assertIn('"quantity_per": "소요량"', source)
