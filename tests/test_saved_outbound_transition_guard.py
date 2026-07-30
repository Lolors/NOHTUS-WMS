import unittest

from nohtus.pages.saved_outbound_date_fix import SAVED_OUTBOUND_TRANSITION_GUARD


class SavedOutboundTransitionGuardTests(unittest.TestCase):
    def test_guard_hides_stale_recent_history_and_customer_detail(self):
        self.assertIn(".saved-outbound-transition-marker", SAVED_OUTBOUND_TRANSITION_GUARD)
        self.assertIn(".out-history-wrap", SAVED_OUTBOUND_TRANSITION_GUARD)
        self.assertIn(".out-customer-detail-marker", SAVED_OUTBOUND_TRANSITION_GUARD)
        self.assertEqual(SAVED_OUTBOUND_TRANSITION_GUARD.count("display: none !important"), 2)


if __name__ == "__main__":
    unittest.main()
