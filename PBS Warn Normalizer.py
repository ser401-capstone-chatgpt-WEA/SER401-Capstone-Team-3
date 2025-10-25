# untested but theoretically might work, mainly including for proof of daily work, do not use w/o testing it might fail

import json
from datetime import datetime

def parse_severity(color: str) -> str:
    """Map RGB color to severity level."""
    color_map = {
        "rgb(250, 58, 47)": "Severe",
        "rgb(250, 146, 0)": "Advisory"
    }
    return color_map.get(color, "Unknown")

def detect_status(message: str) -> str:
    """Detect if the advisory is still active or lifted."""
    msg = message.lower()
    if "lifted" in msg or "safe to use" in msg:
        return "Lifted"
    return "Active"

def normalize_sender(sender: str) -> str:
    """Clean and normalize sender agency names."""
    sender = sender.replace("EM.", "Emergency Management")
    sender = sender.replace("_", " ").replace(",", " ").strip()
    return sender

def parse_datetime(dt_str: str) -> str:
    """Convert input datetime to ISO 8601 UTC format."""
    try:
        dt = datetime.strptime(dt_str, "%m/%d/%Y %H:%M:%S")
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return None

def normalize_events(raw_data):
    """Convert PBS Warn raw alerts to a GPT-readable, general-purpose format."""
    normalized = []
    for alert in raw_data:
        event = {
            "event_type": "Local Area Emergency",
            "status": detect_status(alert.get("message", "")),
            "description": alert.get("message", "").strip(),
            "sender": normalize_sender(alert.get("sender", "")),
            "severity": parse_severity(alert.get("severity_color", "")),
            "issued": parse_datetime(alert.get("expires")),
            "expires": parse_datetime(alert.get("expires"))
        }
        normalized.append(event)
    return normalized

if __name__ == "__main__":
    # Example usage: replace with your actual PBS Warn JSON file path
    with open("pbs_warn_raw.json", "r") as f:
        raw_data = json.load(f)

    cleaned_data = normalize_events(raw_data)

    with open("pbs_warn_cleaned.json", "w") as f:
        json.dump(cleaned_data, f, indent=2)

    print("Conversion complete. Output saved to pbs_warn_cleaned.json")