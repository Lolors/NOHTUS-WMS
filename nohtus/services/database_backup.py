from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from nohtus.config import DB_PATH, PROJECT_ROOT
from nohtus.services.usb_storage import removable_roots


BACKUP_INTERVAL = timedelta(hours=1)
MAX_BACKUPS = 20
LOCAL_BACKUP_DIR = PROJECT_ROOT / "backups"
STATE_PATH = LOCAL_BACKUP_DIR / ".backup_state.json"


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


def _usb_backup_dirs() -> list[Path]:
    return [root / "NOHTUS_WMS_BACKUP" for root in removable_roots()]


def run_due_backups() -> dict:
    if not DB_PATH.is_file():
        return {"local": None, "usb": [], "errors": []}
    now = datetime.now()
    state = _read_state()
    result = {"local": None, "usb": [], "errors": []}

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

    for directory in _usb_backup_dirs():
        key = str(directory)
        try:
            last_usb = datetime.fromisoformat(state.get("usb", {}).get(key, ""))
        except ValueError:
            last_usb = datetime.min
        if now - last_usb < BACKUP_INTERVAL:
            continue
        try:
            result["usb"].append(str(_backup_to(directory, now)))
            state.setdefault("usb", {})[key] = now.isoformat(timespec="seconds")
        except (OSError, sqlite3.Error) as exc:
            result["errors"].append(f"USB 백업 실패({directory}): {exc}")

    _write_state(state)
    return result


def backup_to_usb_now() -> list[str]:
    directories = _usb_backup_dirs()
    if not directories:
        raise ValueError("연결된 외장 USB를 찾을 수 없습니다.")
    now = datetime.now()
    paths = [str(_backup_to(directory, now)) for directory in directories]
    state = _read_state()
    for directory in directories:
        state.setdefault("usb", {})[str(directory)] = now.isoformat(timespec="seconds")
    _write_state(state)
    return paths
