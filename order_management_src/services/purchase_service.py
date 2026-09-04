"""입고, 거래명세서, 월별 매입 관리 서비스."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from repositories import purchase_repository


class PurchaseService:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self._invalidate: Callable[[], None] = lambda: None

    def set_cache_invalidator(self, callback: Callable[[], None]) -> None:
        self._invalidate = callback

    def load_all(self):
        return purchase_repository.load_all(self.data_dir)

    def save_table(self, path, frame, _columns=None) -> None:
        filename = Path(path).name
        writers = {
            "purchase_statements.csv": purchase_repository.replace_statements,
            "purchase_statement_items.csv": purchase_repository.replace_statement_items,
            "price_history.csv": purchase_repository.replace_price_history,
            "purchase_month_close.csv": purchase_repository.replace_monthly_closes,
        }
        writer = writers.get(filename)
        if writer is None:
            raise ValueError(f"지원하지 않는 매입 데이터 저장 대상입니다: {filename}")
        writer(self.data_dir, frame)
        self._invalidate()
