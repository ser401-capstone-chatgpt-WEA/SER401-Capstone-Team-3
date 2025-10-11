import time
from playwright.sync_api import sync_playwright
import pandas as pd
from datetime import datetime
import logging

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
            
            # Wait for potential alert elements (placeholder)
            page.wait_for_selector("body", timeout=10000)  # Broad selector for now
            html = page.content()
            
            logging.info(f"Fetched and saved PBS WARN HTML at {timestamp}")
            browser.close()
            return html
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
    html = fetch_pbs_warn_homepage()
    keywords_found = check_for_alert_keywords(html)
    
    # Stub for real-time polling
    # while True:
    #     html = fetch_pbs_warn_homepage()
    #     keywords_found = check_for_alert_keywords(html)
    #     # Future: Save structured alerts to CSV/JSON
    #     time.sleep(120)  # Poll every 2 minutes

    # Save keyword results for review
    if keywords_found:
        df = pd.DataFrame(keywords_found)
        df.to_csv("pbs_warn_keywords.csv", index=False)
        logging.info(f"Saved keyword analysis to pbs_warn_keywords.csv")
        print("Saved keyword analysis to pbs_warn_keywords.csv")

if __name__ == "__main__":
    main()