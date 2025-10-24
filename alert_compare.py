# import standard libraries for file and json handling
import json
from pathlib import Path


# --- reporting and printing logic ---
def print_alert_diff(alert_diff):
    # print a summary of new, updated, and cleared alerts
    print(f"new alerts: {len(alert_diff['new'])}")
    for alert in alert_diff['new']:
        print(f"  [NEW] {alert['title']} from {alert['sender']}")
    print(f"updated alerts: {len(alert_diff['updated'])}")
    for updated in alert_diff['updated']:
        print(f"  [UPDATED] {updated['new']['title']} from {updated['new']['sender']}")
    print(f"cleared alerts: {len(alert_diff['cleared'])}")
    for cleared in alert_diff['cleared']:
        print(f"  [CLEARED] {cleared['title']} from {cleared['sender']}")

def compare_and_report_alerts(output_folder, current_alert_list):
    # loads the latest previous alert json from output_folder, compares to current_alert_list, and prints the diff
    previous_alert_list = load_latest_alert_json(output_folder)  # get previous alerts if any
    if previous_alert_list:
        print("\n--- comparing to previous alerts ---")
        alert_diff = compare_alerts(previous_alert_list, current_alert_list)  # run comparison
        print_alert_diff(alert_diff)  # print results
    else:
        print("no previous alert file found for comparison.")


# --- alert comparison logic ---
def compare_alerts(previous_alert_list, current_alert_list):
    # compare two lists of alert dicts and classify alerts as new, updated, or cleared
    # alerts are matched by title and sender (for now)
    def alert_identity(alert):
        # use title+sender as a composite key
        return (alert.get('title', '').strip(), alert.get('sender', '').strip())

    # build lookup maps for previous and current alerts
    previous_alert_map = {alert_identity(alert): alert for alert in previous_alert_list}
    current_alert_map = {alert_identity(alert): alert for alert in current_alert_list}

    new_alerts = []      # alerts present in current, not in previous
    updated_alerts = []  # alerts present in both, but with changed fields
    cleared_alerts = []  # alerts present in previous, not in current

    # find new and updated alerts
    for identity, current_alert in current_alert_map.items():
        if identity not in previous_alert_map:
            # alert is new (not seen before)
            new_alerts.append(current_alert)
        else:
            previous_alert = previous_alert_map[identity]
            # compare relevant fields to detect updates
            fields = ['title', 'message', 'sender', 'expires', 'severity_color']
            changed = any(current_alert.get(field) != previous_alert.get(field) for field in fields)
            if changed:
                # alert exists but has changed details
                updated_alerts.append({'old': previous_alert, 'new': current_alert})

    # find cleared alerts (present in previous, missing in current)
    for identity, previous_alert in previous_alert_map.items():
        if identity not in current_alert_map:
            cleared_alerts.append(previous_alert)

    # return a dict with lists of new, updated, and cleared alerts
    return {'new': new_alerts, 'updated': updated_alerts, 'cleared': cleared_alerts}

def load_latest_alert_json(output_folder):
    # find and load the second most recent alert json file from the output folder
    # returns a list of alert dicts, or just [] if none found
    output_folder = Path(output_folder)
    json_files = sorted(output_folder.glob("pbs_warn_alerts_*.json"), reverse=True)
    if len(json_files) < 2:
        # not enough files to compare
        return []
    # the most recent file is assumed to be the current run, so we skip it
    for alert_file in json_files[1:]:
        try:
            with open(alert_file, "r", encoding="utf-8") as fh:
                # try to load and return the first valid json file
                return json.load(fh)
        except Exception:
            # skip files that fail to load
            continue
    # return empty list if no valid file found
    return []