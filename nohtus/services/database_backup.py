from __future__ import annotations

import json
import sqlite3
import tempfile
import threading
from datetime import datetime, timedelta
from pathlib import Path

from nohtus.config import DB_PATH, PROJECT_ROOT

BACKUP_INTERVAL = timedelta(hours=1)
MAX_BACKUPS = 20
LOCAL_BACKUP_DIR = PROJECT_ROOT / "backups"
GOOGLE_DRIVE_FOLDER_NAME = "NOHTUS_WMS_BACKUP"
STATE_PATH = LOCAL_BACKUP_DIR / ".backup_state.json"
_WORKER_LOCK = threading.Lock()
_WORKER_STARTED = False

# 두 DB는 하나의 백업 세트다. 한쪽만 백업되는 상태를 막기 위해
# 주기 판단도 세트 단위로 하고, 실행 시 항상 둘 다 시도한다.
EXPORT_DB_PATH = PROJECT_ROOT / "data" / "export.db"
_BACKUP_TARGETS = (
    (Path(DB_PATH), "nohtus"),
    (Path(EXPORT_DB_PATH), "export"),
)
LOCAL_SET_STATE_KEY = "last_local_pair"
DRIVE_SET_STATE_KEY = "last_google_drive_pair"


def _read_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_state(state: dict) -> None:
    LOCAL_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


def _backup_to(source_path: Path, directory: Path, now: datetime, prefix: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"{prefix}_{now:%Y%m%d_%H%M%S}.db"
    with sqlite3.connect(source_path) as source, sqlite3.connect(destination) as target:
        source.backup(target)
    backups = sorted(directory.glob(f"{prefix}_*.db"), key=lambda path: path.stat().st_mtime, reverse=True)
    for old_backup in backups[MAX_BACKUPS:]:
        old_backup.unlink(missing_ok=True)
    return destination


def current_wms_db_bytes() -> bytes:
    """지금 이 순간의 WMS DB(nohtus.db)를 안전하게 스냅샷 떠서 바이트로 반환한다."""
    source_path = Path(DB_PATH)
    if not source_path.is_file():
        raise ValueError(f"WMS DB를 찾을 수 없습니다: {source_path}")

    with tempfile.TemporaryDirectory() as temp_dir:
        snapshot_path = Path(temp_dir) / "nohtus_snapshot.db"
        with sqlite3.connect(source_path) as source, sqlite3.connect(snapshot_path) as target:
            source.backup(target)
        return snapshot_path.read_bytes()


def _state_time(state: dict, key: str) -> datetime:
    try:
        return datetime.fromisoformat(str(state.get(key) or ""))
    except ValueError:
        return datetime.min


def _pair_is_due(state: dict, pair_key: str, legacy_keys: tuple[str, ...], now: datetime) -> bool:
    """신규 세트 상태가 없으면 과거 개별 상태 중 가장 오래된 시각을 기준으로 즉시 보정한다."""
    if state.get(pair_key):
        return now - _state_time(state, pair_key) >= BACKUP_INTERVAL

    legacy_times = [_state_time(state, key) for key in legacy_keys if state.get(key)]
    if len(legacy_times) < len(legacy_keys):
        return True
    return now - min(legacy_times) >= BACKUP_INTERVAL


def _backup_pair(directory: Path, now: datetime) -> tuple[list[str], list[str]]:
    """nohtus.db와 export.db를 같은 실행에서 함께 백업한다."""
    paths: list[str] = []
    errors: list[str] = []
    for source_path, prefix in _BACKUP_TARGETS:
        if not source_path.is_file():
            errors.append(f"백업 대상 DB를 찾을 수 없습니다({prefix}): {source_path}")
            continue
        try:
            paths.append(str(_backup_to(source_path, directory, now, prefix)))
        except (OSError, sqlite3.Error) as exc:
            errors.append(f"백업 실패({prefix}, {directory}): {exc}")
    return paths, errors


def google_drive_root() -> str:
    return str(_read_state().get("google_drive_root") or "").strip()


def google_drive_backup_dir() -> Path | None:
    configured = google_drive_root()
    if not configured:
        return None
    return Path(configured).expanduser() / GOOGLE_DRIVE_FOLDER_NAME


def set_google_drive_root(path_text: str) -> Path:
    configured = str(path_text or "").strip().strip('"')
    if not configured:
        raise ValueError("Google Drive 동기화 폴더 경로를 입력해 주세요.")

    root = Path(configured).expanduser()
    if not root.exists() or not root.is_dir():
        raise ValueError("입력한 Google Drive 동기화 폴더를 찾을 수 없습니다.")

    backup_dir = root / GOOGLE_DRIVE_FOLDER_NAME
    backup_dir.mkdir(parents=True, exist_ok=True)

    state = _read_state()
    if state.get("google_drive_root") != str(root):
        # 경로 변경 직후 두 DB를 새 위치에 반드시 한 세트로 다시 백업한다.
        state.pop(DRIVE_SET_STATE_KEY, None)
        state.pop("last_google_drive", None)
        state.pop("last_google_drive_export", None)
    state["google_drive_root"] = str(root)
    _write_state(state)
    return backup_dir


def run_due_backups() -> dict:
    now = datetime.now()
    state = _read_state()
    result = {"local": [], "google_drive": [], "errors": []}

    local_due = _pair_is_due(
        state,
        LOCAL_SET_STATE_KEY,
        ("last_local", "last_local_export"),
        now,
    )
    if local_due:
        paths, errors = _backup_pair(LOCAL_BACKUP_DIR, now)
        result["local"].extend(paths)
        result["errors"].extend(errors)
        # 둘 다 성공한 경우에만 세트 전체가 완료된 것으로 기록한다.
        if len(paths) == len(_BACKUP_TARGETS) and not errors:
            state[LOCAL_SET_STATE_KEY] = now.isoformat(timespec="seconds")
            state["last_local"] = state[LOCAL_SET_STATE_KEY]
            state["last_local_export"] = state[LOCAL_SET_STATE_KEY]

    drive_dir = google_drive_backup_dir()
    if drive_dir is not None:
        drive_due = _pair_is_due(
            state,
            DRIVE_SET_STATE_KEY,
            ("last_google_drive", "last_google_drive_export"),
            now,
        )
        if drive_due:
            paths, errors = _backup_pair(drive_dir, now)
            result["google_drive"].extend(paths)
            result["errors"].extend(
                error.replace("백업 실패", "Google Drive 백업 실패", 1)
                for error in errors
            )
            if len(paths) == len(_BACKUP_TARGETS) and not errors:
                state[DRIVE_SET_STATE_KEY] = now.isoformat(timespec="seconds")
                state["last_google_drive"] = state[DRIVE_SET_STATE_KEY]
                state["last_google_drive_export"] = state[DRIVE_SET_STATE_KEY]

    _write_state(state)
    return result


def backup_to_google_drive_now() -> str:
    directory = google_drive_backup_dir()
    if directory is None:
        raise ValueError("먼저 Google Drive 동기화 폴더 경로를 저장해 주세요.")

    now = datetime.now()
    state = _read_state()
    paths, errors = _backup_pair(directory, now)
    if errors:
        raise ValueError(" / ".join(errors))
    if len(paths) != len(_BACKUP_TARGETS):
        raise ValueError("nohtus.db와 export.db를 모두 백업하지 못했습니다.")

    state[DRIVE_SET_STATE_KEY] = now.isoformat(timespec="seconds")
    state["last_google_drive"] = state[DRIVE_SET_STATE_KEY]
    state["last_google_drive_export"] = state[DRIVE_SET_STATE_KEY]
    _write_state(state)
    return "\n".join(paths)


def _backup_worker() -> None:
    while True:
        threading.Event().wait(BACKUP_INTERVAL.total_seconds())
        try:
            run_due_backups()
        except Exception:
            # 백업 오류가 앱 서버를 중단시키지 않도록 다음 주기에 재시도한다.
            continue


def start_backup_worker() -> None:
    global _WORKER_STARTED
    with _WORKER_LOCK:
        if _WORKER_STARTED:
            return
        threading.Thread(target=_backup_worker, name="nohtus-db-backup", daemon=True).start()
        _WORKER_STARTED = True
