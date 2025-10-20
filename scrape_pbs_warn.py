import time
from playwright.sync_api import sync_playwright
import pandas as pd
from datetime import datetime, timezone
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

def open_alert_menu(page, timeout=5000):
    """
    Click the 'active alerts' button for full details of alerts.
    Returns:
        True if the menu was opened successfully, False otherwise.
    """
    try:
        # Prefer text-based locator to avoid complex class names
        locator = page.locator("div:has-text(\"active alerts\")").first
        if locator.count() == 0:
            # fallback: any nearby icon-only button that looks like the chevron symbol
            btn = page.locator("button.ant-btn.ant-btn-icon-only").first
            if btn.count() == 0:
                return False
            btn.click()
        else:
            # click the button inside that container
            try:
                locator.locator("button").first.click()
            except Exception:
                # fallback: click container itself (sometimes clickable)
                locator.click()
        # wait for the collapsed alerts list container to appear
        page.wait_for_selector("#collapsed-alerts-list", timeout=timeout)
        return True
    except Exception:
        return False 
    
def extract_alerts_from_card_list(page):
    """
    Extract alerts under the '#card-alerts-list' container into a list of dicts.
    Returns: 
        [{ "title", "message", "sender", "expires", "severity_color", "raw_html" }, ...]
    Uses a page.evaluate JS snippet to be tolerant of changing class names.
    """
    try:
        container_sel = "#card-alerts-list"
        if page.query_selector(container_sel) is None:
            # fallback to other likely containers
            for alt in ["div[id*='alerts']", "div.infinite-scroll-component__outerdiv", "div._2yWdPmPkE2Y7yBGf4HUUMN"]:
                if page.query_selector(alt):
                    container_sel = alt
                    break
            else:
                return []

        js = r"""
        (sel) => {
            const container = document.querySelector(sel);
            if (!container) return [];
            // candidate alert nodes: try common item class, otherwise direct children
            let candidates = Array.from(container.querySelectorAll("._3hppmX6GqLF_toD4XOvBXz, ._3g3ZIcAdPcGK1KmFtttxbk"));
            if (candidates.length === 0) {
                candidates = Array.from(container.querySelectorAll(":scope > *")).filter(n => (n.innerText||"").trim().length > 0);
            }
            return candidates.map(el => {
                // title node usually has a background-color style (severity)
                const titleNode = el.querySelector('div[style*="background-color"]') || el.querySelector(":scope > div");
                const title = titleNode ? titleNode.textContent.trim() : "";
                // main message often is the next prominent div
                let message = "";
                const possibleMsgs = Array.from(el.querySelectorAll("div")).filter(d => {
                    const t = (d.textContent||"").trim();
                    return t.length > 20 && !/SENDER|EXPIRES/i.test(t); // heuristic
                });
                if (possibleMsgs.length > 0) message = possibleMsgs[0].textContent.trim();
                // find sender and expires by scanning rows/labels
                let sender = null, expires = null;
                const rows = Array.from(el.querySelectorAll("div.ant-row, div")).slice(0, 10);
                rows.forEach(row => {
                    const texts = Array.from(row.querySelectorAll("div")).map(d => (d.textContent||"").trim());
                    for (let i = 0; i < texts.length; i++) {
                        const t = texts[i].toUpperCase();
                        if (t === "SENDER" && texts[i+1]) sender = texts[i+1];
                        if (t === "EXPIRES" && texts[i+1]) expires = texts[i+1];
                    }
                });
                // severity color from titleNode style or icon color
                let severity_color = null;
                if (titleNode && titleNode.style && titleNode.style.backgroundColor) severity_color = titleNode.style.backgroundColor;
                const icon = el.querySelector("span[role='img'], svg");
                if (!severity_color && icon && icon.style && icon.style.color) severity_color = icon.style.color;
                return { title, message, sender, expires, severity_color, raw_html: el.innerHTML };
            }).filter(it => it.title || it.message);
        }
        """
        alerts = page.evaluate(js, container_sel)
        return alerts or []
    except Exception:
        return []

def fetch_pbs_warn_alert_list():
    """
    Opens PBS WARN, clicks the alerts menu, extracts alerts and returns a list of dicts. 
    """
    url = "https://warn.pbs.org/"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; EmergencyMLScraper/0.1)"}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_extra_http_headers(headers)
            page.goto(url, wait_until="networkidle", timeout=30000)

            # Wait briefly for the alerts button/area to render
            page.wait_for_timeout(500)

            opened = False
            try:
                opened = open_alert_menu(page, timeout=5000)
            except Exception:
                opened = False

            # Try to extract alerts regardless of whether the click-path succeeded.
            alerts = extract_alerts_from_card_list(page)
            # Only warn if we couldn't open the menu AND extraction returned nothing.
            if not opened and not alerts:
                logging.warning("Could not open alert menu and no alerts were extracted; attempted direct extraction")

            browser.close()
            return alerts
    except Exception as e:
        logging.error(f"Error fetching alert list: {e}")
        return []

def test_fetch_homepage():
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

    # Try to save alerts to JSON with timestamped filename
    try:
        # Use timezone-aware UTC timestamp and append a 'Z' to indicate UTC
        formatted_ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%SZ")
        output_folder = Path("./pbs_warn_outputs")
        output_folder.mkdir(parents=True, exist_ok=True)
        out_file = output_folder / f"pbs_warn_alerts_{formatted_ts}.json"
        import json
        with open(out_file, "w", encoding="utf-8") as fh:
            json.dump(html, fh, ensure_ascii=False, indent=2)
        logging.info(f"Saved {len(html)} alerts to {out_file}")
        print(f"Saved {len(html)} alerts to {out_file}")
    except Exception as e:
        logging.error(f"Failed saving alerts JSON: {e}")
        print(f"Failed saving alerts JSON: {e}")

def main():
    """
    Main function to demonstrate scraping and keyword analysis.
    IN-PROGRESS: Roadmap for next steps:
    1. Identify specific DOM selectors for alert details (title, desc, location, expires).
    2. Extract data (JSON) for ingestion.
    3. Implement real-time polling.
    4. Add error retry logic and rate limiting.
    """

    # Homepage fetch with keyword scan and "Updated MM/DD/YYYY HH:MM" timestamp extraction test
    # test_fetch_homepage()

    # Alert list extraction and saving to JSON
    test_fetch_alert_list()
    

if __name__ == "__main__":
    main()