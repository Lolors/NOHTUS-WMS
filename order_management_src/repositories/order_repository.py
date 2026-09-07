"""발주서와 발주 품목 데이터 접근 Repository."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

import db_store


class OrderRepository:
    def __init__(self, data_dir: Path, base_app):
        self.data_dir = Path(data_dir)
        self.base_app = base_app

    def load_all(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        return db_store.load_orders(self.data_dir)

    def save(self, vendor_name: str, request_note: str, items: list[dict]) -> str:
        return db_store.save_order(
            self.data_dir,
            self.base_app,
            vendor_name,
            request_note,
            items,
        )

    def update(self, order_id: str, vendor_name: str, request_note: str, items: list[dict]) -> str:
        return db_store.update_order(
            self.data_dir,
            self.base_app,
            order_id,
            vendor_name,
            request_note,
            items,
        )

    def delete(self, order_id: str) -> None:
        db_store.delete_order(self.data_dir, order_id)
