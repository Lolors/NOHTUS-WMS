"""Backward-compatible product matching page runtime wrapper.

The active product matching page now lives in nohtus.pages.product_matching.
This module remains temporarily so older imports do not break.
"""

from nohtus.pages.product_matching import page_product_matching


__all__ = ["page_product_matching"]
