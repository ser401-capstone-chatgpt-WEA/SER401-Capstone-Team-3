
from alert_compare import compare_alerts, load_latest_alert_json, print_alert_diff, compare_and_report_alerts
from pbs_warn_scraper import (
    fetch_pbs_warn_homepage,
    open_alert_menu,
    extract_alerts_from_card_list,
    fetch_pbs_warn_alert_list,
    fetch_pbs_warn_alerts_with_details
)
from datetime import datetime, timezone
from pathlib import Path
import json
# Add missing import for logging
import logging
# import utility functions
from pbs_warn_utils import setup_logging, check_for_alert_keywords, format_timestamp_for_filename, save_keywords_to_csv

# setup basic logging to track progress and errors
setup_logging()

def test_fetch_homepage():
    logging.info("Starting PBS WARN scraper (in-progress)")
    html, timestamp = fetch_pbs_warn_homepage()
    keywords_found = check_for_alert_keywords(html)

    # stub for real-time polling
    # while True:
    #     html = fetch_pbs_warn_homepage()
    #     keywords_found = check_for_alert_keywords(html)
    #     # future: save structured alerts to csv/json
    #     time.sleep(120)  # poll every 2 minutes

    # format yyyy-mm-dd_hhmmss for filenames
    formatted_timestamp = format_timestamp_for_filename(timestamp)
    # save keyword results for review using utility
    save_keywords_to_csv(keywords_found, formatted_timestamp)

    if timestamp:
        # todo: future save structured alerts to csv/json
        pass

def test_fetch_alert_list():
    logging.info("Starting PBS WARN alert list fetch")
    html = fetch_pbs_warn_alert_list()
    print(f"Extracted {len(html)} alerts from PBS WARN.")
    for alert in html:
        print(f"- Title: {alert['title']}")
        print(f"  Message: {alert['message']}")
        print(f"  Sender: {alert['sender']}")
        print(f"  Expires: {alert['expires']}")
        print(f"  Severity Color: {alert['severity_color']}")
        print()

    # Save detailed output with metadata and 'alerts' key only
    try:
        formatted_ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%SZ")
        output_folder = Path("./pbs_warn_outputs")
        output_folder.mkdir(parents=True, exist_ok=True)
        out_file = output_folder / f"pbs_warn_alerts_{formatted_ts}.json"
        file_payload = {
            "scrape_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "alerts": html
        }
        with open(out_file, "w", encoding="utf-8") as fh:
            json.dump(file_payload, fh, ensure_ascii=False, indent=2)
        logging.info(f"Saved {len(html)} alerts to {out_file}")
        print(f"Saved {len(html)} alerts to {out_file}")
    except Exception as e:
        logging.error(f"Failed saving alerts JSON: {e}")
        print(f"Failed saving alerts JSON: {e}")

    # compare with previous alerts if available (using alert_compare helpers)
    compare_and_report_alerts("./pbs_warn_outputs", html)

def test_fetch_alerts_with_details():
    logging.info("Starting PBS WARN detailed alert fetch")
    alerts = fetch_pbs_warn_alerts_with_details()
    print(f"Extracted {len(alerts)} detailed alerts from PBS WARN.")
    for alert in alerts:
        print(f"- Title: {alert['title']}")
        print(f"  Message: {alert['message']}")
        print(f"  Sender: {alert['sender']}")
        print(f"  Expires: {alert['expires']}")
        print(f"  Sent: {alert['sent']}")
        print(f"  Area: {alert['area']}")
        print(f"  ID: {alert['id']}")
        print(f"  WEA 360CH: {alert['wea360']}")
        print(f"  WEA 90CH: {alert['wea90']}")
        print(f"  Severity Color: {alert['severity_color']}")
        print(f"  History Items: {len(alert['history'])} entries")
        print()

def main():
    """
    Main function to demonstrate scraping and keyword analysis.
    IN-PROGRESS: Roadmap for next steps:
    1. Identify specific DOM selectors for alert details (title, desc, location, expires).
    2. Extract data (JSON) for ingestion.
    3. Implement real-time polling.
    4. Add error retry logic and rate limiting.
    """

    # homepage fetch with keyword scan and "updated mm/dd/yyyy hh:mm" timestamp extraction test
    # test_fetch_homepage()

    # alert list extraction with detailed fields and saving to json
    test_fetch_alerts_with_details()

if __name__ == "__main__":
    main()