"""제품·별칭·거래처 데이터 접근 Repository."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

import db_store


class CatalogRepository:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)

    def load_products(self) -> pd.DataFrame:
        return db_store.load_products(self.data_dir)

    def save_products(self, products: pd.DataFrame) -> None:
        db_store.save_products(self.data_dir, products)

    def load_aliases(self) -> pd.DataFrame:
        return db_store.load_aliases(self.data_dir)

    def save_aliases(self, aliases: pd.DataFrame) -> None:
        db_store.save_aliases(self.data_dir, aliases)

    def load_vendors(self) -> pd.DataFrame:
        return db_store.load_vendors(self.data_dir)

    def save_vendors(self, vendors: pd.DataFrame) -> None:
        db_store.save_vendors(self.data_dir, vendors)
