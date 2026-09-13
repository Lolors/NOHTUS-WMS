"""services/location_map.py::render_location_map()가 만드는 최종 HTML 특성화 테스트.

이 파이프라인(enhanced_html의 순차 .replace() 패치 + apply_new_layout)은
이전까지 테스트가 전무했다. 그 결과 수출대기(P존) 카드 그룹핑 패치가
실제로 존재하지 않는 문자열을 타겟으로 삼아 조용히 무효화되어 있던 버그가
한동안 발견되지 않았다. 이 테스트는 (1) 그 버그가 다시 생기지 않는지,
(2) 나머지 패치들도 legacy 템플릿에 계속 매치되는지를 함께 지킨다.
"""

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import nohtus.db as db
import nohtus.services.location_map as location_map
import nohtus.services.location_map_legacy as location_map_legacy


class LocationMapEnhancedHtmlTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self.temp_dir.name) / "wms.db"
        con = sqlite3.connect(self.db_path)
        try:
            con.execute(
                """CREATE TABLE inventory(
                    id INTEGER PRIMARY KEY, company TEXT, product_name TEXT,
                    warehouse_name TEXT, lot TEXT, exp_date TEXT, location TEXT,
                    location_range_end TEXT, location_range_cells TEXT, qty INTEGER
                )"""
            )
            con.execute(
                "INSERT INTO inventory VALUES(1,'노투스','테스트제품','ERP-1','LOT-1','2027-01-01','P-1',NULL,NULL,10)"
            )
            con.execute(
                "CREATE TABLE products(standard_name TEXT, image_path TEXT)"
            )
            con.execute(
                """CREATE TABLE transactions(
                    id INTEGER PRIMARY KEY, created_at TEXT, tx_type TEXT,
                    product_name TEXT, lot TEXT, exp_date TEXT,
                    from_location TEXT, to_location TEXT, qty INTEGER, memo TEXT
                )"""
            )
            con.commit()
        finally:
            con.close()

        self.db_path_patcher = patch.object(db, "DB_PATH", self.db_path)
        self.db_path_patcher.start()

        self.captured_html = {}

        def capture_html(html, *args, **kwargs):
            self.captured_html["value"] = html
            return None

        self.components_patcher = patch.object(location_map_legacy.components, "html", capture_html)
        self.components_patcher.start()

    def tearDown(self):
        self.components_patcher.stop()
        self.db_path_patcher.stop()
        try:
            self.temp_dir.cleanup()
        except PermissionError:
            pass

    def _rendered_html(self):
        location_map.render_location_map()
        return self.captured_html["value"]

    def test_export_waiting_p_zone_grouping_is_actually_wired(self):
        html = self._rendered_html()

        self.assertIn("function exportWaitingCardsHtml(fallbackRows){", html)
        self.assertIn(
            "html+=(loc==='P' ? exportWaitingCardsHtml(rows) : productCardsHtml(rows));",
            html,
        )
        # 고쳐지기 전 원본의 죽은 타겟 문자열이 다시 나타나면 패치가 또
        # 무효화된 것이다.
        self.assertNotIn("html+=productCardsHtml(rows);", html)
        self.assertNotIn("grouped[lvl]", html)

    def test_new_layout_markup_is_applied(self):
        html = self._rendered_html()

        self.assertIn('id="mapZoomLevel"', html)
        self.assertIn('class="special-menu"', html)

    def test_all_enhanced_html_patches_still_match_legacy_template(self):
        """enhanced_html의 .replace() 타겟이 legacy 템플릿에서 사라지면 조용히
        무시되던 것과 같은 종류의 회귀를 로그 경고로 잡아낸다."""
        with self.assertNoLogs("nohtus.services.location_map", level="WARNING"):
            self._rendered_html()


if __name__ == "__main__":
    unittest.main()
