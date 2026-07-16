"""Page modules for NOHTUS WMS.

Legacy Streamlit page functions will be moved here one by one.
"""

# 출고 페이지가 로드되기 전에 제조번호별 출고 경고를 등록한다.
from nohtus.pages import outbound_lot_warning as _outbound_lot_warning  # noqa: F401,E402
