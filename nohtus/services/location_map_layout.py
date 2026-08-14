"""JSON-backed layout storage for the editable warehouse location map."""
from __future__ import annotations

import json
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_LAYOUT_PATH = _PROJECT_ROOT / "data" / "location_map_layout.json"


def layout_path() -> Path:
    return _LAYOUT_PATH


def load_location_map_layout() -> dict:
    if not _LAYOUT_PATH.exists():
        return {"version": 1, "canvas": {"width": 1280, "height": 900, "grid": 10}, "items": []}
    try:
        data = json.loads(_LAYOUT_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "canvas": {"width": 1280, "height": 900, "grid": 10}, "items": []}
    if not isinstance(data, dict):
        return {"version": 1, "canvas": {"width": 1280, "height": 900, "grid": 10}, "items": []}
    data.setdefault("version", 1)
    data.setdefault("canvas", {"width": 1280, "height": 900, "grid": 10})
    data.setdefault("items", [])
    return data


def save_location_map_layout(layout: dict) -> None:
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
        })

    payload = {
        "version": int(layout.get("version") or 1),
        "canvas": {"width": width, "height": height, "grid": grid},
        "items": cleaned,
    }
    _LAYOUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _LAYOUT_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(_LAYOUT_PATH)
