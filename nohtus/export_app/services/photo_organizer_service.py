from __future__ import annotations

from collections import Counter
from pathlib import Path

from nohtus.export_app import db
from nohtus.export_app.services import folder_service

PHOTO_TAGS = ('내부', '외부')


def default_save_root() -> Path:
    """Return the local user's Desktop, falling back to the home directory."""
    desktop = Path.home() / 'Desktop'
    return desktop if desktop.exists() else Path.home()


def list_ctn_numbers(case_id: int) -> list[int]:
    return [
        int(row['box_no'])
        for row in db.rows(
            'SELECT box_no FROM boxes WHERE case_id=? ORDER BY box_no',
            (case_id,),
        )
    ]


def build_photo_names(area_name: str, files: list, tags: list[str]) -> list[str]:
    """Build stable names while preserving each uploaded file extension."""
    if len(files) != len(tags):
        raise ValueError('사진 수와 태그 수가 일치하지 않습니다.')
    if len(files) <= 1:
        return [f'{area_name}{Path(files[0].name).suffix.lower()}'] if files else []

    invalid_tags = [tag for tag in tags if tag not in PHOTO_TAGS]
    if invalid_tags:
        raise ValueError('사진 태그는 내부 또는 외부만 사용할 수 있습니다.')

    totals = Counter(tags)
    seen: Counter[str] = Counter()
    names: list[str] = []
    for uploaded, tag in zip(files, tags):
        seen[tag] += 1
        suffix = f'_{seen[tag] - 1}' if totals[tag] > 1 and seen[tag] > 1 else ''
        names.append(f'{area_name}_{tag}{suffix}{Path(uploaded.name).suffix.lower()}')
    return names


def organize_photos(case_id: int, save_root: Path, uploads: dict[str, list], tags: dict[str, list[str]]) -> Path:
    case = db.row('SELECT * FROM export_cases WHERE id=?', (case_id,))
    if not case:
        raise ValueError(f'수출 건을 찾을 수 없습니다: {case_id}')
    if not any(uploads.values()):
        raise ValueError('정리할 사진을 한 장 이상 넣어주세요.')

    root = Path(save_root).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    destination = folder_service.unique_folder_path(root, folder_service.case_folder_name(case))
    destination.mkdir(parents=True)

    try:
        for area_name, files in uploads.items():
            file_list = list(files or [])
            file_tags = list(tags.get(area_name, []))
            for uploaded, output_name in zip(file_list, build_photo_names(area_name, file_list, file_tags)):
                (destination / output_name).write_bytes(uploaded.getvalue())
    except Exception:
        for item in destination.iterdir():
            item.unlink()
        destination.rmdir()
        raise
    return destination
