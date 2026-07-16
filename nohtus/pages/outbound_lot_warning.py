"""아르케 창상피복재의 박스 유효기간 표기를 출고 저장 직전에 확인한다."""

from __future__ import annotations

import base64
import html
from pathlib import Path

import streamlit as st

from nohtus.services.outbound_cart import get_cart


ARKE_STANDARD_NAME = "아르케 창상피복재"
ARKE_TWO_YEAR_LOTS = {
    "AR0424002",
    "AR0425001",
    "AR0426001",
}

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_original_button = st.button

_PENDING_ROWS_KEY = "_pending_arke_outbound_save_rows"
_CONFIRMED_KEY = "_arke_outbound_save_confirmed_once"


def _normalise(value) -> str:
    return str(value or "").strip()


def _warning_rows(rows):
    """장바구니에서 경고 대상 제조번호를 중복 없이 찾는다."""
    found = []
    seen = set()
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        product = _normalise(row.get("제품명"))
        lot = _normalise(row.get("LOT")).upper()
        if product != ARKE_STANDARD_NAME or lot not in ARKE_TWO_YEAR_LOTS:
            continue
        key = (product, lot, _normalise(row.get("유통기한")))
        if key in seen:
            continue
        seen.add(key)
        found.append(dict(row))
    return found


def _manufacture_year(lot: str) -> str:
    lot = _normalise(lot).upper()
    if len(lot) >= 6 and lot[4:6].isdigit():
        return f"20{lot[4:6]}"
    return "해당 연도"


def _asset_candidates(lot: str, suffix: str):
    """기존 평면 구조와 제조번호별 폴더 구조를 모두 지원한다."""
    return [
        _PROJECT_ROOT / "assets" / "shipment_warnings" / "arke_wound_dressing" / lot / f"{suffix}.jpg",
        _PROJECT_ROOT / "assets" / "shipment_warnings" / "arke_wound_dressing" / f"{lot}_{suffix}.jpg",
        _PROJECT_ROOT / "assets" / "outbound_warnings" / "arke" / f"{lot}_{suffix}.jpg",
        _PROJECT_ROOT / "assets" / "outbound_warnings" / "arke" / lot / f"{suffix}.jpg",
    ]


def _find_asset(lot: str, suffix: str) -> Path | None:
    for path in _asset_candidates(lot, suffix):
        if path.exists():
            return path
    return None


def _data_uri(path: Path | None) -> str:
    if path is None:
        return ""
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def _image_card(lot: str, suffix: str, caption: str) -> str:
    uri = _data_uri(_find_asset(lot, suffix))
    safe_caption = html.escape(caption)
    if not uri:
        return f"""
        <div class="arke-photo-missing">
          <strong>{safe_caption}</strong><br>
          이미지 파일을 찾을 수 없습니다.
        </div>
        """
    return f"""
    <details class="arke-photo-card">
      <summary title="사진을 클릭하면 확대됩니다">
        <img src="{uri}" alt="{safe_caption}">
        <span>{safe_caption} · 클릭하여 확대</span>
      </summary>
      <div class="arke-photo-expanded">
        <img src="{uri}" alt="{safe_caption} 확대 이미지">
        <div>사진을 다시 클릭하면 접힙니다.</div>
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
                {_image_card(lot, "top", "박스 상단")}
                {_image_card(lot, "side", "박스 측면")}
              </div>
            </section>
            """
        )

    return f"""
    <style>
      .arke-warning-section{{padding:4px 0 16px;border-bottom:1px solid #e2e8f0}}
      .arke-warning-section:last-child{{border-bottom:0}}
      .arke-warning-lot{{font-size:18px;font-weight:800;color:#b45309;margin-bottom:8px}}
      .arke-warning-copy{{font-size:16px;line-height:1.75;color:#334155;margin-bottom:14px}}
      .arke-photo-grid{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}
      .arke-photo-card{{border:1px solid #d7dee8;border-radius:12px;background:#fff;overflow:hidden}}
      .arke-photo-card summary{{cursor:zoom-in;list-style:none;padding:8px}}
      .arke-photo-card summary::-webkit-details-marker{{display:none}}
      .arke-photo-card summary img{{display:block;width:100%;height:180px;object-fit:cover;border-radius:8px}}
      .arke-photo-card summary span{{display:block;text-align:center;font-size:13px;font-weight:700;color:#475569;padding:7px 3px 2px}}
      .arke-photo-expanded{{padding:10px;background:#f8fafc;text-align:center}}
      .arke-photo-expanded img{{display:block;width:100%;height:auto;max-height:72vh;object-fit:contain;border-radius:8px;cursor:zoom-out}}
      .arke-photo-expanded div{{font-size:12px;color:#64748b;margin-top:7px}}
      .arke-photo-missing{{display:flex;min-height:180px;align-items:center;justify-content:center;text-align:center;border:1px dashed #cbd5e1;border-radius:12px;color:#64748b;background:#f8fafc}}
      @media (max-width:700px){{.arke-photo-grid{{grid-template-columns:1fr}}.arke-photo-card summary img{{height:160px}}}}
    </style>
    {''.join(sections)}
    """


def _render_save_dialog(rows):
    dialog_api = getattr(st, "dialog", None) or getattr(st, "experimental_dialog", None)
    if dialog_api:
        @dialog_api("⚠ 출고 전 확인", width="large")
        def _dialog():
            st.markdown(_warning_html(rows), unsafe_allow_html=True)
            cancel_col, confirm_col = st.columns(2)
            with cancel_col:
                if _original_button("취소", use_container_width=True, key="arke_save_cancel"):
                    st.session_state.pop(_PENDING_ROWS_KEY, None)
                    st.rerun()
            with confirm_col:
                if _original_button("확인 후 출고", type="primary", use_container_width=True, key="arke_save_confirm"):
                    st.session_state.pop(_PENDING_ROWS_KEY, None)
                    st.session_state[_CONFIRMED_KEY] = True
                    st.rerun()
        _dialog()
        return

    st.warning("출고 전 아르케 창상피복재의 박스 유효기간 표기를 확인하십시오.")
    st.markdown(_warning_html(rows), unsafe_allow_html=True)
    cancel_col, confirm_col = st.columns(2)
    with cancel_col:
        if _original_button("취소", use_container_width=True, key="arke_save_cancel_inline"):
            st.session_state.pop(_PENDING_ROWS_KEY, None)
            st.rerun()
    with confirm_col:
        if _original_button("확인 후 출고", type="primary", use_container_width=True, key="arke_save_confirm_inline"):
            st.session_state.pop(_PENDING_ROWS_KEY, None)
            st.session_state[_CONFIRMED_KEY] = True
            st.rerun()


def _button_with_arke_save_warning(label, *args, **kwargs):
    """출고지시 저장 버튼을 누른 경우에만 장바구니 전체를 검사한다."""
    if str(label) != "지시완료 저장":
        return _original_button(label, *args, **kwargs)

    if bool(st.session_state.pop(_CONFIRMED_KEY, False)):
        return True

    clicked = _original_button(label, *args, **kwargs)
    if clicked:
        rows = _warning_rows(get_cart())
        if rows:
            st.session_state[_PENDING_ROWS_KEY] = rows
            st.rerun()
        return True

    pending_rows = st.session_state.get(_PENDING_ROWS_KEY) or []
    if pending_rows:
        _render_save_dialog(pending_rows)
    return False


# pages 패키지가 초기화될 때 한 번 등록되며, 다른 버튼에는 영향을 주지 않는다.
if st.button is not _button_with_arke_save_warning:
    st.button = _button_with_arke_save_warning
