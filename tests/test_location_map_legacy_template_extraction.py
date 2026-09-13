"""location_map_legacy.py의 620줄짜리 f-string 중 완전히 정적인 부분
(<style> 블록, <script> 블록의 `const DATA = ...;` 이후 전체)을
nohtus/services/location_map_assets/{map.css,map.js} 파일로 분리했다.
이 테스트는 그 분리가 "동작은 그대로, 코드 구조만 바뀜"이었는지를
바이트 단위로 고정한다 — render_location_map()의 최종 출력이 파일
분리 전과 정확히 같은 문자열을 만들어내는지 확인한다(2026-09-13
기준으로 캡처한 골든 출력과 비교).

기존 enhanced_html 패치 체인(services/location_map.py)이나
apply_new_layout(location_map_new_layout.py)은 건드리지 않았다 —
둘 다 이 함수가 반환하는 최종 HTML 문자열을 대상으로 동작하므로,
문자열이 바이트 단위로 동일하면 그대로 계속 동작한다."""

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import nohtus.db as db
import nohtus.services.location_map_legacy as legacy

_GOLDEN_HTML_PATH = Path(__file__).parent / "fixtures" / "location_map_legacy_golden.html"


class LocationMapLegacyTemplateExtractionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self.temp_dir.name) / "wms.db"
        con = sqlite3.connect(self.db_path)
        try:
            con.executescript(
                """
                CREATE TABLE inventory(
                    id INTEGER PRIMARY KEY, company TEXT, product_name TEXT,
                    warehouse_name TEXT, lot TEXT, exp_date TEXT, location TEXT,
                    location_range_end TEXT, location_range_cells TEXT, qty INTEGER
                );
                INSERT INTO inventory VALUES(1,'노투스','테스트제품','ERP-1','LOT-1','2027-01-01','P-1',NULL,NULL,10);
                CREATE TABLE transactions(
                    id INTEGER PRIMARY KEY, created_at TEXT, tx_type TEXT,
                    product_name TEXT, lot TEXT, exp_date TEXT,
                    from_location TEXT, to_location TEXT, qty INTEGER
                );
                """
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

        self.components_patcher = patch.object(legacy.components, "html", capture_html)
        self.components_patcher.start()

    def tearDown(self):
        self.components_patcher.stop()
        self.db_path_patcher.stop()
        try:
            self.temp_dir.cleanup()
        except PermissionError:
            pass

    def test_output_is_byte_identical_to_pre_extraction_golden(self):
        legacy.render_location_map()
        rendered = self.captured_html["value"]
        golden = _GOLDEN_HTML_PATH.read_text(encoding="utf-8")
        self.assertEqual(rendered, golden)


if __name__ == "__main__":
    unittest.main()
