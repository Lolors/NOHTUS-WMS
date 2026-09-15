"""제품 이미지 경로 조회 + 썸네일 생성/조회 (streamlit 미의존).

모바일 API처럼 Streamlit 없이 도는 경로에서도 썸네일을 안전하게 만들 수 있도록,
데스크톱 로케이션맵 페이지(nohtus/pages/location_map.py)가 쓰던 썸네일 로직을
여기로 옮겨 공용으로 쓴다. 원본을 그대로 base64로 보내면(특히 모바일 검색
결과처럼 여러 장을 한 번에 응답에 담을 때) 응답이 몇 MB씩 커져 느려지므로,
항상 리사이즈된 썸네일만 쓰고 원본으로 폴백하지 않는다.
"""

from __future__ import annotations

from pathlib import Path

from nohtus.db import q

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_THUMB_DIR = _PROJECT_ROOT / "data" / "product_images" / "thumbs"
_THUMB_SIZE = (500, 500)
_THUMB_QUALITY = 78


def get_product_image_path(product_name):
    df = q("SELECT image_path FROM products WHERE standard_name=? AND COALESCE(image_path, '') <> '' LIMIT 1", (product_name,))
    if df.empty:
        return ""
    value = str(df.iloc[0].get("image_path") or "").strip()
    if not value:
        return ""
    path = Path(value)
    if not path.is_absolute():
        path = _PROJECT_ROOT / path
    return str(path) if path.is_file() else ""


def thumbnail_path_for(original_path) -> Path:
    original = Path(str(original_path or ""))
    return _THUMB_DIR / f"{original.stem}.jpg"


def create_thumbnail(original_path) -> str:
    """원본 이미지를 리사이즈해 썸네일로 저장하고 그 경로를 반환한다. 실패 시 빈 문자열."""
    original = Path(str(original_path or ""))
    if not original.is_file():
        return ""
    target = thumbnail_path_for(original)
    try:
        from PIL import Image, ImageOps

        _THUMB_DIR.mkdir(parents=True, exist_ok=True)
        with Image.open(original) as image:
            image = ImageOps.exif_transpose(image)
            if image.mode not in ("RGB", "L"):
                background = Image.new("RGB", image.size, "white")
                alpha = image.getchannel("A") if "A" in image.getbands() else None
                background.paste(image.convert("RGB"), mask=alpha)
                image = background
            else:
                image = image.convert("RGB")
            image = ImageOps.fit(image, _THUMB_SIZE, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
            image.save(target, format="JPEG", quality=_THUMB_QUALITY, optimize=True)
        return str(target)
    except Exception:
        return ""


def ensure_thumbnail(original_path) -> str:
    """썸네일이 이미 최신 상태면 그대로 쓰고, 없거나 오래됐으면 새로 만든다."""
    original = Path(str(original_path or ""))
    if not original.is_file():
        return ""
    target = thumbnail_path_for(original)
    try:
        if target.is_file():
            from PIL import Image
            with Image.open(target) as thumb:
                correct_size = tuple(thumb.size) == _THUMB_SIZE
            if correct_size and target.stat().st_mtime >= original.stat().st_mtime:
                return str(target)
    except Exception:
        pass
    return create_thumbnail(original)
