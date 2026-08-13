from pathlib import Path
import unittest


class DeviceMobileQueryTests(unittest.TestCase):
    def test_desktop_removes_mobile_query_instead_of_writing_zero(self) -> None:
        source = Path("nohtus/device.py").read_text(encoding="utf-8")

        self.assertIn('url.searchParams.set("wms_mobile", "1")', source)
        self.assertIn('url.searchParams.delete("wms_mobile")', source)
        self.assertNotIn('url.searchParams.set("wms_mobile", isMobile)', source)
