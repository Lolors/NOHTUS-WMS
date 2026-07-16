"""출고지시의 아르케 창상피복재 제조번호 경고를 보강한다.

페이지 패키지가 로드될 때 기존 출고 장바구니 경고 함수와 Streamlit 경고 문구
렌더링을 감싸는 방식으로 동작한다. 기존 출고 로직은 변경하지 않는다.
"""

from __future__ import annotations

import base64
import html
from pathlib import Path

import streamlit as st

from nohtus.services import outbound_cart


ARKE_STANDARD_NAME = "아르케 창상피복재"
ARKE_TWO_YEAR_LOTS = {
    "AR0424002",
    "AR0425001",
    "AR0426001",
}

_ASSET_DIR = Path(__file__).resolve().parents[2] / "assets" / "outbound_warnings" / "arke"
_original_expiry_warnings = outbound_cart._cart_expiry_warnings
_original_markdown = st.markdown


def _normalise(value) -> str:
    return str(value or "").strip()


def _arke_rows(rows):
    """특정 재고 선택 중인 경고 대상 행만 반환한다."""
    if not bool(st.session_state.get("out_manual_pick")):
        return []

    result = []
    for row in rows or []:
        product = _normalise(row.get("제품명"))
        lot = _normalise(row.get("LOT")).upper()
        if product == ARKE_STANDARD_NAME and lot in ARKE_TWO_YEAR_LOTS:
            result.append(row)
    return result


def _cart_expiry_warnings_with_arke(rows):
    warnings = list(_original_expiry_warnings(rows) or [])
    existing = {
        (_normalise(row.get("제품명")), _normalise(row.get("LOT")).upper())
        for row in warnings
        if isinstance(row, dict)
    }

    for row in _arke_rows(rows):
        key = (_normalise(row.get("제품명")), _normalise(row.get("LOT")).upper())
        if key in existing:
            continue
        warnings.append(
            {
                "경고유형": "박스 유효기간 표기 확인",
                "제품명": row.get("제품명", ""),
                "LOT": row.get("LOT", ""),
                "유통기한": row.get("유통기한", ""),
                "요청수량": row.get("요청수량", ""),
            }
        )
        existing.add(key)
    return warnings


def _manufacture_year(lot: str) -> str:
    lot = _normalise(lot).upper()
    if len(lot) >= 6 and lot[4:6].isdigit():
        return f"20{lot[4:6]}"
    return "해당 연도"


def _data_uri(path: Path) -> str:
    if not path.exists():
        return ""
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def _image_card(lot: str, suffix: str, caption: str) -> str:
    uri = _data_uri(_ASSET_DIR / f"{lot}_{suffix}.jpg")
    if not uri:
        return ""
    safe_caption = html.escape(caption)
    return f"""
    <details class="arke-photo-card">
      <summary title="사진을 클릭하면 확대됩니다">
        <img src="{uri}" alt="{safe_caption}">
        <span>{safe_caption} · 클릭하여 확대</span>
      </summary>
      <div class="arke-photo-expanded">
        <img src="{uri}" alt="{safe_caption} 확대 이미지">
      </div>
    </details>
    """


def _warning_html(rows) -> str:
    sections = []
    for row in rows:
        lot = _normalise(row.get("LOT")).upper()
        expiry = _normalise(row.get("유통기한")) or "DB 유통기한 미등록"
        year = _manufacture_year(lot)
        sections.append(
            f"""
            <section class="arke-warning-section">
              <div class="arke-warning-lot">제조번호 {html.escape(lot)}</div>
              <div class="arke-warning-copy">
                해당 제품은 <strong>{html.escape(year)}년에 생산</strong>되었으며<br>
                박스에는 유효기간이 <strong>제조일로부터 2년</strong>으로 표기되어 있습니다.<br>
                실제 허가받은 유효기간은 <strong>{html.escape(expiry)}</strong> 입니다.<br>
                거래처에서 문의가 들어올 수 있으므로 확인 후 출고하십시오.
              </div>
              <div class="arke-photo-grid">
                {_image_card(lot, "top", "제조번호·제조일 표기")}
                {_image_card(lot, "side", "박스 유효기간 표기")}
              </div>
            </section>
            """
        )

    return f"""
    <style>
      .arke-warning-section{{padding:14px 0 18px;border-bottom:1px solid #e2e8f0}}
      .arke-warning-section:last-child{{border-bottom:0}}
      .arke-warning-lot{{font-size:18px;font-weight:800;color:#b45309;margin-bottom:8px}}
      .arke-warning-copy{{font-size:16px;line-height:1.75;color:#334155;margin-bottom:14px}}
      .arke-photo-grid{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}
      .arke-photo-card{{border:1px solid #d7dee8;border-radius:12px;background:#fff;overflow:hidden}}
      .arke-photo-card summary{{cursor:zoom-in;list-style:none;padding:8px}}
      .arke-photo-card summary::-webkit-details-marker{{display:none}}
      .arke-photo-card summary img{{display:block;width:100%;height:170px;object-fit:cover;border-radius:8px}}
      .arke-photo-card summary span{{display:block;text-align:center;font-size:13px;font-weight:700;color:#475569;padding:7px 3px 2px}}
      .arke-photo-expanded{{padding:8px 10px 12px;background:#f8fafc}}
      .arke-photo-expanded img{{display:block;width:100%;height:auto;max-height:70vh;object-fit:contain;border-radius:8px;cursor:zoom-out}}
      @media (max-width:700px){{.arke-photo-grid{{grid-template-columns:1fr}}.arke-photo-card summary img{{height:150px}}}}
    </style>
    {''.join(sections)}
    """


def _markdown_with_arke_warning(body, *args, **kwargs):
    text = str(body or "")
    pending_rows = st.session_state.get("pending_outbound_add_rows", [])
    arke_rows = _arke_rows(pending_rows)
    is_existing_expiry_prompt = (
        "유통기한이 만료되었거나 1개월 미만 남은 품목입니다" in text
        and "장바구니에 담으시겠습니까" in text
    )
    if arke_rows and is_existing_expiry_prompt:
        kwargs["unsafe_allow_html"] = True
        return _original_markdown(_warning_html(arke_rows), *args, **kwargs)
    return _original_markdown(body, *args, **kwargs)


# outbound.py가 함수를 import하기 전에 교체되도록 pages 패키지 초기화 시 실행한다.
outbound_cart._cart_expiry_warnings = _cart_expiry_warnings_with_arke
st.markdown = _markdown_with_arke_warning
