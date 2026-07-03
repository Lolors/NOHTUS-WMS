"""Outbound order save/update wrapper services.

The heavy DB save/update implementation still lives in app.py for now.
This wrapper removes direct app.py imports from page modules first, then the
implementation can be migrated here in smaller safe commits.
"""

from __future__ import annotations


def save_outbound_order(cart, title="", memo=""):
    from app import save_outbound_order as _save_outbound_order
    return _save_outbound_order(cart, title, memo)


def update_outbound_order(order_id, title_or_cart, maybe_cart=None):
    from app import update_outbound_order as _update_outbound_order
    if maybe_cart is None:
        return _update_outbound_order(order_id, title_or_cart)
    return _update_outbound_order(order_id, title_or_cart, maybe_cart)
