"""JSON-backed layout storage for the editable warehouse location map."""
from __future__ import annotations

import json
from pathlib import Path
import re

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_LAYOUT_PATH = _PROJECT_ROOT / "data" / "location_map_layout.json"
_DRAFT_PATH = _PROJECT_ROOT / "data" / "location_map_layout.draft.json"


def layout_path() -> Path:
    return _LAYOUT_PATH


def _load_layout(path: Path) -> dict:
    if not path.exists():
        return {"version": 1, "canvas": {"width": 1280, "height": 900, "grid": 10}, "items": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "canvas": {"width": 1280, "height": 900, "grid": 10}, "items": []}
    if not isinstance(data, dict):
        return {"version": 1, "canvas": {"width": 1280, "height": 900, "grid": 10}, "items": []}
    data.setdefault("version", 1)
    data.setdefault("canvas", {"width": 1280, "height": 900, "grid": 10})
    data.setdefault("items", [])
    return data


def load_location_map_layout() -> dict:
    return _load_layout(_LAYOUT_PATH)


def load_location_map_draft() -> dict | None:
    return _load_layout(_DRAFT_PATH) if _DRAFT_PATH.exists() else None


def _clean_layout(layout: dict) -> dict:
    if not isinstance(layout, dict):
        raise ValueError("레이아웃 데이터 형식이 올바르지 않습니다.")
    canvas = layout.get("canvas") or {}
    items = layout.get("items") or []
    width = int(canvas.get("width") or 1280)
    height = int(canvas.get("height") or 900)
    grid = max(1, int(canvas.get("grid") or 10))
    if width < 400 or height < 300:
        raise ValueError("캔버스 크기가 너무 작습니다.")

    cleaned = []
    seen = set()
    for raw in items:
        if not isinstance(raw, dict):
            continue
        code = str(raw.get("code") or "").strip()
        if not code or code in seen:
            continue
        seen.add(code)
        fill_type = str(raw.get("fill_type") or "company").strip()
        if fill_type not in {"company", "solid", "hatched", "none"}:
            fill_type = "company"
        fill_color = str(raw.get("fill_color") or "#ffffff").strip()
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", fill_color):
            fill_color = "#ffffff"
        cleaned.append({
            "code": code,
            "label": str(raw.get("label") or code).strip() or code,
            "x": max(0, int(raw.get("x") or 0)),
            "y": max(0, int(raw.get("y") or 0)),
            "width": max(36, int(raw.get("width") or 80)),
            "height": max(30, int(raw.get("height") or 56)),
            "rotation": int(raw.get("rotation") or 0),
            "company": str(raw.get("company") or "기타").strip() or "기타",
            "kind": str(raw.get("kind") or "location").strip() or "location",
            "note": str(raw.get("note") or "").strip(),
            "group_id": str(raw.get("group_id") or "").strip(),
            "shape_type": str(raw.get("shape_type") or "").strip(),
            "stroke": str(raw.get("stroke") or "#475569").strip() or "#475569",
            "fill_type": fill_type,
            "fill_color": fill_color,
        })

    payload = {
        "version": int(layout.get("version") or 1),
        "canvas": {"width": width, "height": height, "grid": grid},
        "items": cleaned,
    }
    return payload


def _write_layout(path: Path, layout: dict) -> None:
    payload = _clean_layout(layout)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def save_location_map_layout(layout: dict) -> None:
    _write_layout(_LAYOUT_PATH, layout)


def save_location_map_draft(layout: dict) -> None:
    _write_layout(_DRAFT_PATH, layout)


def delete_location_map_draft() -> None:
    if _DRAFT_PATH.exists():
        _DRAFT_PATH.unlink()
