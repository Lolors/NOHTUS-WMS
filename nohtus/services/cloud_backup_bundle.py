"""Create a verified local archive before publishing it to Drive."""
from pathlib import Path
from datetime import timedelta, datetime
from contextlib import closing
import json
import shutil
import sqlite3
import tempfile
import zipfile


def _photo_backup(root, destination, now):
    prefix = "wms_photos_"
    existing = []
    for path in destination.glob(prefix + "*.zip"):
        try:
            stamp = datetime.strptime(path.stem.removeprefix(prefix), "%Y%m%d_%H%M%S_%f")
        except ValueError:
            continue
        existing.append((stamp, path))
    existing.sort(reverse=True)
    if existing and now - existing[0][0] < timedelta(hours=24):
        return existing[0][1].name
    name = f"{prefix}{now:%Y%m%d_%H%M%S_%f}.zip"
    with tempfile.TemporaryDirectory(prefix="nohtus-photos-") as temporary:
        archive = Path(temporary) / name
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as output:
            for path in sorted((root / "data" / "product_images").rglob("*")):
                if path.is_file() and not path.is_symlink():
                    output.write(path, path.relative_to(root).as_posix())
            output.writestr("photo_manifest.json", json.dumps({"created_at": now.isoformat(), "version": 1}))
        with zipfile.ZipFile(archive) as check:
            if check.testzip() is not None:
                raise ValueError("제품사진 백업 검사 실패")
        pending = destination / (name + ".partial")
        try:
            shutil.copyfile(archive, pending)
            with zipfile.ZipFile(pending) as check:
                if check.testzip() is not None:
                    raise ValueError("제품사진 Drive 복사본 검사 실패")
            pending.replace(destination / name)
        finally:
            pending.unlink(missing_ok=True)
    return name


def create_bundle(root, targets, destination, now):
    root, destination = Path(root), Path(destination)
    if not destination.parent.is_dir():
        raise OSError("Google Drive 동기화 폴더에 연결할 수 없습니다.")
    destination.mkdir(exist_ok=True)
    photo_archive = _photo_backup(root, destination, now)
    name = f"wms_bundle_{now:%Y%m%d_%H%M%S_%f}.zip"
    with tempfile.TemporaryDirectory(prefix="nohtus-backup-") as temporary:
        stage = Path(temporary)
        archive = stage / name
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as output:
            for source, prefix in targets:
                source = Path(source)
                if not source.is_file():
                    raise FileNotFoundError(source)
                snapshot = stage / (prefix + ".db")
                with closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)) as db:
                    with closing(sqlite3.connect(snapshot)) as copy:
                        db.backup(copy)
                        if copy.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                            raise ValueError(f"DB 무결성 검사 실패: {prefix}")
                output.write(snapshot, source.relative_to(root).as_posix())
            # Explicit allowlist: never include credentials, caches or old backups.
            for folder in ("export_uploads", "discrepancy_comic"):
                for path in sorted((root / "data" / folder).rglob("*")):
                    if path.is_file() and not path.is_symlink():
                        output.write(path, path.relative_to(root).as_posix())
            for filename in ("location_map_layout.json", "location_map_layout.draft.json"):
                path = root / "data" / filename
                if path.is_file():
                    output.write(path, path.relative_to(root).as_posix())
            output.writestr("backup_manifest.json", json.dumps({"created_at": now.isoformat(), "version": 2, "product_photos_archive": photo_archive, "note": "DB snapshots are sequential; restore with WMS stopped."}))
        with zipfile.ZipFile(archive) as check:
            if check.testzip() is not None:
                raise ValueError("백업 ZIP 검사 실패")
        pending = destination / (name + ".partial")
        try:
            shutil.copyfile(archive, pending)
            with zipfile.ZipFile(pending) as check:
                if check.testzip() is not None:
                    raise ValueError("Drive 복사본 검사 실패")
            final = destination / name
            pending.replace(final)
        finally:
            pending.unlink(missing_ok=True)
    # Only this feature's archives are eligible for pruning; legacy DB backups remain.
    daily = set()
    for path in sorted(destination.glob("wms_bundle_*.zip"), reverse=True):
        try:
            stamp = datetime.strptime(path.stem.removeprefix("wms_bundle_"), "%Y%m%d_%H%M%S_%f")
        except ValueError:
            continue
        age = now - stamp
        keep = age <= timedelta(hours=24) or (age <= timedelta(days=30) and stamp.date() not in daily)
        daily.add(stamp.date())
        if not keep:
            path.unlink()
    referenced_photos = {photo_archive}
    for bundle in destination.glob("wms_bundle_*.zip"):
        try:
            with zipfile.ZipFile(bundle) as saved:
                referenced_photos.add(json.loads(saved.read("backup_manifest.json")).get("product_photos_archive"))
        except (OSError, ValueError, KeyError, zipfile.BadZipFile):
            # Avoid deleting dependencies if a retained manifest cannot be read.
            return str(final)
    for photo in destination.glob("wms_photos_*.zip"):
        if photo.name not in referenced_photos:
            photo.unlink()
    return str(final)
