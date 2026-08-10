from nohtus.export_app.services import order_save_guard


def test_reset_intake_order_editor_state_discards_draft_and_bumps_version(monkeypatch):
    state = {
        'shipment_order_draft_42': 'stale rows',
        'shipment_order_editor_version_42': 3,
        'unrelated': 'keep',
    }
    monkeypatch.setattr(order_save_guard.st, 'session_state', state)

    order_save_guard.reset_intake_order_editor_state(42)

    assert 'shipment_order_draft_42' not in state
    assert state['shipment_order_editor_version_42'] == 4
    assert state['unrelated'] == 'keep'


def test_reset_intake_order_editor_state_initializes_version(monkeypatch):
    state = {'shipment_order_draft_7': 'stale rows'}
    monkeypatch.setattr(order_save_guard.st, 'session_state', state)

    order_save_guard.reset_intake_order_editor_state(7)

    assert state == {'shipment_order_editor_version_7': 1}
