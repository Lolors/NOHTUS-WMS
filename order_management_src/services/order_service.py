"""발주 작성, 임시저장, 발주서 관리 서비스."""
from __future__ import annotations

from typing import Callable


class OrderService:
    """발주 업무만 담당하며 기초정보 저장 기능은 포함하지 않습니다."""

    def __init__(self, core_app, draft_repo, order_repo):
        self.core_app = core_app
        self.draft_repo = draft_repo
        self.order_repo = order_repo
        self._invalidate: Callable[[], None] = lambda: None

    def set_cache_invalidator(self, callback: Callable[[], None]) -> None:
        self._invalidate = callback

    def load_all(self):
        drafts, draft_items = self.draft_repo.load_all()
        orders, order_items = self.order_repo.load_all()
        return drafts, draft_items, orders, order_items

    def save_order(self, vendor_name, request_note, items):
        editing_order_id = str(
            self.core_app.st.session_state.get("order_management_editing_order_id", "") or ""
        ).strip()
        if editing_order_id:
            order_id = self.order_repo.update(
                editing_order_id, vendor_name, request_note, items
            )
            self.core_app.st.session_state.pop("order_management_editing_order_id", None)
        else:
            order_id = self.order_repo.save(vendor_name, request_note, items)
        self._invalidate()
        return order_id

    def delete_order(self, order_id) -> None:
        self.order_repo.delete(order_id)
        self._invalidate()

    def save_draft(self, vendor_name, request_note, items):
        draft_id = self.draft_repo.save(vendor_name, request_note, items)
        self._invalidate()
        return draft_id

    def delete_draft(self, draft_id) -> None:
        self.draft_repo.delete(draft_id)
        self._invalidate()
