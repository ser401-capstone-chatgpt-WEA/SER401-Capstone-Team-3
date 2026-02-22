import json
import sys
import argparse
import os
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

def normalize_file(input_path: str, output_path: str) -> None:
    """Normalize a single JSON file."""
    with open(input_path, "r", encoding="utf-8") as in_f:
        raw_data = json.load(in_f)

    cleaned_data = normalize_events(raw_data)

    with open(output_path, "w", encoding="utf-8") as out_f:
        json.dump(cleaned_data, out_f, indent=2)
        out_f.write("\n")

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Normalize PBS Warn alert data (file or folder) into a GPT-readable JSON format."
    )
    parser.add_argument(
        "input",
        help="Path to input JSON file OR folder containing JSON files.",
    )
    parser.add_argument(
        "-o",
        "--output",
        help=(
            "Output path. If input is a file: output JSON file path. "
            "If input is a folder: output folder path. "
            "If omitted, outputs go next to the input with '_cleaned' added to filenames."
        ),
    )
    return parser

def process_path(input_path: str, output_path: Optional[str]) -> None:
    """Handle either a single file or a folder of files."""
    if os.path.isdir(input_path):
        # Folder mode
        input_dir = input_path
        if output_path:
            output_dir = output_path
            os.makedirs(output_dir, exist_ok=True)
        else:
            output_dir = input_dir

        count = 0
        for name in os.listdir(input_dir):
            if not name.lower().endswith(".json"):
                continue
            in_file = os.path.join(input_dir, name)
            base, ext = os.path.splitext(name)
            out_name = f"{base}_cleaned.json"
            out_file = os.path.join(output_dir, out_name)

            normalize_file(in_file, out_file)
            count += 1

        print(f"Processed {count} JSON file(s) from folder: {input_dir}")

    else:
        # Single file mode
        if not os.path.isfile(input_path):
            raise FileNotFoundError(f"Input file not found: {input_path}")

        if output_path:
            out_file = output_path
        else:
            dir_name, file_name = os.path.split(input_path)
            base, ext = os.path.splitext(file_name)
            out_file = os.path.join(dir_name, f"{base}_cleaned.json")

        normalize_file(input_path, out_file)
        print(f"Processed 1 file -> {out_file}")

def main():
    parser = build_arg_parser()
    args = parser.parse_args()

    try:
        process_path(args.input, args.output)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
