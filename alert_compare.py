# import standard libraries for file and json handling
import json
from pathlib import Path


# --- reporting and printing logic ---
def print_alert_change_summary(alert_changes):
    # print a summary of new, updated, and cleared alerts
    print(f"New alerts: {len(alert_changes['new'])}")
    for new_alert in alert_changes['new']:
        print(f"  [NEW] {new_alert.get('event', new_alert.get('title', ''))} from {new_alert.get('sender', '')}")
    print(f"Updated alerts: {len(alert_changes['updated'])}")
    for updated_alert in alert_changes['updated']:
        previous_alert = updated_alert['old']
        current_alert = updated_alert['new']
        print(f"  [UPDATED] {current_alert.get('event', current_alert.get('title', ''))} from {current_alert.get('sender', '')}")
        changed_fields = updated_alert.get('changed_fields', [])
        if changed_fields:
            print(f"    Changed fields: {', '.join(changed_fields)}")
    print(f"Cleared alerts: {len(alert_changes['cleared'])}")
    for cleared_alert in alert_changes['cleared']:
        print(f"  [CLEARED] {cleared_alert.get('event', cleared_alert.get('title', ''))} from {cleared_alert.get('sender', '')}")

def compare_and_report_alerts(output_folder, current_alerts, diff_output_path=None):
    """
    Loads the latest previous alert JSON from output_folder, compares to current_alerts, and prints the change summary.
    Optionally saves the diff summary to a file.
    """
    previous_alerts = load_previous_alerts_from_folder(output_folder)
    if previous_alerts:
        print("\n--- Comparing to previous alerts ---")
        alert_changes = get_alert_changes(previous_alerts, current_alerts)
        print_alert_change_summary(alert_changes)
        if diff_output_path:
            save_alert_change_summary(alert_changes, diff_output_path)
    else:
        print("No previous alert file found for comparison.")


# --- alert comparison logic ---
def get_alert_changes(previous_alerts, current_alerts):
    """
    Compare two lists of alert dicts and classify alerts as new, updated, or cleared.
    Alerts are matched by event/title and sender.
    """
    def get_alert_identity(alert):
        event = alert.get('event', '').strip()
        title = alert.get('title', '').strip()
        sender = alert.get('sender', '').strip()
        return (event or title, sender)

    previous_alert_map = {get_alert_identity(alert): alert for alert in previous_alerts}
    current_alert_map = {get_alert_identity(alert): alert for alert in current_alerts}

    new_alerts = []      # alerts present in current, not in previous
    updated_alerts = []  # alerts present in both, but with changed fields
    cleared_alerts = []  # alerts present in previous, not in current

    fields_to_compare = [
        'event', 'title', 'message', 'sender', 'expires', 'severity', 'urgency', 'certainty', 'status', 'cap_identifier', 'category', 'is_cancelled', 'is_out_of_date'
    ]

    for identity, current_alert in current_alert_map.items():
        if identity not in previous_alert_map:
            new_alerts.append(current_alert)
        else:
            previous_alert = previous_alert_map[identity]
            changed_fields = [field for field in fields_to_compare if current_alert.get(field) != previous_alert.get(field)]
            if changed_fields:
                updated_alerts.append({'old': previous_alert, 'new': current_alert, 'changed_fields': changed_fields})

    for identity, previous_alert in previous_alert_map.items():
        if identity not in current_alert_map:
            cleared_alerts.append(previous_alert)

    return {'new': new_alerts, 'updated': updated_alerts, 'cleared': cleared_alerts}

def load_previous_alerts_from_folder(output_folder):
    """
    Find and load the second most recent alert JSON file from the output folder.
    Returns a list of alert dicts, or just [] if none found.
    """
    output_folder = Path(output_folder)
    json_files = sorted(output_folder.glob("pbs_warn_alerts_*.json"), reverse=True)
    if len(json_files) < 2:
        return []
    file_mode_read = "r"
    for alert_file in json_files[1:]:
        try:
            with open(alert_file, file_mode_read, encoding="utf-8") as file_handle:
                data = json.load(file_handle)
                if isinstance(data, dict) and 'alerts' in data:
                    return data['alerts']
                elif isinstance(data, list):
                    return data
        except Exception:
            continue
    return []

def save_alert_change_summary(alert_changes, output_path):
    """
    Save the alert change summary as a JSON file.
    """
    file_mode_write = "w"
    with open(output_path, file_mode_write, encoding="utf-8") as file_handle:
        json.dump(alert_changes, file_handle, ensure_ascii=False, indent=2)