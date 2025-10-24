import logging
from datetime import datetime
import re
import pandas as pd
from pathlib import Path

# setup basic logging to track progress and errors
def setup_logging():
    logging.basicConfig(filename='pbs_warn_scraper.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# scan html for emergency alert keywords to confirm relevant content
def check_for_alert_keywords(html):
    if not html:
        logging.warning("No HTML content to check.")
        print("No HTML content to check.")
        return []
    keywords = [
        "alert", "warning", "evacuation", "AMBER", "civil emergency",
        "public safety", "evacuation order", "shelter in place",
        "disaster", "emergency", "severe weather", "flood", "fire",
        "tornado", "hazard"
    ]
    found = []
    html_lower = html.lower()
    for keyword in keywords:
        count = html_lower.count(keyword.lower())
        if count > 0:
            found.append({"keyword": keyword, "count": count})
            logging.info(f"Found keyword '{keyword}' {count} times")
            print(f"Keyword '{keyword}': Found {count} times")
    return found

# timestamp string and return a safe string for filenames
def format_timestamp_for_filename(timestamp_str):
    if not timestamp_str:
        return "UNKNOWN_TIME"
    match = re.search(r"(\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2})", timestamp_str)
    if match:
        try:
            dt = datetime.strptime(match.group(1), "%m/%d/%Y %H:%M:%S")
            return dt.strftime("%Y-%m-%d_%H%M%S")
        except Exception:
            pass
    return re.sub(r"[^\w]", "_", timestamp_str)

# save keyword results for review
def save_keywords_to_csv(keywords_found, formatted_timestamp):
    output_folder = Path("./pbs_warn_outputs")
    output_folder.mkdir(parents=True, exist_ok=True)
    keywords_filename = output_folder / f"pbs_warn_keywords_{formatted_timestamp}.csv"
    if keywords_found:
        df = pd.DataFrame(keywords_found)
        df.to_csv(keywords_filename, index=False)
        logging.info(f"Saved keyword findings to {keywords_filename}")
        print(f"Saved keyword findings to {keywords_filename}")
    return keywords_filename
