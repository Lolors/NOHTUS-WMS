import unittest

from nohtus.pages.outbound import _recent_outbound_history_html


class OutboundRecentHistoryHtmlTests(unittest.TestCase):
    def test_tooltip_is_hidden_inline_until_hover_css_applies(self):
        history = [
            {
                "order_id": 1,
                "order_date": "2026-07-20",
                "products": [{"product_name": "제품 A", "qty": 3}],
            }
        ]

        rendered = _recent_outbound_history_html("거래처 A", history)

        self.assertIn('class="out-history-tooltip" style="display:none"', rendered)
        self.assertIn("2026-07-20", rendered)
        self.assertIn("제품 A", rendered)

    def test_empty_history_tooltip_is_also_hidden_inline(self):
        rendered = _recent_outbound_history_html("거래처 A", [])

        self.assertIn('class="out-history-tooltip" style="display:none"', rendered)
        self.assertIn("이 매출처의 이전 출고지시가 없습니다.", rendered)


if __name__ == "__main__":
    unittest.main()
