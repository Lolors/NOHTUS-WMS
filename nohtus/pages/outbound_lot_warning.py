"""아르케 창상피복재의 박스 유효기간 표기를 출고 저장 직전에 확인한다."""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

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
_IMAGE_VIEWER_KEY = "_arke_outbound_original_image"


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
    """평면 구조와 제조번호별 폴더 구조를 모두 지원한다."""
    return [
        _PROJECT_ROOT / "assets" / "shipment_warnings" / "arke_wound_dressing" / lot / f"{suffix}.jpg",
        _PROJECT_ROOT / "assets" / "shipment_warnings" / "arke_wound_dressing" / lot / f"{suffix}.jpeg",
        _PROJECT_ROOT / "assets" / "shipment_warnings" / "arke_wound_dressing" / lot / f"{suffix}.png",
        _PROJECT_ROOT / "assets" / "shipment_warnings" / "arke_wound_dressing" / f"{lot}_{suffix}.jpg",
        _PROJECT_ROOT / "assets" / "shipment_warnings" / "arke_wound_dressing" / f"{lot}_{suffix}.jpeg",
        _PROJECT_ROOT / "assets" / "shipment_warnings" / "arke_wound_dressing" / f"{lot}_{suffix}.png",
        _PROJECT_ROOT / "assets" / "shipment_warnings" / lot / f"{suffix}.jpg",
        _PROJECT_ROOT / "assets" / "shipment_warnings" / f"{lot}_{suffix}.jpg",
        _PROJECT_ROOT / "assets" / "outbound_warnings" / "arke" / f"{lot}_{suffix}.jpg",
        _PROJECT_ROOT / "assets" / "outbound_warnings" / "arke" / lot / f"{suffix}.jpg",
        _PROJECT_ROOT / "assets" / f"{lot}_{suffix}.jpg",
    ]


def _find_asset(lot: str, suffix: str) -> Path | None:
    for path in _asset_candidates(lot, suffix):
        if path.is_file():
            return path

    assets = _PROJECT_ROOT / "assets"
    if assets.exists():
        wanted_flat = {
            f"{lot}_{suffix}.jpg".lower(),
            f"{lot}_{suffix}.jpeg".lower(),
            f"{lot}_{suffix}.png".lower(),
        }
        for path in assets.rglob("*"):
            if path.is_file() and path.name.lower() in wanted_flat:
                return path

        wanted_names = {f"{suffix}.jpg", f"{suffix}.jpeg", f"{suffix}.png"}
        for lot_dir in assets.rglob("*"):
            if not lot_dir.is_dir() or lot_dir.name.upper() != lot:
                continue
            for name in wanted_names:
                candidate = lot_dir / name
                if candidate.is_file():
                    return candidate
    return None


def _open_original_image(path: Path, lot: str, caption: str):
    st.session_state[_IMAGE_VIEWER_KEY] = {
        "path": str(path),
        "lot": lot,
        "caption": caption,
    }
    st.rerun()


def _render_original_image(path: Path):
    """브라우저 축소 없이 원본 픽셀 크기로 표시하고 넘치는 부분은 스크롤한다."""
    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    components.html(
        f"""
        <div style="width:100%;height:680px;overflow:auto;background:#f8fafc;border:1px solid #d7dee8;border-radius:10px;padding:12px;box-sizing:border-box;">
          <img src="data:{mime};base64,{encoded}" style="display:block;width:auto;max-width:none;height:auto;max-height:none;" alt="원본 이미지">
        </div>
        """,
        height=710,
        scrolling=False,
    )


def _render_image_viewer_dialog():
    viewer = st.session_state.get(_IMAGE_VIEWER_KEY) or {}
    path = Path(str(viewer.get("path") or ""))
    lot = _normalise(viewer.get("lot"))
    caption = _normalise(viewer.get("caption")) or "사진"

    dialog_api = getattr(st, "dialog", None) or getattr(st, "experimental_dialog", None)
    if not dialog_api:
        st.subheader(f"{lot} · {caption} 원본")
        if path.is_file():
            _render_original_image(path)
        else:
            st.error("원본 이미지 파일을 찾을 수 없습니다.")
        if _original_button("원본 보기 닫기", use_container_width=True, key="arke_original_close_inline"):
            st.session_state.pop(_IMAGE_VIEWER_KEY, None)
            st.rerun()
        return

    try:
        decorator = dialog_api(f"🔍 {lot} · {caption} 원본", width="large")
    except TypeError:
        decorator = dialog_api(f"🔍 {lot} · {caption} 원본")

    @decorator
    def _viewer_dialog():
        st.caption("사진은 원본 픽셀 크기로 표시됩니다. 큰 사진은 안쪽 영역을 스크롤해서 확인하세요.")
        if path.is_file():
            _render_original_image(path)
        else:
            st.error("원본 이미지 파일을 찾을 수 없습니다.")
        if _original_button("닫기", use_container_width=True, key="arke_original_close"):
            st.session_state.pop(_IMAGE_VIEWER_KEY, None)
            st.rerun()

    _viewer_dialog()


def _render_warning_row(row, index: int):
    """Streamlit 기본 요소로 경고와 사진을 렌더링한다."""
    lot = _normalise(row.get("LOT")).upper()
    expiry = _normalise(row.get("유통기한")) or "DB 유통기한 미등록"
    year = _manufacture_year(lot)

    st.markdown(f"### 제조번호 {lot}")
    st.write(f"해당 제품은 {year}년에 생산되었으며")
    st.write("박스에는 유효기간이 제조일로부터 2년으로 표기되어 있습니다.")
    st.write(f"실제 허가받은 유효기간은 {expiry} 입니다.")
    st.write("거래처에서 문의가 들어올 수 있으므로 확인 후 출고하십시오.")

    top_path = _find_asset(lot, "top")
    side_path = _find_asset(lot, "side")
    left, right = st.columns(2)

    with left:
        st.caption("박스 상단")
        if top_path:
            st.image(str(top_path), use_container_width=True)
            if _original_button(
                "🔍 원본 크기 보기",
                use_container_width=True,
                key=f"arke_original_top_{lot}_{index}",
            ):
                _open_original_image(top_path, lot, "박스 상단")
        else:
            st.warning("박스 상단 이미지 파일을 찾을 수 없습니다.")

    with right:
        st.caption("박스 측면")
        if side_path:
            st.image(str(side_path), use_container_width=True)
            if _original_button(
                "🔍 원본 크기 보기",
                use_container_width=True,
                key=f"arke_original_side_{lot}_{index}",
            ):
                _open_original_image(side_path, lot, "박스 측면")
        else:
            st.warning("박스 측면 이미지 파일을 찾을 수 없습니다.")

    if index >= 0:
        st.divider()


def _render_save_dialog(rows):
    if st.session_state.get(_IMAGE_VIEWER_KEY):
        _render_image_viewer_dialog()
        return

    dialog_api = getattr(st, "dialog", None) or getattr(st, "experimental_dialog", None)
    if dialog_api:
        @dialog_api("⚠ 출고 전 확인")
        def _dialog():
            for index, row in enumerate(rows):
                _render_warning_row(row, index)
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
    for index, row in enumerate(rows):
        _render_warning_row(row, index)
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
