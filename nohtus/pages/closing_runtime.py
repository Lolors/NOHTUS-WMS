"""Backward-compatible closing page runtime wrapper.

The active closing page now lives in nohtus.pages.closing.
This module remains temporarily so older imports do not break.
"""

from nohtus.pages.closing import page_closing


__all__ = ["page_closing"]
