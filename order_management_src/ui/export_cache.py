"""발주서 내보내기 파일 캐시와 output 정리 유틸리티."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


EXPORT_CACHE_FILE = "export_cache.json"
EXPORT_CACHE_VERSION = 1
MAX_OUTPUT_FILE_AGE_DAYS = 7


def _safe_text(value: Any) -> str:
    text = str(value or "").strip()
    return text or "미지정"


def _safe_int(value: Any) -> int:
    try:
        return int(float(str(value or "0").replace(",", "")))
    except (TypeError, ValueError):
        return 0


def _safe_filename_part(value: Any) -> str:
    text = _safe_text(value)
    text = re.sub(r'[\\/:*?"<>|]+', "_", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:40] or "미지정"


def _payload(vendor, order_items, request_note: str, order_date: str, kind: str) -> dict[str, Any]:
    items = []
    for item in order_items or []:
        items.append({
            "제품코드": _safe_text(item.get("제품코드", "")),
            "정식제품명": _safe_text(item.get("정식제품명", item.get("제품명", ""))),
            "규격": _safe_text(item.get("규격", "")),
            "단위": _safe_text(item.get("단위", item.get("포장단위", ""))),
            "수량": _safe_int(item.get("수량", 0)),
        })
    return {
        "version": EXPORT_CACHE_VERSION,
        "kind": kind,
        "거래처명": _safe_text(vendor.get("거래처명", "")),
        "납품처": _safe_text(vendor.get("배송지", "")),
        "연락처": _safe_text(vendor.get("연락처", "")),
        "발주일자": str(order_date or ""),
        "요청사항": str(request_note or ""),
        "items": items,
    }


def export_fingerprint(vendor, order_items, request_note: str, order_date: str, kind: str) -> str:
    raw = json.dumps(
        _payload(vendor, order_items, request_note, order_date, kind),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _cache_file(core_app) -> Path:
    core_app.OUTPUT.mkdir(parents=True, exist_ok=True)
    return core_app.OUTPUT / EXPORT_CACHE_FILE


def _load_cache(core_app) -> dict[str, Any]:
    path = _cache_file(core_app)
    if not path.exists():
        return {"version": EXPORT_CACHE_VERSION, "files": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"version": EXPORT_CACHE_VERSION, "files": {}}
    if not isinstance(data, dict):
        return {"version": EXPORT_CACHE_VERSION, "files": {}}
    data.setdefault("files", {})
    return data


def _save_cache(core_app, cache: dict[str, Any]) -> None:
    path = _cache_file(core_app)
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def cleanup_output_files(core_app, max_age_days: int = MAX_OUTPUT_FILE_AGE_DAYS) -> None:
    """output/excel, output/pdf, output/png의 오래된 생성 파일을 정리합니다."""
    cutoff = datetime.now() - timedelta(days=max_age_days)
    directories = [
        core_app.EXCEL_OUTPUT,
        core_app.PDF_OUTPUT,
        core_app.OUTPUT / "png",
    ]
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
        for path in directory.iterdir():
            if not path.is_file():
                continue
            try:
                modified = datetime.fromtimestamp(path.stat().st_mtime)
            except OSError:
                continue
            if modified < cutoff:
                try:
                    path.unlink()
                except OSError:
                    pass

    cache = _load_cache(core_app)
    files = cache.get("files", {})
    cleaned = {
        fingerprint: info
        for fingerprint, info in files.items()
        if Path(str(info.get("path", ""))).exists()
    }
    if cleaned != files:
        cache["files"] = cleaned
        _save_cache(core_app, cache)


def _target_excel_path(core_app, vendor, order_date: str) -> Path:
    vendor_name = _safe_filename_part(vendor.get("거래처명", ""))
    date_text = str(order_date or datetime.now().strftime("%Y-%m-%d")).replace("-", "")
    stamp = datetime.now().strftime("%H%M%S")
    core_app.EXCEL_OUTPUT.mkdir(parents=True, exist_ok=True)
    base = core_app.EXCEL_OUTPUT / f"PO-{vendor_name}-{date_text}-{stamp}.xlsx"
    if not base.exists():
        return base
    for suffix in range(2, 100):
        candidate = core_app.EXCEL_OUTPUT / f"PO-{vendor_name}-{date_text}-{stamp}-{suffix}.xlsx"
        if not candidate.exists():
            return candidate
    return core_app.EXCEL_OUTPUT / f"PO-{vendor_name}-{date_text}-{stamp}-{datetime.now().microsecond}.xlsx"


def get_or_create_excel(core_app, vendor, order_items, request_note: str, order_date: str) -> Path:
    """같은 발주 내용이면 기존 엑셀 파일을 재사용하고, 없을 때만 생성합니다."""
    cleanup_output_files(core_app)
    fingerprint = export_fingerprint(vendor, order_items, request_note, order_date, "excel")
    cache = _load_cache(core_app)
    cached = cache.get("files", {}).get(fingerprint)
    if cached:
        cached_path = Path(str(cached.get("path", "")))
        if cached_path.exists():
            return cached_path

    created_path = Path(core_app.create_excel(vendor, order_items, request_note, order_date))
    target_path = _target_excel_path(core_app, vendor, order_date)
    try:
        created_path.replace(target_path)
    except OSError:
        target_path = created_path

    cache.setdefault("files", {})[fingerprint] = {
        "kind": "excel",
        "path": str(target_path),
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    _save_cache(core_app, cache)
    return target_path
