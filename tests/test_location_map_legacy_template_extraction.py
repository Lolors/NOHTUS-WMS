"""외부 CSS/JS를 포함한 도면 HTML이 승인된 스냅샷과 일치하는지 검증한다.

2026-09-30: 매입대기 배지, 정상재고 합계 제외, 이동 버튼 제외를 반영했다.
기존 enhanced_html 패치 체인의 동작은 별도 관련 테스트로 함께 검증한다.
"""

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

    def test_output_matches_approved_golden(self):
        legacy.render_location_map()
        rendered = self.captured_html["value"]
        golden = _GOLDEN_HTML_PATH.read_text(encoding="utf-8")
        self.assertEqual(rendered, golden)


if __name__ == "__main__":
    unittest.main()
