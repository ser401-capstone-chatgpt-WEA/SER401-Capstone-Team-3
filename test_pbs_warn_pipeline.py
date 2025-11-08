"""
Test script for PBS WARN API pipeline.
Simulates alert data fetch, runs change tracking, and asserts expected results.
"""
import json
import os
from alert_compare import get_alert_differences, save_alert_change_summary_to_file

TEST_DATA_DIRECTORY = "test_data"
FAKE_ALERTS_PATH = os.path.join(TEST_DATA_DIRECTORY, "pbs_warn_alerts_FAKE.json")
PREVIOUS_ALERTS_PATH = os.path.join(TEST_DATA_DIRECTORY, "prev_alerts.json")
CURRENT_ALERTS_PATH = os.path.join(TEST_DATA_DIRECTORY, "current_alerts.json")
DIFF_SUMMARY_PATH = os.path.join(TEST_DATA_DIRECTORY, "diff_summary_test.json")

def prepare_simulated_alert_data():
    # Ensure test_data directory exists
    os.makedirs(TEST_DATA_DIRECTORY, exist_ok=True)
    # Copy fake alerts to previous and current for simulation
    with open(FAKE_ALERTS_PATH, "r") as fake_alerts_file:
        fake_alerts = json.load(fake_alerts_file)
    # Simulate previous alerts (first alert only)
    with open(PREVIOUS_ALERTS_PATH, "w") as previous_file:
        json.dump([fake_alerts[0]], previous_file)
    # Simulate current alerts (both alerts)
    with open(CURRENT_ALERTS_PATH, "w") as current_file:
        json.dump(fake_alerts, current_file)

def test_new_alert_detection():
    os.makedirs(TEST_DATA_DIRECTORY, exist_ok=True)
    previous_alerts = [
        {
            "event": "Local Area Emergency",
            "title": "Local Area Emergency",
            "sender": "MI_Iosco_County_Emergency_Management",
            "severity": "Severe",
            "urgency": "Immediate",
            "certainty": "Observed",
            "status": "Actual",
            "cap_identifier": "17625290450001391722060",
            "message": "Police activity near 22400 Cabin Branch Ave, Clarksburg. Residents should shelter-in-place.",
            "expires": "2025-11-08T05:24:05+00:00"
        }
    ]
    current_alerts = previous_alerts + [
        {
            "event": "Health Warning",
            "title": "Health Warning",
            "sender": "MI_Iosco_County_Emergency_Management",
            "severity": "Moderate",
            "urgency": "Expected",
            "certainty": "Likely",
            "status": "Actual",
            "cap_identifier": "17625290450001391722061",
            "message": "Air quality advisory issued for the area.",
            "expires": "2025-11-08T10:00:00+00:00"
        }
    ]
    diff_summary = get_alert_differences(previous_alerts, current_alerts)
    save_alert_change_summary_to_file(diff_summary, os.path.join(TEST_DATA_DIRECTORY, "diff_summary_new_alert.json"))
    print("[new_alert_detection] Saved diff summary to diff_summary_new_alert.json")
    assert len(diff_summary["new"]) == 1, "Should detect 1 new alert"
    assert len(diff_summary["updated"]) == 0, "Should detect 0 updated alerts"
    assert len(diff_summary["cleared"]) == 0, "Should detect 0 cleared alerts"

def test_updated_alert_detection():
    os.makedirs(TEST_DATA_DIRECTORY, exist_ok=True)
    previous_alert = {
        "event": "Local Area Emergency",
        "title": "Local Area Emergency",
        "sender": "MI_Iosco_County_Emergency_Management",
        "severity": "Severe",
        "urgency": "Immediate",
        "certainty": "Observed",
        "status": "Actual",
        "cap_identifier": "17625290450001391722060",
        "message": "Police activity near 22400 Cabin Branch Ave, Clarksburg. Residents should shelter-in-place.",
        "expires": "2025-11-08T05:24:05+00:00"
    }
    updated_alert = previous_alert.copy()
    updated_alert["message"] = "Police activity resolved. Area is now safe."
    previous_alerts = [previous_alert]
    current_alerts = [updated_alert]
    diff_summary = get_alert_differences(previous_alerts, current_alerts)
    save_alert_change_summary_to_file(diff_summary, os.path.join(TEST_DATA_DIRECTORY, "diff_summary_updated_alert.json"))
    print("[updated_alert_detection] Saved diff summary to diff_summary_updated_alert.json")
    assert len(diff_summary["new"]) == 0, "Should detect 0 new alerts"
    assert len(diff_summary["updated"]) == 1, "Should detect 1 updated alert"
    assert len(diff_summary["cleared"]) == 0, "Should detect 0 cleared alerts"

def test_cleared_alert_detection():
    os.makedirs(TEST_DATA_DIRECTORY, exist_ok=True)
    previous_alert = {
        "event": "Local Area Emergency",
        "title": "Local Area Emergency",
        "sender": "MI_Iosco_County_Emergency_Management",
        "severity": "Severe",
        "urgency": "Immediate",
        "certainty": "Observed",
        "status": "Actual",
        "cap_identifier": "17625290450001391722060",
        "message": "Police activity near 22400 Cabin Branch Ave, Clarksburg. Residents should shelter-in-place.",
        "expires": "2025-11-08T05:24:05+00:00"
    }
    previous_alerts = [previous_alert]
    current_alerts = []
    diff_summary = get_alert_differences(previous_alerts, current_alerts)
    save_alert_change_summary_to_file(diff_summary, os.path.join(TEST_DATA_DIRECTORY, "diff_summary_cleared_alert.json"))
    print("[cleared_alert_detection] Saved diff summary to diff_summary_cleared_alert.json")
    assert len(diff_summary["new"]) == 0, "Should detect 0 new alerts"
    assert len(diff_summary["updated"]) == 0, "Should detect 0 updated alerts"
    assert len(diff_summary["cleared"]) == 1, "Should detect 1 cleared alert"

def test_no_change_detection():
    os.makedirs(TEST_DATA_DIRECTORY, exist_ok=True)
    alert = {
        "event": "Local Area Emergency",
        "title": "Local Area Emergency",
        "sender": "MI_Iosco_County_Emergency_Management",
        "severity": "Severe",
        "urgency": "Immediate",
        "certainty": "Observed",
        "status": "Actual",
        "cap_identifier": "17625290450001391722060",
        "message": "Police activity near 22400 Cabin Branch Ave, Clarksburg. Residents should shelter-in-place.",
        "expires": "2025-11-08T05:24:05+00:00"
    }
    previous_alerts = [alert]
    current_alerts = [alert.copy()]
    diff_summary = get_alert_differences(previous_alerts, current_alerts)
    save_alert_change_summary_to_file(diff_summary, os.path.join(TEST_DATA_DIRECTORY, "diff_summary_no_change.json"))
    print("[no_change_detection] Saved diff summary to diff_summary_no_change.json")
    assert len(diff_summary["new"]) == 0, "Should detect 0 new alerts"
    assert len(diff_summary["updated"]) == 0, "Should detect 0 updated alerts"
    assert len(diff_summary["cleared"]) == 0, "Should detect 0 cleared alerts"

def test_mixed_alert_changes():
    os.makedirs(TEST_DATA_DIRECTORY, exist_ok=True)
    previous_alert = {
        "event": "Local Area Emergency",
        "title": "Local Area Emergency",
        "sender": "MI_Iosco_County_Emergency_Management",
        "severity": "Severe",
        "urgency": "Immediate",
        "certainty": "Observed",
        "status": "Actual",
        "cap_identifier": "17625290450001391722060",
        "message": "Police activity near 22400 Cabin Branch Ave, Clarksburg. Residents should shelter-in-place.",
        "expires": "2025-11-08T05:24:05+00:00"
    }
    previous_health_alert = {
        "event": "Health Warning",
        "title": "Health Warning",
        "sender": "MI_Iosco_County_Emergency_Management",
        "severity": "Moderate",
        "urgency": "Expected",
        "certainty": "Likely",
        "status": "Actual",
        "cap_identifier": "17625290450001391722061",
        "message": "Air quality advisory issued for the area.",
        "expires": "2025-11-08T10:00:00+00:00"
    }
    current_health_alert = previous_health_alert.copy()
    current_health_alert["message"] = "Air quality advisory updated: Stay indoors until noon."
    new_flood_alert = {
        "event": "Flood Warning",
        "title": "Flood Warning",
        "sender": "MI_Iosco_County_Emergency_Management",
        "severity": "Severe",
        "urgency": "Immediate",
        "certainty": "Observed",
        "status": "Actual",
        "cap_identifier": "17625290450001391722062",
        "message": "Flooding expected in low-lying areas.",
        "expires": "2025-11-08T12:00:00+00:00"
    }
    previous_alerts = [previous_alert, previous_health_alert]
    current_alerts = [current_health_alert, new_flood_alert]
    diff_summary = get_alert_differences(previous_alerts, current_alerts)
    save_alert_change_summary_to_file(diff_summary, os.path.join(TEST_DATA_DIRECTORY, "diff_summary_mixed_alerts.json"))
    print("[mixed_alert_changes] Saved diff summary to diff_summary_mixed_alerts.json")
    assert len(diff_summary["new"]) == 1, "Should detect 1 new alert"
    assert len(diff_summary["updated"]) == 1, "Should detect 1 updated alert"
    assert len(diff_summary["cleared"]) == 1, "Should detect 1 cleared alert"

if __name__ == "__main__":
    test_new_alert_detection()
    test_updated_alert_detection()
    test_cleared_alert_detection()
    test_no_change_detection()
    test_mixed_alert_changes()