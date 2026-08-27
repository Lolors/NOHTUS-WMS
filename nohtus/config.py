from pathlib import Path

APP_TITLE = "NOHTUS WMS"
VERSION = "v4.9 RC3.3 UI Stable"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "nohtus.db"

COMPANIES = ["노투스팜", "노투스", "NOH", "비자료"]
INBOUND_COMPANIES = COMPANIES + ["등록대기"]
SPECIAL_LOCATIONS = ["오른쪽 창고", "사무실(4층)", "지엠메딕"]

AREA_CONFIG = {
    # A1/B1/C1/D1/E1 라인 수는 로케이션맵 도면(data/location_map_layout.json)의
    # 실제 랙 셀 개수와 맞춘다. (A1: 15칸, B1: 12칸, C1: 6칸, D1: 12칸, E1: 9칸)
    "A1": {"lines": [f"{i:02d}" for i in range(1, 16)], "levels": ["01", "02", "03"]},
    "B1": {"lines": [f"{i:02d}" for i in range(1, 13)], "levels": ["01", "02", "03"]},
    "C1": {"lines": ["01", "02", "03", "04", "05", "06"], "levels": ["01", "02", "03"]},
    "D1": {"lines": [f"{i:02d}" for i in range(1, 13)], "levels": ["01", "02", "03"]},
    "E1": {"lines": [f"{i:02d}" for i in range(1, 10)], "levels": ["01", "02", "03"]},
    "F1": {"lines": ["01", "02", "03"], "levels": ["01", "02", "03"]},
    "G1": {"lines": ["01", "02", "03"], "levels": ["01", "02", "03"]},
    "T1": {"lines": [], "levels": []},
    "T2": {"lines": [], "levels": []},
    "T3": {"lines": [], "levels": []},
    "T4": {"lines": [], "levels": []},
    "T5": {"lines": [], "levels": []},
    "박스(기타)": {"lines": [], "levels": []},
    "X1": {"lines": ["01", "02", "03"], "levels": ["01", "02", "03", "04"]},
    "X2": {"lines": [], "levels": []},
    "REC": {"lines": [], "levels": []},
    "Q": {"lines": ["01", "02", "03"], "levels": ["01", "02", "03"]},
    "P": {"lines": [], "levels": []},
    "R1": {"lines": [], "levels": []},
    "R2": {"lines": [], "levels": []},
    "N": {"lines": SPECIAL_LOCATIONS, "levels": []},
    "홍보물랙": {"lines": [], "levels": []},
    "옷장1": {"lines": [], "levels": []},
    "옷장2": {"lines": [], "levels": []},
    "옷장3": {"lines": [], "levels": []},
    "옷장4": {"lines": [], "levels": []},
    "옷장5": {"lines": [], "levels": []},
}

AREA_COLOR = {
    "A1": "yellow", "B1": "yellow", "C1": "yellow",
    "D1": "blue",
    "E1": "pink", "Q": "pink",
    "F1": "bidata", "G1": "gray", "X1": "gray", "X2": "gray", "N": "gray",
    "REC": "white", "P": "white", "R1": "white", "R2": "white", "T1": "white", "T2": "white", "홍보물랙": "white",
}
