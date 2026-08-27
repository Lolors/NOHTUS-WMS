"""전산과 실물 재고가 달라진 3가지 사건을 보여주는 만화 이미지 저장소."""
from __future__ import annotations

from pathlib import Path

IMAGE_DIR = Path(__file__).resolve().parents[2] / "data" / "discrepancy_comic"
ALLOWED_IMAGE_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
MAX_IMAGE_BYTES = 8 * 1024 * 1024


def image_path() -> Path | None:
    if not IMAGE_DIR.is_dir():
        return None
    for ext in ALLOWED_IMAGE_TYPES.values():
        candidate = IMAGE_DIR / f"comic{ext}"
        if candidate.is_file():
            return candidate
    return None


def save_image(uploaded_file) -> Path:
    if uploaded_file is None:
        raise ValueError("업로드할 이미지를 선택하세요.")
    mime = str(getattr(uploaded_file, "type", "") or "").lower()
    if mime not in ALLOWED_IMAGE_TYPES:
        raise ValueError("JPG, PNG, WEBP 형식만 업로드할 수 있습니다.")
    data = uploaded_file.getvalue()
    if not data:
        raise ValueError("빈 파일은 업로드할 수 없습니다.")
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError("이미지는 8MB 이하만 등록할 수 있습니다.")

    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    existing = image_path()
    if existing is not None:
        existing.unlink(missing_ok=True)

    target = IMAGE_DIR / f"comic{ALLOWED_IMAGE_TYPES[mime]}"
    target.write_bytes(data)
    return target


def delete_image() -> None:
    existing = image_path()
    if existing is not None:
        existing.unlink(missing_ok=True)
