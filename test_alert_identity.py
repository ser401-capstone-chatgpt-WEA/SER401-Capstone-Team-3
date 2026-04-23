"""Unit tests for alert identity edge cases."""

from alert_compare import get_alert_changes

def _base_alert(**overrides):
    alert = {
        "event": "Test Event",
        "title": "Test Event",
        "sender": "Test Sender",
        "cap_identifier": "CAP-BASE",
        "message": "Base message",
        "status": "Actual",
    }
    alert.update(overrides)
    return alert


def test_identity_fallback_to_cap_identifier_when_primary_missing():
    previous_alerts = [
        _base_alert(event=None, title=None, sender=None, cap_identifier="CAP-1")
    ]
    current_alerts = [
        _base_alert(event="", title="", sender="", cap_identifier="CAP-1", message="Updated")
    ]

    diff_summary = get_alert_changes(previous_alerts, current_alerts)

    assert len(diff_summary["new"]) == 0
    assert len(diff_summary["cleared"]) == 0
    assert len(diff_summary["updated"]) == 1


def test_identity_fallback_for_missing_sender():
    previous_alerts = [
        _base_alert(event="Flood Warning", sender=None, cap_identifier="CAP-2")
    ]
    current_alerts = [
        _base_alert(event="Flood Warning", sender="", cap_identifier="CAP-2", message="Updated")
    ]

    diff_summary = get_alert_changes(previous_alerts, current_alerts)

    assert len(diff_summary["new"]) == 0
    assert len(diff_summary["cleared"]) == 0
    assert len(diff_summary["updated"]) == 1


def test_identity_distinguishes_multiple_cap_fallbacks():
    previous_alerts = [
        _base_alert(event=None, title=None, sender=None, cap_identifier="CAP-A", message="A"),
        _base_alert(event=None, title=None, sender=None, cap_identifier="CAP-B", message="B"),
    ]
    current_alerts = [
        _base_alert(event=None, title=None, sender=None, cap_identifier="CAP-A", message="A updated"),
        _base_alert(event=None, title=None, sender=None, cap_identifier="CAP-B", message="B"),
    ]

    diff_summary = get_alert_changes(previous_alerts, current_alerts)

    assert len(diff_summary["new"]) == 0
    assert len(diff_summary["cleared"]) == 0
    assert len(diff_summary["updated"]) == 1
