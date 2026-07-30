from __future__ import annotations

import json
import sqlite3
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


def _read_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_state(state: dict) -> None:
    LOCAL_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


def _backup_to(directory: Path, now: datetime) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"nohtus_{now:%Y%m%d_%H%M%S}.db"
    with sqlite3.connect(DB_PATH) as source, sqlite3.connect(destination) as target:
        source.backup(target)
    backups = sorted(directory.glob("nohtus_*.db"), key=lambda path: path.stat().st_mtime, reverse=True)
    for old_backup in backups[MAX_BACKUPS:]:
        old_backup.unlink(missing_ok=True)
    return destination


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
        state.pop("last_google_drive", None)
    state["google_drive_root"] = str(root)
    _write_state(state)
    return backup_dir


def run_due_backups() -> dict:
    if not DB_PATH.is_file():
        return {"local": None, "google_drive": None, "errors": []}

    now = datetime.now()
    state = _read_state()
    result = {"local": None, "google_drive": None, "errors": []}

    try:
        last_local = datetime.fromisoformat(state.get("last_local", ""))
    except ValueError:
        last_local = datetime.min
    if now - last_local >= BACKUP_INTERVAL:
        try:
            result["local"] = str(_backup_to(LOCAL_BACKUP_DIR, now))
            state["last_local"] = now.isoformat(timespec="seconds")
        except (OSError, sqlite3.Error) as exc:
            result["errors"].append(f"로컬 백업 실패: {exc}")

    drive_dir = google_drive_backup_dir()
    if drive_dir is not None:
        try:
            last_drive = datetime.fromisoformat(state.get("last_google_drive", ""))
        except ValueError:
            last_drive = datetime.min
        if now - last_drive >= BACKUP_INTERVAL:
            try:
                result["google_drive"] = str(_backup_to(drive_dir, now))
                state["last_google_drive"] = now.isoformat(timespec="seconds")
            except (OSError, sqlite3.Error) as exc:
                result["errors"].append(f"Google Drive 백업 실패({drive_dir}): {exc}")

    _write_state(state)
    return result


def backup_to_google_drive_now() -> str:
    directory = google_drive_backup_dir()
    if directory is None:
        raise ValueError("먼저 Google Drive 동기화 폴더 경로를 저장해 주세요.")
    path = _backup_to(directory, datetime.now())
    state = _read_state()
    state["last_google_drive"] = datetime.now().isoformat(timespec="seconds")
    _write_state(state)
    return str(path)


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
