from pathlib import Path

APP_TITLE = "NOHTUS WMS"
VERSION = "v3.10.2 Business Patch"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "nohtus.db"

COMPANIES = ["노투스팜", "노투스", "NOH", "비자료"]
INBOUND_COMPANIES = COMPANIES + ["등록대기"]
SPECIAL_LOCATIONS = ["홍보물랙", "회색 카트", "오른쪽 창고", "사무실(4층)", "지엠메딕"]

AREA_CONFIG = {
    "A1": {"lines": ["01", "02", "03", "04", "05", "06"], "levels": ["01", "02", "03"]},
    "A2": {"lines": ["01", "02", "03", "04", "05", "06"], "levels": ["01", "02", "03"]},
    "B1": {"lines": ["01", "02", "03", "04", "05", "06"], "levels": ["01", "02", "03"]},
    "B2": {"lines": ["01", "02", "03", "04", "05", "06"], "levels": ["01", "02", "03"]},
    "C1": {"lines": ["01", "02", "03", "04", "05", "06"], "levels": ["01", "02", "03"]},
    "C2": {"lines": ["01", "02", "03", "04", "05", "06"], "levels": ["01", "02", "03"]},
    "D1": {"lines": ["01", "02", "03", "04", "05", "06"], "levels": ["01", "02", "03"]},
    "E1": {"lines": ["01", "02", "03", "04", "05", "06"], "levels": ["01", "02", "03"]},
    "F1": {"lines": ["01", "02", "03"], "levels": ["01", "02", "03"]},
    "G1": {"lines": ["01", "02", "03"], "levels": ["01", "02", "03"]},
    "G2": {"lines": [], "levels": []},
    "T1": {"lines": [], "levels": []},
    "T2": {"lines": [], "levels": []},
    "X1": {"lines": ["01", "02", "03"], "levels": ["01", "02", "03", "04"]},
    "X2": {"lines": [], "levels": []},
    "REC": {"lines": [], "levels": []},
    "Q": {"lines": ["Q1", "Q2"], "levels": []},
    "P": {"lines": [], "levels": []},
    "R1": {"lines": [], "levels": []},
    "R2": {"lines": [], "levels": []},
    "N": {"lines": SPECIAL_LOCATIONS, "levels": []},
}

AREA_COLOR = {
    "A1": "yellow", "A2": "yellow", "B1": "yellow", "B2": "yellow", "C1": "yellow",
    "C2": "blue", "D1": "blue",
    "E1": "pink", "Q": "pink",
    "F1": "bidata", "G1": "gray", "G2": "gray", "X1": "gray", "X2": "gray", "N": "gray",
    "REC": "white", "P": "white", "R1": "white", "R2": "white", "T1": "white", "T2": "white",
}
