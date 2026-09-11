import os
from pathlib import Path

APP_TITLE = "NOHTUS WMS"
VERSION = "v4.9 RC3.3 UI Stable"

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# NOHTUS_DB_PATH가 설정되어 있으면 그걸 우선 쓴다. 이 저장소를 git worktree로
# 여러 개 체크아웃해두고 각각에서 서버를 띄우는 경우(예: 모바일 API를
# mobile-inventory-ui-review 브랜치 워크트리에서 실행), data/nohtus.db가
# 워크트리마다 서로 다른(gitignore된) 파일이라 로그인 계정이 안 맞는 문제가
# 생길 수 있다 — 그럴 때 실제 운영 DB 경로를 이 환경변수로 지정해서 같은
# DB를 바라보게 한다.
_db_path_override = str(os.environ.get("NOHTUS_DB_PATH", "") or "").strip()
DB_PATH = Path(_db_path_override) if _db_path_override else PROJECT_ROOT / "data" / "nohtus.db"

COMPANIES = ["노투스팜", "노투스", "NOH", "비자료"]
INBOUND_COMPANIES = COMPANIES + ["등록대기"]
SPECIAL_LOCATIONS = ["오른쪽 창고", "사무실(4층)", "지엠메딕", "거래처 창고"]

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
    "다용도랙": {"lines": [], "levels": []},
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
    "REC": "white", "P": "white", "R1": "white", "R2": "white", "T1": "white", "T2": "white",
}
