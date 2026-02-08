import json
import sys
import argparse
from datetime import datetime
from typing import Any, Dict, List, Optional

def parse_severity(value: Optional[str]) -> str:
    """Map severity string or color to normalized level."""
    value = (value or "").strip().lower()
    if value in ["extreme", "severe"]:
        return "Severe"
    elif value in ["moderate", "minor", "advisory"]:
        return "Advisory"
    else:
        return "Unknown"

def detect_status(msg_type: Optional[str], texts: Optional[List[Dict[str, Any]]]) -> str:
    """Determine if an alert is Active or Lifted."""
    if msg_type and msg_type.lower() == "cancel":
        return "Lifted"
    for text in texts or []:
        if "lifted" in (text.get("value", "") or "").lower():
            return "Lifted"
    return "Active"

def normalize_sender(sender: Optional[str]) -> str:
    """Clean and normalize sender agency names."""
    sender = (sender or "").replace("_", " ").replace(",", " ").strip()
    sender = sender.replace("EM.", "Emergency Management")
    return sender

def parse_datetime(dt_str: Optional[str]) -> Optional[str]:
    """Convert input datetime (ISO or legacy) to ISO 8601 UTC."""
    if not dt_str:
        return None
    try:
        # Handles ISO formats like 2025-11-04T03:33:17+00:00 and 2025-11-04T03:33:17Z
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return None

def extract_description(texts: Optional[List[Dict[str, Any]]]) -> str:
    """Choose the most descriptive text entry available."""
    if not texts:
        return ""
    preferred_types = ["cap_instruction", "cap_description", "cmac_long_text"]
    for key in preferred_types:
        for t in texts:
            if t.get("type") == key and t.get("value"):
                return t["value"].strip()
    for t in texts:
        if t.get("value"):
            return t["value"].strip()
    return ""

def normalize_events(raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Convert PBS Warn API response to a GPT-readable general format.

    Expected input format:
        {
          "alerts": [ ... ],
          "pages": { ... },
          "timestamp": "..."
        }

    Returns:
        List of normalized alert dictionaries.
    """
    alerts = raw_data.get("alerts", [])
    normalized: List[Dict[str, Any]] = []

    for alert in alerts:
        event = {
            "event_type": alert.get("event", "Unknown Event"),
            "status": detect_status(alert.get("msg_type", ""), alert.get("texts")),
            "description": extract_description(alert.get("texts")),
            "sender": normalize_sender(alert.get("sender", "")),
            "severity": parse_severity(alert.get("severity", "")),
            "issued": parse_datetime(alert.get("sent")),
            "expires": parse_datetime(alert.get("expires")),
        }
        normalized.append(event)
    return normalized

def normalize_file(input_stream, output_stream) -> None:
    """
    Read raw JSON from input_stream, normalize it, and write JSON to output_stream.
    This makes it easy to call from other code or from the CLI.
    """
    raw_data = json.load(input_stream)
    cleaned_data = normalize_events(raw_data)
    json.dump(cleaned_data, output_stream, indent=2)
    output_stream.write("\n")

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Normalize PBS Warn alert data into a GPT-readable JSON format."
    )
    parser.add_argument(
        "input",
        help="Path to input JSON file",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="pbs_warn_cleaned.json",
        help="Path to output JSON file (default: pbs_warn_cleaned.json)",
    )
    return parser

def open_input(path: str):
    return open(path, "r", encoding="utf-8")

def open_output(path: str):
    return open(path, "w", encoding="utf-8")

def main():
    parser = build_arg_parser()
    args = parser.parse_args()
    try:
        with open_input(args.input) as in_f, open_output(args.output) as out_f:
            normalize_file(in_f, out_f)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
