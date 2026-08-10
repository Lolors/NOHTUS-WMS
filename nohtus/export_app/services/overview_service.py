from __future__ import annotations

import json
from uuid import uuid4

from nohtus.export_app import db
from nohtus.export_app.utils.dates import now_text


TASK_SETTING_KEY = 'overview_task_notes'


def _load() -> list[dict]:
    raw = db.get_setting(TASK_SETTING_KEY, '[]')
    try:
        values = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(values, list):
        return []

    tasks: list[dict] = []
    for value in values:
        if not isinstance(value, dict):
            continue
        text = str(value.get('text', '') or '').strip()
        if not text:
            continue
        tasks.append({
            'id': str(value.get('id') or uuid4().hex),
            'text': text,
            'done': bool(value.get('done', False)),
            'created_at': str(value.get('created_at') or ''),
        })
    return tasks


def _save(tasks: list[dict]) -> None:
    db.set_setting(TASK_SETTING_KEY, json.dumps(tasks, ensure_ascii=False))


def list_tasks() -> list[dict]:
    return sorted(
        _load(),
        key=lambda task: (bool(task['done']), str(task.get('created_at', ''))),
    )


def add_task(text: str) -> None:
    clean_text = str(text or '').strip()
    if not clean_text:
        raise ValueError('메모할 내용을 입력하세요.')
    tasks = _load()
    tasks.append({
        'id': uuid4().hex,
        'text': clean_text,
        'done': False,
        'created_at': now_text(),
    })
    _save(tasks)


def set_done(task_id: str, done: bool) -> None:
    tasks = _load()
    for task in tasks:
        if task['id'] == task_id:
            task['done'] = bool(done)
            break
    _save(tasks)


def delete_task(task_id: str) -> None:
    _save([task for task in _load() if task['id'] != task_id])
