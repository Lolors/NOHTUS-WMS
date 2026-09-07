"""통합 수정 업무 서비스."""
from __future__ import annotations

from typing import Callable

from repositories import correction_repository


class CorrectionService:
    def __init__(self, data_dir):
        self.data_dir = data_dir
        self._invalidate: Callable[[], None] = lambda: None

    def set_cache_invalidator(self, callback: Callable[[], None]) -> None:
        self._invalidate = callback

    def save_bundle(self, order_id, header, order_items, statements, statement_items) -> None:
        correction_repository.save_bundle(
            self.data_dir, order_id, header, order_items, statements, statement_items
        )
        self._invalidate()
