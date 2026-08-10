from __future__ import annotations

from collections.abc import Callable
from typing import Any

import streamlit as st


def dialog(title: str, **kwargs: Any) -> Callable:
    """Use the stable dialog API when available, with Streamlit 1.36 fallback."""
    decorator = getattr(st, 'dialog', None)
    if decorator is None:
        decorator = st.experimental_dialog
    return decorator(title, **kwargs)
