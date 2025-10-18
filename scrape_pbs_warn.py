import time
from playwright.sync_api import sync_playwright
import pandas as pd
from datetime import datetime
import logging
from pathlib import Path
import re

# Setup basic logging to track progress and errors
logging.basicConfig(filename='pbs_warn_scraper.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def fetch_pbs_warn_homepage():
    """
    Fetch PBS WARN homepage HTML using Playwright to handle JavaScript rendering.
    IN-PROGRESS: This is to capture raw HTML for alert extraction.
    """
    url = "https://warn.pbs.org/"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; EmergencyMLScraper/0.1)"}
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_extra_http_headers(headers)
            page.goto(url, wait_until="networkidle", timeout=30000)
            
            # Wait for timestamp element (Updated MM/DD/YYYY HH:MM format on page)
            timestamp_element = "_36XBCKh9PtUiaizdAv2d7t._3rGW2ARGcFG6V04zyupN-3" 
            timestamp_div = f"div.{timestamp_element}"
            page.wait_for_selector(timestamp_div, timeout=10000)
            html = page.content()
            
            # Extract timestamp text
            timestamp_text = page.query_selector(timestamp_div)
            timestamp = timestamp_text.inner_text() if timestamp_text else None

            logging.info(f"Fetched and saved PBS WARN HTML at {timestamp}")
            browser.close()
            return html, timestamp
    except Exception as e:
        logging.error(f"Error fetching page: {e}")
        print(f"Error fetching page: {e}")
        return None

def check_for_alert_keywords(html):
    """
    Scan HTML for emergency alert keywords to confirm relevant content.
    IN-PROGRESS: Next steps include parsing specific alert elements (title, location, etc.)
    """
    if not html:
        logging.warning("No HTML content to check.")
        print("No HTML content to check.")
        return []
    
    # Broad keywords for all WEA types
    keywords = [
        "alert", "warning", "evacuation", "AMBER", "civil emergency",
        "public safety", "evacuation order", "shelter in place",
        "disaster", "emergency", "severe weather", "flood", "fire",
        "tornado", "hazard"
    ]
    
    # Basic keyword frequency check
    found = []
    html_lower = html.lower()
    for keyword in keywords:
        count = html_lower.count(keyword.lower())
        if count > 0:
            found.append({"keyword": keyword, "count": count})
            logging.info(f"Found keyword '{keyword}' {count} times")
            print(f"Keyword '{keyword}': Found {count} times")
    
    return found

def format_timestamp_for_filename(timestamp_str):
    """
    Parse a timestamp string like 'Updated 10/18/2025 14:33:05' and return a safe string for filenames.
    If parsing fails, sanitize the string for filename use.
    """
    if not timestamp_str:
        return "UNKNOWN_TIME"
    match = re.search(r"(\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2})", timestamp_str)
    if match:
        try:
            dt = datetime.strptime(match.group(1), "%m/%d/%Y %H:%M:%S")
            return dt.strftime("%Y-%m-%d_%H%M%S")
        except Exception:
            pass
    # fallback: sanitize string for filename
    return re.sub(r"[^\w]", "_", timestamp_str)

def main():
    """
    Main function to demonstrate scraping and keyword analysis.
    IN-PROGRESS: Roadmap for next steps:
    1. Identify specific DOM selectors for alert details (title, desc, location, expires).
    2. Extract data (JSON) for ingestion.
    3. Implement real-time polling.
    4. Add error retry logic and rate limiting.
    """
    logging.info("Starting PBS WARN scraper (in-progress)")
    html, timestamp = fetch_pbs_warn_homepage()
    keywords_found = check_for_alert_keywords(html)

    # Stub for real-time polling
    # while True:
    #     html = fetch_pbs_warn_homepage()
    #     keywords_found = check_for_alert_keywords(html)
    #     # Future: Save structured alerts to CSV/JSON
    #     time.sleep(120)  # Poll every 2 minutes

    # Format YYYY-MM-DD_HHmmss for filenames
    formatted_timestamp = format_timestamp_for_filename(timestamp)
    keywords_filename = f"pbs_warn_keywords_{formatted_timestamp}.csv"

    # Create output directory if not exists
    output_folder = Path("./pbs_warn_outputs")
    output_folder.mkdir(parents=True, exist_ok=True)
    keywords_filename = output_folder / keywords_filename

    # Save keyword results for review
    if keywords_found:
        df = pd.DataFrame(keywords_found)
        df.to_csv(keywords_filename, index=False)
        logging.info(f"Saved keyword findings to {keywords_filename}")
        print(f"Saved keyword findings to {keywords_filename}")

    if timestamp:
        # TODO: Future save structured alerts to CSV/JSON
        pass

if __name__ == "__main__":
    main()