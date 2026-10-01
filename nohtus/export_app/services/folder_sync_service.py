"""사용자가 선택한 범위의 수출 폴더를 재생성하고 하나의 배치로 모은다."""
from datetime import date, datetime, timedelta
from pathlib import Path
import shutil
from nohtus.export_app.services import folder_service


def reference_date(case):
    dates = []
    for key in ("actual_ship_date", "created_at", "updated_at"):
        try:
            dates.append(date.fromisoformat(str(case[key] or "")[:10]))
        except (KeyError, IndexError, TypeError, ValueError):
            pass
    return max(dates) if dates else None


def select_cases(cases, days=None, today=None):
    cutoff = (today or date.today()) - timedelta(days=days - 1) if days else None
    return [case for case in cases
            if case["status"] != "취소" and case["stage"] != "취소"
            and (cutoff is None or (reference_date(case) is not None and reference_date(case) >= cutoff))]


def rebuild_batch(cases, progress=None):
    result = dict(root=None, rebuilt=[], skipped=[], gathered=[], failures=[], copy_failures=[], drive_corruption=False)
    cases = list(cases)
    if not cases:
        return result
    root = folder_service.storage_root().resolve()
    for index, case in enumerate(cases, 1):
        try:
            folder, changed = folder_service.sync_case_folder_if_changed(int(case["id"]))
            if not changed:
                result["skipped"].append(str(case["export_no"]))
                if progress:
                    progress(index, len(cases))
                continue
            folder = folder.resolve()
            result["rebuilt"].append(str(case["export_no"]))
            if result["root"] is None:
                batch = root / f"갱신폴더_{datetime.now():%Y%m%d_%H%M%S_%f}"
                batch.mkdir(parents=True, exist_ok=False)
                result["root"] = batch
            try:
                # Preserve country/year/month so equal folder names never merge.
                relative = folder.relative_to(root)
                target = result["root"] / relative
                shutil.copytree(folder, target, dirs_exist_ok=False)
                result["gathered"].append((str(case["export_no"]), str(relative)))
            except Exception as exc:
                result["copy_failures"].append(f"{case['export_no']}: {exc}")
                if getattr(exc, "winerror", None) == 1392:
                    result["drive_corruption"] = True
        except Exception as exc:
            result["failures"].append(f"{case['export_no']}: {exc}")
            if getattr(exc, "winerror", None) == 1392:
                result["drive_corruption"] = True
        if progress:
            progress(index, len(cases))
        if result["drive_corruption"]:
            break
    return result
