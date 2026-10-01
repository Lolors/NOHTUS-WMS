"""제품 사진 모달에서 사용하는 클립보드 및 파일 입력."""
import base64
import binascii
from io import BytesIO

import streamlit as st
import streamlit.components.v2 as components


@st.cache_resource
def _get_clipboard_photo_input():
    return components.component(
        "expiry_clipboard_photo",
        html='<div class="paste-box" tabindex="0" role="textbox" aria-label="사진 붙여넣기">여기를 클릭한 뒤 Ctrl+V로 사진을 붙여넣으세요.</div><p class="paste-status" role="status"></p>',
        css="""
        .paste-box { padding: 20px; border: 2px dashed #94a3b8; border-radius: 8px; cursor: text; text-align: center; }
        .paste-box:focus { outline: 2px solid #2563eb; border-color: #2563eb; }
        .paste-status { font-size: 13px; margin: 6px 0; }
        """,
        js="""
        export default function(component) {
            const { parentElement, setStateValue } = component;
            const box = parentElement.querySelector('.paste-box');
            const status = parentElement.querySelector('.paste-status');
            let reader;
            let sequence = 0;
            const onPaste = (event) => {
                event.preventDefault();
                const current = ++sequence;
                if (reader && reader.readyState === 1) reader.abort();
                const item = Array.from(event.clipboardData?.items || []).find(item => item.type.startsWith('image/'));
                const file = item?.getAsFile();
                if (!file || !['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) {
                    status.textContent = '클립보드에 JPG, PNG 또는 WEBP 사진이 없습니다.';
                    setStateValue('image', null);
                    return;
                }
                if (file.size > 8 * 1024 * 1024) {
                    status.textContent = '사진은 8MB 이하만 등록할 수 있습니다.';
                    setStateValue('image', null);
                    return;
                }
                status.textContent = '사진을 불러오는 중입니다…';
                reader = new FileReader();
                reader.onload = () => {
                    if (current !== sequence) return;
                    status.textContent = '사진이 붙여넣어졌습니다. 미리보기 확인 후 사진 저장을 누르세요.';
                    setStateValue('image', {type: file.type, data: reader.result});
                };
                reader.onerror = () => {
                    status.textContent = '사진을 읽지 못했습니다. 다시 붙여넣어 주세요.';
                    setStateValue('image', null);
                };
                reader.readAsDataURL(file);
            };
            box.addEventListener('paste', onPaste);
            return () => {
                ++sequence;
                box.removeEventListener('paste', onPaste);
                if (reader && reader.readyState === 1) reader.abort();
            };
        }
        """,
    )


def _clipboard_uploaded_file(payload):
    if not payload:
        return None
    from PIL import Image, UnidentifiedImageError

    mime = payload.get("type") if isinstance(payload, dict) else None
    formats = {"image/png": "PNG", "image/jpeg": "JPEG", "image/webp": "WEBP"}
    if mime not in formats:
        raise ValueError("JPG, PNG, WEBP 사진만 붙여넣을 수 있습니다.")
    data_url = payload.get("data", "")
    prefix = f"data:{mime};base64,"
    if not isinstance(data_url, str) or not data_url.startswith(prefix):
        raise ValueError("붙여넣은 사진을 읽을 수 없습니다.")
    if len(data_url) > 12 * 1024 * 1024:
        raise ValueError("사진은 8MB 이하만 등록할 수 있습니다.")
    try:
        data = base64.b64decode(data_url[len(prefix):], validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("붙여넣은 사진을 읽을 수 없습니다.") from exc
    if len(data) > 8 * 1024 * 1024:
        raise ValueError("사진은 8MB 이하만 등록할 수 있습니다.")
    try:
        with Image.open(BytesIO(data)) as image:
            if image.format != formats[mime]:
                raise ValueError("사진 형식이 올바르지 않습니다.")
            image.verify()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("올바른 이미지 파일을 붙여넣어 주세요.") from exc
    uploaded = BytesIO(data)
    uploaded.type = mime
    uploaded.name = "clipboard." + formats[mime].lower()
    return uploaded


def render_photo_input(*, key_prefix: str, upload_key: str):
    source = st.radio("사진 입력 방법", ["클립보드 붙여넣기", "파일 선택"],
                      horizontal=True, key=f"{key_prefix}_source")
    uploaded = None
    if source == "클립보드 붙여넣기":
        pasted = _get_clipboard_photo_input()(
            key=f"{key_prefix}_clipboard", on_image_change=lambda: None,
        )
        try:
            uploaded = _clipboard_uploaded_file(pasted.image)
        except ValueError as exc:
            st.error(str(exc))
    else:
        uploaded = st.file_uploader(
            "변경할 사진 선택", type=["jpg", "jpeg", "png", "webp"], key=upload_key,
        )
    st.caption("JPG, PNG, WEBP · 최대 8MB")
    if uploaded is not None:
        st.image(uploaded, caption="변경할 사진 미리보기", width=240)
    return uploaded
