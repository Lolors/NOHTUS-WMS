import unittest

from nohtus.config import AREA_CONFIG
from nohtus.locations import parse_location


class InboundAreaLineSyncTests(unittest.TestCase):
    """입고 위치 콤보박스(구역/라인/단)가 실제 로케이션맵 도면
    (data/location_map_layout.json)과 같은 범위를 가져야 라인까지 연동된다."""

    def test_a1_has_all_fifteen_physical_lines(self):
        self.assertEqual(AREA_CONFIG["A1"]["lines"], [f"{i:02d}" for i in range(1, 16)])

    def test_b1_has_all_twelve_physical_lines(self):
        self.assertEqual(AREA_CONFIG["B1"]["lines"], [f"{i:02d}" for i in range(1, 13)])

    def test_c1_has_all_six_physical_lines(self):
        self.assertEqual(AREA_CONFIG["C1"]["lines"], [f"{i:02d}" for i in range(1, 7)])

    def test_d1_has_all_twelve_physical_lines(self):
        self.assertEqual(AREA_CONFIG["D1"]["lines"], [f"{i:02d}" for i in range(1, 13)])

    def test_e1_has_all_nine_physical_lines(self):
        self.assertEqual(AREA_CONFIG["E1"]["lines"], [f"{i:02d}" for i in range(1, 10)])

    def test_clicked_line_beyond_old_six_is_parsed_and_selectable(self):
        for loc in ("A1-10", "B1-09", "D1-11", "E1-08"):
            with self.subTest(loc=loc):
                area, line, _level = parse_location(loc)
                self.assertIn(line, AREA_CONFIG[area]["lines"])

    def test_closet_zones_are_registered_as_selectable_areas(self):
        for closet in ("옷장1", "옷장2", "옷장3", "옷장4", "옷장5"):
            with self.subTest(closet=closet):
                self.assertIn(closet, AREA_CONFIG)
                self.assertEqual(AREA_CONFIG[closet], {"lines": [], "levels": []})


if __name__ == "__main__":
    unittest.main()
