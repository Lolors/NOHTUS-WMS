"""Small smoke checks for NOHTUS WMS refactoring.

Run from the repository root:

    python tools/smoke_check.py

This does not start Streamlit. It only checks that important Python modules compile
and that the refactor support modules can be imported.
"""

from __future__ import annotations

import py_compile
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FILES_TO_COMPILE = [
    ROOT / "app.py",
    ROOT / "styles.py",
    ROOT / "inbound_map.py",
    ROOT / "nohtus" / "__init__.py",
    ROOT / "nohtus" / "config.py",
    ROOT / "nohtus" / "db.py",
    ROOT / "nohtus" / "navigation.py",
    ROOT / "nohtus" / "dates.py",
    ROOT / "nohtus" / "locations.py",
    ROOT / "nohtus" / "pages" / "__init__.py",
    ROOT / "nohtus" / "services" / "__init__.py",
    ROOT / "nohtus" / "ui" / "__init__.py",
]

OPTIONAL_FILES_TO_COMPILE = [
    ROOT / "nohtus" / "services" / "inventory.py",
    ROOT / "nohtus" / "services" / "products.py",
]


def main() -> None:
    missing = [path for path in FILES_TO_COMPILE if not path.exists()]
    if missing:
        raise SystemExit("Missing files:\n" + "\n".join(str(p) for p in missing))

    for path in FILES_TO_COMPILE + [p for p in OPTIONAL_FILES_TO_COMPILE if p.exists()]:
        py_compile.compile(str(path), doraise=True)
        print(f"OK compile: {path.relative_to(ROOT)}")

    from nohtus.config import APP_TITLE, COMPANIES, AREA_CONFIG
    from nohtus.db import connect, q, exec_sql
    from nohtus.navigation import MENU_SECTIONS
    from nohtus.dates import normalize_exp_date, display_date_only, expiry_status
    from nohtus.locations import make_location, parse_location, location_picking_key

    import nohtus.pages
    import nohtus.services
    import nohtus.ui

    if (ROOT / "nohtus" / "services" / "inventory.py").exists():
        import nohtus.services.inventory
    if (ROOT / "nohtus" / "services" / "products.py").exists():
        import nohtus.services.products

    assert APP_TITLE == "NOHTUS WMS"
    assert "노투스팜" in COMPANIES
    assert "REC" in AREA_CONFIG
    assert MENU_SECTIONS
    assert callable(connect)
    assert callable(q)
    assert callable(exec_sql)

    assert normalize_exp_date("28/3/2") == "2028-03-02"
    assert display_date_only("2028-03-02 00:00:00") == "2028-03-02"
    assert expiry_status("-") == "정상"
    assert make_location("A1", "01", "02") == "A1-01-02"
    assert parse_location("A1-01-02") == ("A1", "01", "02")
    assert location_picking_key("REC") < location_picking_key("A1-01-01")

    print("OK imports: nohtus config/db/navigation/dates/locations/pages/services/ui")


if __name__ == "__main__":
    main()
