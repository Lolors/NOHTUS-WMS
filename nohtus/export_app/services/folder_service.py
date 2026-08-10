from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from pathlib import Path

from nohtus.export_app import db
from nohtus.export_app.services import usb_storage_service
from nohtus.export_app.utils.dates import now_text, parse_date
from nohtus.export_app.utils.formatters import sanitize_folder_part

CASE_MARKER_NAME = '.export_case.json'
BACKUP_FOLDER_NAME = '.backup'
CATEGORY_FOLDERS = {
    '출고사진': '01 출고제품사진',
    'CI': '02 CI',
    'Shipping Mark': '03 Shipping Mark',
    '기타': '04 기타',
}
LEGACY_CATEGORY_FOLDERS = {
    '출고사진': '01_출고제품사진',
    'CI': '02_CI',
    'Shipping Mark': '03_Shipping Mark',
    '기타': '04_기타',
}

_WINDOWS_HIDDEN_ATTRIBUTE = 0x02
_WINDOWS_READONLY_ATTRIBUTE = 0x01
_WINDOWS_INVALID_ATTRIBUTES = 0xFFFFFFFF


def _get_windows_attributes(path: Path) -> int | None:
    if os.name != 'nt' or not path.exists():
        return None
    try:
        import ctypes

        attributes = ctypes.windll.kernel32.GetFileAttributesW(str(path))
        if attributes == _WINDOWS_INVALID_ATTRIBUTES:
            return None
        return int(attributes)
    except (AttributeError, OSError):
        return None


def _set_windows_attributes(path: Path, attributes: int) -> bool:
    if os.name != 'nt' or not path.exists():
        return False
    try:
        import ctypes

        return bool(ctypes.windll.kernel32.SetFileAttributesW(str(path), attributes))
    except (AttributeError, OSError):
        return False


def set_hidden(path: Path) -> bool:
    """Apply the Windows Hidden attribute while preserving other attributes."""
    attributes = _get_windows_attributes(path)
    if attributes is None:
        return False
    if attributes & _WINDOWS_HIDDEN_ATTRIBUTE:
        return True
    return _set_windows_attributes(path, attributes | _WINDOWS_HIDDEN_ATTRIBUTE)


def _prepare_hidden_file_for_update(path: Path) -> int | None:
    """Temporarily clear Hidden/Read-only so an existing marker can be replaced."""
    attributes = _get_windows_attributes(path)
    if attributes is None:
        return None
    writable_attributes = attributes & ~(_WINDOWS_HIDDEN_ATTRIBUTE | _WINDOWS_READONLY_ATTRIBUTE)
    if writable_attributes != attributes:
        _set_windows_attributes(path, writable_attributes)
    return attributes


def _write_hidden_text(path: Path, content: str, *, encoding: str = 'utf-8') -> None:
    """Atomically replace a Windows hidden file, then reapply the Hidden attribute."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f'{path.name}.tmp')
    previous_attributes = _prepare_hidden_file_for_update(path) if path.exists() else None

    try:
        if temporary.exists():
            _prepare_hidden_file_for_update(temporary)
            temporary.unlink()
        temporary.write_text(content, encoding=encoding)
        os.replace(temporary, path)
        set_hidden(path)
    except Exception:
        if temporary.exists():
            try:
                _prepare_hidden_file_for_update(temporary)
                temporary.unlink()
            except OSError:
                pass
        if path.exists() and previous_attributes is not None:
            _set_windows_attributes(path, previous_attributes)
        raise


def visible_items(folder: Path) -> list[Path]:
    """Return user-facing directory entries, excluding dot-prefixed internals."""
    try:
        return sorted(
            (item for item in folder.iterdir() if not item.name.startswith('.')),
            key=lambda item: (not item.is_dir(), item.name.casefold()),
        )
    except OSError:
        return []


def hide_existing_internal_items(root: Path | None = None) -> int:
    """Hide existing dot-prefixed files and folders below the storage root."""
    target_root = root or storage_root()
    if os.name != 'nt' or not target_root.exists():
        return 0
    hidden_count = 0
    try:
        candidates = (item for item in target_root.rglob('*') if item.name.startswith('.'))
        for item in candidates:
            if set_hidden(item):
                hidden_count += 1
    except OSError:
        pass
    return hidden_count


def _configured_storage_path() -> Path | None:
    configured = db.get_setting('shared_root').strip()
    usb_root = usb_storage_service.find_export_usb()
    if not configured:
        return (usb_root / '수출관리') if usb_root else None

    path = Path(configured).expanduser()
    if path.is_absolute():
        if path.exists():
            return path
        if usb_root and path.anchor:
            try:
                relative = path.relative_to(path.anchor)
                return usb_root / relative
            except ValueError:
                pass
        return path
    if usb_root:
        return usb_root / path
    return path


def storage_root() -> Path:
    configured = _configured_storage_path()
    if configured is None:
        return db.UPLOAD_DIR
    anchor = configured.anchor
    if anchor:
        try:
            if not Path(anchor).exists():
                return db.UPLOAD_DIR
        except OSError:
            return db.UPLOAD_DIR
    return configured


def test_storage_root(path_text: str) -> tuple[bool, str]:
    path_text = path_text.strip()
    if not path_text:
        return False, '폴더 경로를 입력하세요.'
    try:
        path = Path(path_text).expanduser()
        anchor = path.anchor
        if anchor and not Path(anchor).exists():
            return False, f'드라이브 또는 공유 경로를 찾을 수 없습니다: {anchor}'
        path.mkdir(parents=True, exist_ok=True)
        probe = path / '.export_write_test'
        probe.write_text('ok', encoding='utf-8')
        probe.unlink()
        return True, str(path.resolve())
    except Exception as exc:
        return False, str(exc)


def order_item_summary(case_id: int) -> str:
    product_rows = db.rows(
        'SELECT product_name FROM order_items WHERE case_id=? ORDER BY id',
        (case_id,),
    )
    products: list[str] = []
    seen: set[str] = set()
    for product in product_rows:
        name = sanitize_folder_part(product['product_name'], '')
        if name and name not in seen:
            products.append(name)
            seen.add(name)
    if not products:
        return '제품미입력'
    if len(products) <= 2:
        return ', '.join(products)
    return f'{products[0]}, {products[1]} 외 {len(products) - 2}품목'


def _case_date(case) -> datetime:
    actual = parse_date(case['actual_ship_date'] if 'actual_ship_date' in case.keys() else '')
    if actual:
        return actual
    created = parse_date(str(case['created_at'] or '')[:10])
    return created or datetime.now()


def _actual_ship_date(case) -> datetime | None:
    if 'actual_ship_date' not in case.keys():
        return None
    return parse_date(case['actual_ship_date'])


def _is_missing_label(value: str, *missing_labels: str) -> bool:
    normalized = value.replace(' ', '').casefold()
    return not normalized or normalized in {label.replace(' ', '').casefold() for label in missing_labels}


def case_folder_name(case) -> str:
    actual_ship_date = _actual_ship_date(case)
    buyer = sanitize_folder_part(case['buyer'], '')
    transport = sanitize_folder_part(case['transport_mode'], '')
    summary = order_item_summary(int(case['id']))

    label_parts: list[str] = []
    if not _is_missing_label(buyer, '바이어미입력'):
        label_parts.append(buyer)
    if not _is_missing_label(transport, '운송방식미입력'):
        label_parts.append(transport)

    date_prefix = f'{actual_ship_date.strftime("%m%d")}_' if actual_ship_date else ''
    detail_prefix = f'[{" ".join(label_parts)}] ' if label_parts else ''
    name = f'{date_prefix}{detail_prefix}{summary}'

    if str(case['status']) == '취소' or str(case['stage']) == '취소':
        return name if name.startswith('[취소]') else f'[취소]{name}'
    return name.removeprefix('[취소]')


def case_folder_base(case) -> Path:
    case_date = _case_date(case)
    country = sanitize_folder_part(case['country'], '국가미입력')
    return storage_root() / country / case_date.strftime('%Y') / f'{case_date.strftime("%m")}월'


def _path_for_database(path: Path) -> str:
    usb_root = usb_storage_service.find_export_usb()
    if usb_root:
        try:
            return str(path.resolve().relative_to(usb_root.resolve()))
        except (ValueError, OSError):
            pass
    return str(path)


def resolve_database_path(path_text: str) -> Path | None:
    text = str(path_text or '').strip()
    if not text:
        return None
    path = Path(text).expanduser()
    if path.is_absolute() and path.exists():
        return path
    usb_root = usb_storage_service.find_export_usb()
    if usb_root:
        if path.is_absolute() and path.anchor:
            try:
                path = path.relative_to(path.anchor)
            except ValueError:
                return None
        candidate = usb_root / path
        if candidate.exists():
            return candidate
    if path.exists():
        return path
    return None


def write_case_marker(folder: Path, case) -> Path:
    marker = folder / CASE_MARKER_NAME
    _write_hidden_text(
        marker,
        json.dumps(
            {'case_id': int(case['id']), 'export_no': str(case['export_no'])},
            ensure_ascii=False,
            indent=2,
        ),
        encoding='utf-8',
    )
    return marker


def _marker_matches(marker: Path, case_id: int) -> bool:
    try:
        data = json.loads(marker.read_text(encoding='utf-8'))
        return int(data.get('case_id')) == int(case_id)
    except (OSError, ValueError, TypeError):
        return False


def find_case_folder(case_id: int) -> Path | None:
    case = db.row('SELECT folder_path FROM export_cases WHERE id=?', (case_id,))
    saved = resolve_database_path(case['folder_path'] if case else '')
    if saved and saved.exists():
        return saved
    root = storage_root()
    if not root.exists():
        return None
    try:
        for marker in root.rglob(CASE_MARKER_NAME):
            if _marker_matches(marker, case_id):
                return marker.parent
    except OSError:
        return None
    return None


def ensure_category_folders(folder: Path) -> None:
    for category, name in CATEGORY_FOLDERS.items():
        target = folder / name
        legacy = folder / LEGACY_CATEGORY_FOLDERS[category]
        if legacy.exists() and not target.exists():
            legacy.rename(target)
        target.mkdir(parents=True, exist_ok=True)


def category_folder(case_id: int, category: str) -> Path:
    folder = ensure_case_folder(case_id)
    name = CATEGORY_FOLDERS.get(category, CATEGORY_FOLDERS['기타'])
    target = folder / name
    target.mkdir(parents=True, exist_ok=True)
    return target


def unique_folder_path(base: Path, folder_name: str, current_path: Path | None = None) -> Path:
    target = base / folder_name
    if current_path and target.resolve() == current_path.resolve():
        return target
    if not target.exists():
        return target
    index = 2
    while True:
        candidate = base / f'{folder_name}_{index}'
        if current_path and candidate.resolve() == current_path.resolve():
            return candidate
        if not candidate.exists():
            return candidate
        index += 1


def _parse_timestamp(value: object) -> datetime | None:
    text = str(value or '').strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace('Z', '+00:00')).replace(tzinfo=None)
    except ValueError:
        return None


def _workbook_needs_update(case_id: int, folder: Path, *, force: bool = False) -> bool:
    workbook_path = folder / '수출진행내역.xlsx'
    if force or not workbook_path.exists():
        return True

    from nohtus.export_app.services.workbook_service import is_valid_xlsx

    if not is_valid_xlsx(workbook_path):
        return True

    timestamps: list[datetime] = []
    queries = [
        ('SELECT updated_at AS value FROM export_cases WHERE id=?', (case_id,)),
        ('SELECT MAX(created_at) AS value FROM order_items WHERE case_id=?', (case_id,)),
        ('SELECT MAX(COALESCE(updated_at, created_at)) AS value FROM shipment_items WHERE case_id=?', (case_id,)),
        ('SELECT MAX(updated_at) AS value FROM boxes WHERE case_id=?', (case_id,)),
    ]
    for sql, params in queries:
        row = db.row(sql, params)
        parsed = _parse_timestamp(row['value'] if row else '')
        if parsed:
            timestamps.append(parsed)
    if not timestamps:
        return False
    workbook_time = datetime.fromtimestamp(workbook_path.stat().st_mtime)
    return max(timestamps) > workbook_time


def _write_case_workbook(case_id: int, folder: Path) -> None:
    from nohtus.export_app.services.workbook_service import write_case_workbook

    write_case_workbook(case_id, folder)


def _prepare_folder(case, folder: Path, *, force_workbook: bool = False) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    write_case_marker(folder, case)
    set_hidden(folder / BACKUP_FOLDER_NAME)
    ensure_category_folders(folder)
    if _workbook_needs_update(int(case['id']), folder, force=force_workbook):
        _write_case_workbook(int(case['id']), folder)
    return folder


@db.backup_batch
def ensure_case_folder(case_id: int) -> Path:
    case = db.row('SELECT * FROM export_cases WHERE id=?', (case_id,))
    if not case:
        raise ValueError(f'수출 건을 찾을 수 없습니다: {case_id}')
    existing = find_case_folder(case_id)
    if existing:
        _prepare_folder(case, existing)
        stored = _path_for_database(existing)
        if str(case['folder_path'] or '') != stored:
            db.execute('UPDATE export_cases SET folder_path=?,updated_at=? WHERE id=?', (stored, now_text(), case_id))
        return existing
    base = case_folder_base(case)
    base.mkdir(parents=True, exist_ok=True)
    target = unique_folder_path(base, case_folder_name(case))
    _prepare_folder(case, target)
    db.execute('UPDATE export_cases SET folder_path=?,updated_at=? WHERE id=?', (_path_for_database(target), now_text(), case_id))
    return target


@db.backup_batch
def refresh_attachment_paths(case_id: int, old_root: Path, new_root: Path) -> None:
    old_text = str(old_root)
    for attachment in db.rows('SELECT id, stored_path FROM attachments WHERE case_id=?', (case_id,)):
        stored = str(attachment['stored_path'])
        resolved = resolve_database_path(stored) or Path(stored)
        if str(resolved).startswith(old_text):
            replacement = new_root / resolved.relative_to(old_root)
            db.execute('UPDATE attachments SET stored_path=? WHERE id=?', (_path_for_database(replacement), attachment['id']))


@db.backup_batch
def sync_case_folder(case_id: int, *, force_workbook: bool = False) -> Path:
    case = db.row('SELECT * FROM export_cases WHERE id=?', (case_id,))
    if not case:
        raise ValueError(f'수출 건을 찾을 수 없습니다: {case_id}')
    base = case_folder_base(case)
    current = find_case_folder(case_id)
    target = unique_folder_path(base, case_folder_name(case), current)
    base.mkdir(parents=True, exist_ok=True)
    if current and current.exists() and current.resolve() != target.resolve():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(current), str(target))
        refresh_attachment_paths(case_id, current, target)
    elif not current:
        target.mkdir(parents=True, exist_ok=True)
    stored_target = _path_for_database(target)
    if str(case['folder_path'] or '') != stored_target:
        db.execute(
            'UPDATE export_cases SET folder_path=?,updated_at=? WHERE id=?',
            (stored_target, now_text(), case_id),
        )
        case = db.row('SELECT * FROM export_cases WHERE id=?', (case_id,))
    _prepare_folder(case, target, force_workbook=force_workbook)
    return target


def rebuild_all_case_folders() -> list[tuple[int, Path]]:
    cases = db.rows(
        """SELECT id FROM export_cases
           WHERE status<>'취소' AND stage<>'취소'
           ORDER BY id"""
    )
    return [
        (int(case['id']), sync_case_folder(int(case['id']), force_workbook=True))
        for case in cases
    ]


@db.backup_batch
def move_file_to_case(case_id: int, source: Path, category: str = '출고사진') -> Path:
    destination_folder = category_folder(case_id, category)
    destination = destination_folder / source.name
    counter = 2
    while destination.exists():
        destination = destination_folder / f'{source.stem}_{counter}{source.suffix}'
        counter += 1
    shutil.copy2(source, destination)
    db.execute(
        '''INSERT INTO attachments(case_id,category,original_name,stored_path,created_at)
           VALUES (?,?,?,?,?)''',
        (case_id, category, source.name, _path_for_database(destination), now_text()),
    )
    return destination


def delete_attachment(attachment_id: int) -> None:
    attachment = db.row('SELECT stored_path FROM attachments WHERE id=?', (attachment_id,))
    if not attachment:
        return
    path = resolve_database_path(attachment['stored_path']) or Path(str(attachment['stored_path']))
    if path.exists():
        path.unlink()
    db.execute('DELETE FROM attachments WHERE id=?', (attachment_id,))


def list_attachments(case_id: int):
    return [
        attachment
        for attachment in db.rows(
            'SELECT id,category,original_name,stored_path,created_at FROM attachments WHERE case_id=? ORDER BY id',
            (case_id,),
        )
        if not Path(str(attachment['original_name'] or '')).name.startswith('.')
    ]
