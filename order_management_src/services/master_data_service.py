"""거래처, 제품, 별칭처럼 독립적으로 관리하는 기초정보 서비스."""
from __future__ import annotations

from typing import Callable


class MasterDataService:
    """발주 업무 규칙과 무관한 기초정보 읽기·쓰기를 담당합니다."""

    def __init__(self, catalog_repo):
        self.catalog_repo = catalog_repo
        self._invalidate: Callable[[], None] = lambda: None

    def set_cache_invalidator(self, callback: Callable[[], None]) -> None:
        self._invalidate = callback

    def load_all(self):
        vendors = self.catalog_repo.load_vendors()
        products = self.catalog_repo.load_products()
        products["정식제품명"] = products["제품명"]
        products["단위"] = products["포장단위"]
        aliases = self.catalog_repo.load_aliases()
        return vendors, products, aliases

    def read_products(self, product_schema):
        return product_schema.products_for_app(self.catalog_repo.load_products())

    def save_products(self, products) -> None:
        self.catalog_repo.save_products(products)
        self._invalidate()

    def save_aliases(self, aliases) -> None:
        self.catalog_repo.save_aliases(aliases)
        self._invalidate()

    def save_vendors(self, vendors) -> None:
        self.catalog_repo.save_vendors(vendors)
        self._invalidate()
