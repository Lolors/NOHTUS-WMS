from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import string
import time
from contextlib import closing
from datetime import datetime
from functools import lru_cache
from pathlib import Path

USB_MARKER_NAME = '.export_usb.json'
USB_STORAGE_ID = 'NOHTUS_EXPORT_USB'
USB_DB_DIR = 'EXPORT_DB'
USB_DB_NAME = 'export.db'
DB_VERSION = 1
MAX_DB_SNAPSHOTS = 20
_USB_CACHE_SECONDS = 5.0
_USB_CACHE_CHECKED_AT = 0.0
_USB_CACHE_ROOT: Path | None = None


def _candidate_roots() -> list[Path]:
    if os.name != 'nt':
        return []

    # Asking every drive letter whether it exists can pause on disconnected
    # network drives. Windows exposes the mounted-drive bitmask in one call.
    try:
        import ctypes

        drive_mask = int(ctypes.windll.kernel32.GetLogicalDrives())
    except (AttributeError, OSError, ValueError):
        drive_mask = 0

    if drive_mask:
        return [
            Path(f'{letter}:\\')
            for index, letter in enumerate(string.ascii_uppercase)
            if drive_mask & (1 << index)
        ]

    roots: list[Path] = []
    for letter in string.ascii_uppercase:
        root = Path(f'{letter}:\\')
        try:
            if root.exists():
                roots.append(root)
        except OSError:
            continue
    return roots


def read_usb_marker(root: Path) -> dict:
    marker = root / USB_MARKER_NAME
    try:
        data = json.loads(marker.read_text(encoding='utf-8'))
    except (OSError, ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def is_export_usb(root: Path) -> bool:
    return read_usb_marker(root).get('storage_id') == USB_STORAGE_ID


def clear_usb_search_cache() -> None:
    global _USB_CACHE_CHECKED_AT, _USB_CACHE_ROOT
    _USB_CACHE_CHECKED_AT = 0.0
    _USB_CACHE_ROOT = None


def find_export_usb() -> Path | None:
    """Cache the expensive Windows drive scan briefly within repeated reruns."""
    global _USB_CACHE_CHECKED_AT, _USB_CACHE_ROOT
    checked_at = time.monotonic()
    if checked_at - _USB_CACHE_CHECKED_AT < _USB_CACHE_SECONDS:
        return _USB_CACHE_ROOT

    found = None
    for root in _candidate_roots():
        if is_export_usb(root):
            found = root
            break
    _USB_CACHE_ROOT = found
    _USB_CACHE_CHECKED_AT = checked_at
    return found


def drive_root_for(path: Path) -> Path | None:
    resolved = Path(path).expanduser()
    if os.name != 'nt' or not resolved.drive:
        return None
    return Path(f'{resolved.drive}\\')


def register_export_usb(path: Path) -> Path:
    root = drive_root_for(path)
    if root is None or not root.exists():
        raise ValueError('Windows USB 드라이브 경로를 선택하세요.')
    marker = root / USB_MARKER_NAME
    marker.write_text(
        json.dumps(
            {
                'storage_id': USB_STORAGE_ID,
                'version': 1,
                'registered_at': datetime.now().isoformat(timespec='seconds'),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding='utf-8',
    )
    global _USB_CACHE_CHECKED_AT, _USB_CACHE_ROOT
    _USB_CACHE_ROOT = root
    _USB_CACHE_CHECKED_AT = time.monotonic()
    return root


def usb_database_path(root: Path | None = None) -> Path | None:
    usb_root = root or find_export_usb()
    if usb_root is None:
        return None
    return usb_root / USB_DB_DIR / USB_DB_NAME


@lru_cache(maxsize=32)
def _cached_database_info(path_text: str, modified_ns: int, size: int) -> dict:
    path = Path(path_text)
    version = DB_VERSION
    logical_digest = ''
    try:
        uri_path = path.resolve().as_posix()
        with closing(sqlite3.connect(f'file:{uri_path}?mode=ro', uri=True, timeout=5.0)) as conn:
            row = conn.execute('PRAGMA user_version').fetchone()
            version = int(row[0] or DB_VERSION) if row else DB_VERSION
            digest = hashlib.sha256()
            for statement in conn.iterdump():
                digest.update(statement.encode('utf-8'))
                digest.update(b'\n')
            logical_digest = digest.hexdigest()
    except (OSError, sqlite3.Error):
        version = 0
        logical_digest = ''

    return {
        'exists': True,
        'version': version,
        'modified_at': datetime.fromtimestamp(modified_ns / 1_000_000_000),
        'size': size,
        'logical_digest': logical_digest,
    }


def database_info(path: Path) -> dict:
    if not path.exists():
        return {
            'exists': False,
            'version': 0,
            'modified_at': None,
            'size': 0,
            'logical_digest': '',
        }

    stat = path.stat()
    return dict(_cached_database_info(str(path.resolve()), stat.st_mtime_ns, stat.st_size))


def compare_databases(local_path: Path, usb_path: Path | None) -> dict:
    local = database_info(local_path)
    usb = database_info(usb_path) if usb_path else {
        'exists': False,
        'version': 0,
        'modified_at': None,
        'size': 0,
        'logical_digest': '',
    }
    same_database = bool(
        local['logical_digest']
        and usb['logical_digest']
        and local['logical_digest'] == usb['logical_digest']
    )
    usb_is_newer = bool(
        usb['exists']
        and not same_database
        and (
            usb['version'] > local['version']
            or (
                usb['version'] == local['version']
                and usb['modified_at']
                and (not local['modified_at'] or usb['modified_at'] > local['modified_at'])
            )
        )
    )
    return {
        'local': local,
        'usb': usb,
        'same_database': same_database,
        'usb_is_newer': usb_is_newer,
    }


def _replace_with_retry(source: Path, destination: Path, attempts: int = 5) -> None:
    for attempt in range(attempts):
        try:
            source.replace(destination)
            return
        except OSError as exc:
            if getattr(exc, 'winerror', None) != 32 or attempt == attempts - 1:
                raise
            time.sleep(0.2 * (attempt + 1))


def validate_sqlite_database(path: Path) -> None:
    try:
        with closing(sqlite3.connect(f'file:{path}?mode=ro&immutable=1', uri=True, timeout=10.0)) as connection:
            result = connection.execute('PRAGMA quick_check').fetchone()
    except sqlite3.DatabaseError as exc:
        raise ValueError(f'DB 무결성 검사에 실패했습니다: {path}') from exc
    if not result or str(result[0]).strip().casefold() != 'ok':
        detail = str(result[0]) if result else '검사 결과 없음'
        raise ValueError(f'DB가 손상되었습니다: {path} ({detail})')


def _finish_standalone_database(connection: sqlite3.Connection) -> None:
    connection.commit()
    connection.execute('PRAGMA journal_mode=DELETE')
    connection.commit()


def _cleanup_backup_artifacts(backup_dir: Path) -> None:
    patterns = ('*.db-wal', '*.db-shm', '*.tmp-wal', '*.tmp-shm')
    for pattern in patterns:
        for artifact in backup_dir.glob(pattern):
            try:
                artifact.unlink()
            except FileNotFoundError:
                pass
    legacy_backup = backup_dir / 'export.db.bak'
    if legacy_backup.exists():
        legacy_backup.unlink()


def list_database_snapshots(root: Path | None = None) -> list[Path]:
    usb_root = root or find_export_usb()
    if usb_root is None:
        return []
    backup_dir = usb_root / USB_DB_DIR
    if not backup_dir.exists():
        return []
    return sorted(
        backup_dir.glob('*_export.db'),
        key=lambda path: path.name,
        reverse=True,
    )


def _create_timestamped_snapshot(temporary: Path, backup_dir: Path) -> Path:
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]
    snapshot = backup_dir / f'{timestamp}_export.db'
    snapshot_temporary = backup_dir / f'.{timestamp}_export.db.tmp'
    shutil.copy2(temporary, snapshot_temporary)
    validate_sqlite_database(snapshot_temporary)
    _replace_with_retry(snapshot_temporary, snapshot)
    validate_sqlite_database(snapshot)
    return snapshot


def _prune_database_snapshots(backup_dir: Path) -> None:
    snapshots = sorted(
        backup_dir.glob('*_export.db'),
        key=lambda path: path.name,
        reverse=True,
    )
    for old_snapshot in snapshots[MAX_DB_SNAPSHOTS:]:
        old_snapshot.unlink()


def safe_backup_database(local_path: Path, usb_root: Path | None = None) -> Path | None:
    root = usb_root or find_export_usb()
    if root is None or not local_path.exists():
        return None
    destination = root / USB_DB_DIR / USB_DB_NAME
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix('.db.tmp')
    if temporary.exists():
        temporary.unlink()

    with closing(sqlite3.connect(local_path, timeout=10.0)) as source:
        with closing(sqlite3.connect(temporary, timeout=10.0)) as target:
            source.backup(target)
            target.execute(f'PRAGMA user_version = {DB_VERSION}')
            _finish_standalone_database(target)

    validate_sqlite_database(temporary)

    snapshot = _create_timestamped_snapshot(temporary, destination.parent)
    _replace_with_retry(temporary, destination)
    validate_sqlite_database(destination)
    validate_sqlite_database(snapshot)
    _prune_database_snapshots(destination.parent)
    _cleanup_backup_artifacts(destination.parent)
    return destination


def restore_database_from_usb(local_path: Path, usb_path: Path) -> Path:
    if not usb_path.exists():
        raise FileNotFoundError('USB 백업 DB를 찾을 수 없습니다.')
    validate_sqlite_database(usb_path)

    temporary = local_path.with_suffix('.db.restore.tmp')
    if temporary.exists():
        temporary.unlink()
    with closing(sqlite3.connect(usb_path, timeout=10.0)) as source:
        with closing(sqlite3.connect(temporary, timeout=10.0)) as target:
            source.backup(target)
            _finish_standalone_database(target)

    validate_sqlite_database(temporary)
    _replace_with_retry(temporary, local_path)
    validate_sqlite_database(local_path)
    return local_path
