from __future__ import annotations

import streamlit as st

from nohtus.services.discrepancy_comic import delete_image, image_path, save_image

PANEL_TITLE = "전산과 실물 재고가 달라진 3가지 사건 만화로 보기"


@st.dialog(PANEL_TITLE, width="large")
def _comic_dialog() -> None:
    path = image_path()
    if path is None:
        st.info("등록된 이미지가 없습니다. '이미지 등록/변경'에서 이미지를 먼저 등록하세요.")
    else:
        st.image(str(path), use_container_width=True)


@st.dialog("이미지 등록/변경", width="small")
def _manage_image_dialog() -> None:
    st.caption("JPG, PNG, WEBP 형식, 최대 8MB까지 등록할 수 있습니다.")
    path = image_path()
    if path is not None:
        st.image(str(path), width=200)
    else:
        st.info("등록된 이미지가 없습니다.")
    uploaded = st.file_uploader(
        "이미지 선택", type=["jpg", "jpeg", "png", "webp"], key="discrepancy_comic_upload"
    )
    save_col, delete_col = st.columns(2)
    if save_col.button("저장", key="discrepancy_comic_save", disabled=uploaded is None, use_container_width=True):
        try:
            save_image(uploaded)
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.success("이미지를 저장했습니다.")
            st.rerun()
    if delete_col.button("삭제", key="discrepancy_comic_delete", disabled=path is None, use_container_width=True):
        delete_image()
        st.success("이미지를 삭제했습니다.")
        st.rerun()


def render_discrepancy_comic_panel():
    """자사제품 조회 화면 우측 컬럼에 들어가는 만화 보기 패널."""
    st.markdown(f"##### {PANEL_TITLE}")

    with st.container(horizontal=True, horizontal_alignment="center"):
        if st.button("만화 보기", type="primary"):
            _comic_dialog()
        if st.button("이미지 등록/변경"):
            _manage_image_dialog()
