from __future__ import annotations

from contextlib import contextmanager
import os
import time


_ENABLED = os.getenv('EXPORT_PERF_DEBUG', '').strip().casefold() in {'1', 'true', 'yes', 'on'}
_SLOW_MS = float(os.getenv('EXPORT_PERF_SLOW_MS', '50') or 50)


def enabled() -> bool:
    return _ENABLED


@contextmanager
def measure(label: str, *, slow_ms: float | None = None):
    """Print elapsed time only when performance debugging is enabled."""
    if not _ENABLED:
        yield
        return
    started = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (time.perf_counter() - started) * 1000
        threshold = _SLOW_MS if slow_ms is None else slow_ms
        if elapsed_ms >= threshold:
            print(f'[PERF] {label}: {elapsed_ms:.1f} ms')
