# import standard libraries for file and json handling
import json
from pathlib import Path


# --- alert comparison logic ---
def compare_alerts(previous_alert_list, current_alert_list):
    # compare two lists of alert dicts and classify alerts as new, updated, or cleared
    # alerts are matched by title and sender (for now)
    def alert_identity(alert):
        # use title+sender as a composite key (adjust if needed)
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
    # find and load the most recent alert json file from the output folder
    # returns a list of alert dicts, or [] if none found
    output_folder = Path(output_folder)
    json_files = sorted(output_folder.glob("pbs_warn_alerts_*.json"), reverse=True)
    for alert_file in json_files:
        try:
            with open(alert_file, "r", encoding="utf-8") as fh:
                # try to load and return the first valid json file
                return json.load(fh)
        except Exception:
            # skip files that fail to load
            continue
    # return empty list if no valid file found
    return []