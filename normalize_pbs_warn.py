import json
from datetime import datetime

def parse_severity(value: str) -> str:
    """Map severity string or color to normalized level."""
    value = (value or "").strip().lower()
    if value in ["extreme", "severe"]:
        return "Severe"
    elif value in ["moderate", "minor", "advisory"]:
        return "Advisory"
    else:
        return "Unknown"

def detect_status(msg_type: str, texts: list) -> str:
    """Determine if an alert is Active or Lifted."""
    if msg_type and msg_type.lower() == "cancel":
        return "Lifted"

    # fallback check
    for text in texts or []:
        if "lifted" in text.get("value", "").lower():
            return "Lifted"
    return "Active"

def normalize_sender(sender: str) -> str:
    """Clean and normalize sender agency names."""
    sender = (sender or "").replace("_", " ").replace(",", " ").strip()
    sender = sender.replace("EM.", "Emergency Management")
    return sender

def parse_datetime(dt_str: str) -> str:
    """Convert input datetime (ISO or legacy) to ISO 8601 UTC."""
    if not dt_str:
        return None
    try:
        # Handles ISO formats like 2025-11-04T03:33:17+00:00
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return None

def extract_description(texts: list) -> str:
    """Choose the most descriptive text entry available."""
    if not texts:
        return ""
    # Prefer instruction, description, or long text fields
    for key in ["cap_instruction", "cap_description", "cmac_long_text"]:
        for t in texts:
            if t.get("type") == key and t.get("value"):
                return t["value"].strip()
    # fallback to any available text
    for t in texts:
        if t.get("value"):
            return t["value"].strip()
    return ""

def normalize_events(raw_data):
    """Convert PBS Warn API response to GPT-readable general format."""
    alerts = raw_data.get("alerts", [])
    normalized = []

    for alert in alerts:
        event = {
            "event_type": alert.get("event", "Unknown Event"),
            "status": detect_status(alert.get("msg_type", ""), alert.get("texts")),
            "description": extract_description(alert.get("texts")),
            "sender": normalize_sender(alert.get("sender", "")),
            "severity": parse_severity(alert.get("severity", "")),
            "issued": parse_datetime(alert.get("sent")),
            "expires": parse_datetime(alert.get("expires"))
        }
        normalized.append(event)

    return normalized

if __name__ == "__main__":
    # Example: replace with your actual JSON file path
    with open("pbs_warn_raw.json", "r") as f:
        raw_data = json.load(f)

    cleaned_data = normalize_events(raw_data)

    with open("pbs_warn_cleaned.json", "w") as f:
        json.dump(cleaned_data, f, indent=2)

    print("Conversion complete. Output saved to pbs_warn_cleaned.json")
