from alert_compare import compare_alerts, load_latest_alert_json, print_alert_diff, compare_and_report_alerts
import time
from playwright.sync_api import sync_playwright
import pandas as pd
from datetime import datetime, timezone
import logging
from pathlib import Path
import re
import json

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
        [{ "title", "message", "sender", "expires", "area", "id", "wea360", "wea90", "severity_color", "raw_html" }, ...]
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
    Returns: 
        [{ "title", "message", "sender", "expires", "severity_color", "raw_html" }, ...]
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

def fetch_pbs_warn_alerts_with_details():
    """
    Navigate to PBS WARN, open alerts, click each alert card to expand details,
    extract structured fields for each alert, save to a timestamped JSON file,
    and return the list of alert dicts.
    Returns:
        [{ "title", "message", "sender", "expires", "severity_color]
    """
    url = "https://warn.pbs.org/"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; EmergencyMLScraper/0.1)"}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            page = browser.new_page()
            page.set_extra_http_headers(headers)
            page.goto(url, wait_until="networkidle", timeout=30000)

            # Forward browser console messages to our log for debugging timing/scope issues
            try:
                page.on("console", lambda msg: logging.info(f"[browser console] {msg.type}: {msg.text}"))
            except Exception:
                # best-effort; not critical
                pass

            # Try to capture site timestamp for filenames
            timestamp_element = "_36XBCKh9PtUiaizdAv2d7t._3rGW2ARGcFG6V04zyupN-3"
            timestamp_div = f"div.{timestamp_element}"
            site_timestamp = None
            try:
                if page.query_selector(timestamp_div):
                    site_timestamp = page.query_selector(timestamp_div).inner_text()
            except Exception:
                site_timestamp = None

            # Open the alert menu
            try:
                open_alert_menu(page, timeout=5000)
            except Exception:
                pass
            # Wait for the card list container to be present
            try:
                page.wait_for_selector("#card-alerts-list, div.infinite-scroll-component__outerdiv", timeout=5000)
            except Exception:
                pass

            # Find candidate alert card elements
            candidates = page.query_selector_all("div._3hppmX6GqLF_toD4XOvBXz")
            if not candidates:
                # fallback to container children
                container = page.query_selector("#card-alerts-list") or page.query_selector("div.infinite-scroll-component__outerdiv")
                if container:
                    candidates = container.query_selector_all(":scope > *")

            alerts = []
            for el in candidates:
                try:
                    # Skip non-alert headers (e.g., 'Alert List' container)
                    try:
                        title_preview = el.evaluate("el => { const n = el.querySelector('div[style*=\"background-color\"]') || el.querySelector(':scope > div'); return n ? n.textContent.trim() : (el.textContent||'').trim(); }")
                        if not title_preview:
                            continue
                        if 'alert list' in title_preview.lower() or 'active alerts' in title_preview.lower():
                            continue
                    except Exception:
                        # if evaluation fails, continue with best-effort
                        pass

                    # Click the title node (preferred) to expand details, otherwise click the card
                    try:
                        title_node = el.query_selector("div[style*='background-color']") or el.query_selector(":scope > div")
                        if title_node:
                            try:
                                title_node.click()
                                # give the UI a bit more time to render expanded details
                                page.wait_for_timeout(1000)
                            except Exception:
                                # fallback to clicking the card itself
                                el.click()
                                page.wait_for_timeout(1000)
                        else:
                            el.click()
                            page.wait_for_timeout(1000)
                    except Exception:
                        # ignore click errors and attempt to extract anyway
                        page.wait_for_timeout(400)

                    # Extract details from the expanded detail panel (preferred).
                    # Strategy: wait for a panel-like node, evaluate a JS extractor
                    # against the page to read the full details, then fall back to
                    # a scoped extractor evaluated on the card if needed. On repeated
                    # failures we save debug artifacts (HTML/screenshot) for inspection.
                    # Use a global search that prefers nodes containing 'SENDER'/'EXPIRES'.
                    global_js = r"""
                    () => {
                        // Try to find an element that contains SENDER or EXPIRES and looks like a detail panel
                        const candidate = Array.from(document.querySelectorAll('div')).find(d => /SENDER|EXPIRES/i.test(d.textContent || ''));
                        const panel = candidate || document.querySelector('div._2kD36e8w0LlK3JPw_QHlKm');
                        if (!panel) return null;

                        const titleNode = panel.querySelector('div[style*="background-color"]') || panel.querySelector('h1') || panel.querySelector('h2') || panel.querySelector(':scope > div');
                        const title = titleNode ? titleNode.textContent.trim() : '';

                        const out = { title: title, message: '', sender: null, expires: null, sent: null, area: null, id: null, wea360: null, wea90: null, severity_color: null, history: [], unknown_extras: {}, raw_html: panel.outerHTML };

                        // label/value rows: try to find rows containing label-like text
                        const rows = Array.from(panel.querySelectorAll('div')).filter(d => (d.querySelectorAll(':scope > div').length >= 2));
                        const rowsCols = rows.map(r => Array.from(r.querySelectorAll(':scope > div')).map(d => (d.textContent||'').trim()).filter(Boolean));
                        // If the first matching row looks like labels and the next row looks like values, map by index
                        if (rowsCols.length >= 2 && rowsCols[0].every(x => x && x === x.toUpperCase())) {
                            const labels = rowsCols[0];
                            const values = rowsCols[1] || [];
                            for (let i = 0; i < labels.length; i++) {
                                const lab = (labels[i]||'').toUpperCase();
                                const val = values[i] || null;
                                const key = lab.toLowerCase().replace(/\s+/g,'_').replace(/[^a-z0-9_]/g,'');
                                if (lab === 'SENDER') out.sender = val;
                                else if (lab === 'EXPIRES') out.expires = val;
                                else if (lab === 'SENT') out.sent = val;
                                else if (lab === 'AREA') out.area = val;
                                else if (lab === 'ID') out.id = val;
                                else if (/WEA\s*360/i.test(lab)) out.wea360 = val;
                                else if (/WEA\s*90/i.test(lab)) out.wea90 = val;
                                else if (lab === 'HEADLINE_EN' || lab === 'HEADLINE' || /HEADLINE/i.test(lab)) out.headline_en = val;
                                else if (lab === 'DESCRIPTION_EN' || /DESCRIPTION/i.test(lab)) out.description_en = val;
                                else if (lab === 'INSTRUCTIONS_EN' || /INSTRUCTION/i.test(lab)) out.instructions_en = val;
                                else if (lab === 'CONTACT') out.contact = val;
                                else out.unknown_extras[key] = val;
                            }
                        } else {
                            rows.forEach(row => {
                                const cols = Array.from(row.querySelectorAll(':scope > div')).map(d => (d.textContent||'').trim()).filter(Boolean);
                                if (cols.length >= 2) {
                                    const lab = cols[0].toUpperCase();
                                    const val = cols[1];
                                    const key = lab.toLowerCase().replace(/\s+/g,'_').replace(/[^a-z0-9_]/g,'');
                                    if (lab === 'SENDER') out.sender = val;
                                    else if (lab === 'EXPIRES') out.expires = val;
                                    else if (lab === 'SENT') out.sent = val;
                                    else if (lab === 'AREA') out.area = val;
                                    else if (lab === 'ID') out.id = val;
                                    else if (/WEA\s*360/i.test(lab)) out.wea360 = val;
                                    else if (/WEA\s*90/i.test(lab)) out.wea90 = val;
                                    else if (/HEADLINE/i.test(lab)) out.headline_en = val;
                                    else if (/DESCRIPTION/i.test(lab)) out.description_en = val;
                                    else if (/INSTRUCTION/i.test(lab)) out.instructions_en = val;
                                    else if (lab === 'CONTACT') out.contact = val;
                                    else out.unknown_extras[key] = val;
                                }
                            });
                        }

                        // fallback message: look for obvious message containers
                        const msgCandidate = panel.querySelector('.LgcsbPsiL2uEI-nZqHF-e') || panel.querySelector('.message') || panel.querySelector('p');
                        if (msgCandidate) out.message = msgCandidate.textContent.trim();

                        // history items: parse list items into structured entries {tag, title, id, sent}
                        out.history = Array.from(panel.querySelectorAll('.ant-list-items li')).map(li => {
                            try {
                                const tagSpan = li.querySelector('span._1iv5qxCNer7nWUpYxE49gV');
                                const tag = tagSpan ? (tagSpan.textContent||'').trim() : null;
                                // title often includes the tag span; remove the tag text if present
                                const titleNode = li.querySelector('div.ant-row > div, div');
                                let titleText = titleNode ? (titleNode.textContent||'').trim() : '';
                                if (tagSpan) {
                                    const tagText = (tagSpan.textContent||'').trim();
                                    // remove tag occurrence and any leading whitespace / NBSP
                                    titleText = titleText.replace(tagText, '').replace(/^[:\s\u00A0]+/, '').trim();
                                }

                                // subsequent rows often contain label rows and value rows
                                const labelRows = Array.from(li.querySelectorAll('div.ant-row')).slice(1);
                                let id = null, sent = null;
                                const rowsCols = labelRows.map(r => Array.from(r.querySelectorAll('div')).map(d => (d.textContent||'').trim()).filter(Boolean));
                                // If first row is labels and second row values, map them
                                if (rowsCols.length >= 2 && rowsCols[0].length > 0) {
                                    const labels = rowsCols[0];
                                    const values = rowsCols[1] || [];
                                    for (let i = 0; i < labels.length; i++) {
                                        const lab = (labels[i]||'').toUpperCase();
                                        const val = values[i] || null;
                                        if (lab === 'ID') id = val;
                                        else if (lab === 'SENT') sent = val;
                                    }
                                } else {
                                    // fallback: per-row parsing
                                    labelRows.forEach(r => {
                                        const cols = Array.from(r.querySelectorAll('div')).map(d => (d.textContent||'').trim()).filter(Boolean);
                                        if (cols.length === 2) {
                                            if (cols[0].toUpperCase() === 'ID') id = cols[1];
                                            if (cols[0].toUpperCase() === 'SENT') sent = cols[1];
                                        } else if (cols.length === 4) {
                                            if (cols[0].toUpperCase() === 'ID') id = cols[1];
                                            if (cols[2].toUpperCase() === 'SENT') sent = cols[3];
                                        }
                                    });
                                }
                                return { tag: tag, title: titleText, id: id, sent: sent };
                            } catch (e) { return null; }
                        }).filter(Boolean);

                        // severity color heuristics
                        const titleEl = panel.querySelector('div[style*="background-color"]') || panel.querySelector('span[role="img"], svg');
                        if (titleEl && titleEl.style && titleEl.style.backgroundColor) out.severity_color = titleEl.style.backgroundColor;
                        else if (titleEl && titleEl.style && titleEl.style.color) out.severity_color = titleEl.style.color;

                        return out;
                    }
                    """

                    # Fallback JS that is scoped to a card element (older UI variants)
                    scoped_js = r"""
                    (el) => {
                        const titleNode = el.querySelector('div[style*="background-color"]') || el.querySelector(':scope > div');
                        const title = titleNode ? titleNode.textContent.trim() : '';
                        const out = { title: title, message: '', sender: null, expires: null, sent: null, area: null, id: null, wea360: null, wea90: null, severity_color: null, history: [], unknown_extras: {} };
                        const rows = Array.from(el.querySelectorAll('div')).filter(d => (d.querySelectorAll(':scope > div').length >= 2));
                        const rowsCols = rows.map(r => Array.from(r.querySelectorAll(':scope > div')).map(d => (d.textContent||'').trim()).filter(Boolean));
                        if (rowsCols.length >= 2 && rowsCols[0].every(x => x && x === x.toUpperCase())) {
                            const labels = rowsCols[0];
                            const values = rowsCols[1] || [];
                            for (let i = 0; i < labels.length; i++) {
                                const lab = (labels[i]||'').toUpperCase();
                                const val = values[i] || null;
                                const key = lab.toLowerCase().replace(/\s+/g,'_').replace(/[^a-z0-9_]/g,'');
                                if (lab === 'SENDER') out.sender = val;
                                else if (lab === 'EXPIRES') out.expires = val;
                                else if (lab === 'SENT') out.sent = val;
                                else if (lab === 'AREA') out.area = val;
                                else if (lab === 'ID') out.id = val;
                                else if (/WEA\s*360/i.test(lab)) out.wea360 = val;
                                else if (/WEA\s*90/i.test(lab)) out.wea90 = val;
                                else if (/HEADLINE/i.test(lab)) out.headline_en = val;
                                else if (/DESCRIPTION/i.test(lab)) out.description_en = val;
                                else if (/INSTRUCTION/i.test(lab)) out.instructions_en = val;
                                else if (lab === 'CONTACT') out.contact = val;
                                else out.unknown_extras[key] = val;
                            }
                        } else {
                            rows.forEach(row => {
                                const cols = Array.from(row.querySelectorAll(':scope > div')).map(d => (d.textContent||'').trim()).filter(Boolean);
                                if (cols.length >= 2) {
                                    const lab = cols[0].toUpperCase();
                                    const val = cols[1];
                                    const key = lab.toLowerCase().replace(/\s+/g,'_').replace(/[^a-z0-9_]/g,'');
                                    if (lab === 'SENDER') out.sender = val;
                                    else if (lab === 'EXPIRES') out.expires = val;
                                    else if (lab === 'SENT') out.sent = val;
                                    else if (lab === 'AREA') out.area = val;
                                    else if (lab === 'ID') out.id = val;
                                    else if (/WEA\s*360/i.test(lab)) out.wea360 = val;
                                    else if (/WEA\s*90/i.test(lab)) out.wea90 = val;
                                    else if (/HEADLINE/i.test(lab)) out.headline_en = val;
                                    else if (/DESCRIPTION/i.test(lab)) out.description_en = val;
                                    else if (/INSTRUCTION/i.test(lab)) out.instructions_en = val;
                                    else if (lab === 'CONTACT') out.contact = val;
                                    else out.unknown_extras[key] = val;
                                }
                            });
                        }
                        const msgCandidate = el.querySelector('.LgcsbPsiL2uEI-nZqHF-e') || el.querySelector('.message') || el.querySelector('p');
                        if (msgCandidate) out.message = msgCandidate.textContent.trim();
                        out.history = Array.from(el.querySelectorAll('.ant-list-items li')).map(li => {
                            try {
                                const tagSpan = li.querySelector('span._1iv5qxCNer7nWUpYxE49gV');
                                const tag = tagSpan ? (tagSpan.textContent||'').trim() : null;
                                const titleNode = li.querySelector('div.ant-row > div, div');
                                let titleText = titleNode ? (titleNode.textContent||'').trim() : '';
                                if (tagSpan) {
                                    const tagText = (tagSpan.textContent||'').trim();
                                    titleText = titleText.replace(tagText, '').replace(/^[:\s\u00A0]+/, '').trim();
                                }
                                const labelRows = Array.from(li.querySelectorAll('div.ant-row')).slice(1);
                                let id = null, sent = null;
                                const rowsCols = labelRows.map(r => Array.from(r.querySelectorAll('div')).map(d => (d.textContent||'').trim()).filter(Boolean));
                                if (rowsCols.length >= 2 && rowsCols[0].length > 0) {
                                    const labels = rowsCols[0];
                                    const values = rowsCols[1] || [];
                                    for (let i = 0; i < labels.length; i++) {
                                        const lab = (labels[i]||'').toUpperCase();
                                        const val = values[i] || null;
                                        if (lab === 'ID') id = val;
                                        else if (lab === 'SENT') sent = val;
                                    }
                                } else {
                                    labelRows.forEach(r => {
                                        const cols = Array.from(r.querySelectorAll('div')).map(d => (d.textContent||'').trim()).filter(Boolean);
                                        if (cols.length === 2) {
                                            if (cols[0].toUpperCase() === 'ID') id = cols[1];
                                            if (cols[0].toUpperCase() === 'SENT') sent = cols[1];
                                        } else if (cols.length === 4) {
                                            if (cols[0].toUpperCase() === 'ID') id = cols[1];
                                            if (cols[2].toUpperCase() === 'SENT') sent = cols[3];
                                        }
                                    });
                                }
                                return { tag: tag, title: titleText, id: id, sent: sent };
                            } catch (e) { return null; }
                        }).filter(Boolean);
                        return out;
                    }
                    """

                    details = None
                    for attempt in range(4):
                        try:
                            # Prefer a real detail panel element; avoid evaluating against document.body
                            panel_selector = "div._3g3ZIcAdPcGK1KmFtttxbk._2kD36e8w0LlK3JPw_QHlKm, div._2kD36e8w0LlK3JPw_QHlKm"
                            try:
                                page.wait_for_selector(panel_selector, timeout=1500)
                                details = page.evaluate(global_js)
                            except Exception:
                                # Panel not found yet; skip global eval this attempt
                                details = None
                        except Exception:
                            details = None

                        # If that didn't return useful fields, try a scoped eval against the card
                        if not details or not (details.get('sender') or details.get('expires') or details.get('wea90')):
                            try:
                                details = el.evaluate(scoped_js)
                            except Exception:
                                details = details or None

                        # If key fields found, break early
                        if details and (details.get('sender') or details.get('expires') or details.get('wea90')):
                            break

                        # wait a bit (exponential backoff)
                        page.wait_for_timeout(250 * (attempt + 1))

                    # If still missing key data, dump the global panel HTML and take a screenshot for debugging
                    if not details or not (details.get('sender') or details.get('expires') or details.get('wea90')):
                        try:
                            dump_ts = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
                            output_folder = Path('./pbs_warn_outputs')
                            output_folder.mkdir(parents=True, exist_ok=True)
                            # Save full page HTML for inspection
                            page_html_file = output_folder / f'debug_page_{dump_ts}_{len(alerts)}.html'
                            with open(page_html_file, 'w', encoding='utf-8') as fh:
                                fh.write(page.content())
                            # Save a screenshot (headful run will capture current viewport)
                            screenshot_file = output_folder / f'debug_page_{dump_ts}_{len(alerts)}.png'
                            try:
                                page.screenshot(path=str(screenshot_file), full_page=True)
                            except Exception:
                                # try a viewport screenshot fallback
                                try:
                                    page.screenshot(path=str(screenshot_file))
                                except Exception:
                                    pass
                            logging.info(f'Wrote debug HTML and screenshot to {page_html_file} / {screenshot_file}')
                        except Exception:
                            pass

                    # Normalize the details dict to include expected keys
                    if not isinstance(details, dict):
                        details = {}
                    # canonical keys we want at top level
                    canonical_keys = ['title', 'message', 'sender', 'expires', 'sent', 'area', 'id', 'wea360', 'wea90', 'severity_color', 'raw_html', 'history', 'headline_en', 'description_en', 'instructions_en', 'contact', 'unknown_extras']
                    # ensure canonical keys exist
                    for k in canonical_keys:
                        if k not in details:
                            details[k] = [] if k == 'history' else ({} if k == 'unknown_extras' else None)

                    # Move any non-canonical top-level keys into extras
                    try:
                        for k in list(details.keys()):
                            if k not in canonical_keys:
                                # move unexpected keys into unknown_extras (don't overwrite existing keys)
                                try:
                                    if not isinstance(details.get('unknown_extras'), dict):
                                        details['unknown_extras'] = {}
                                    details['unknown_extras'][k] = details.pop(k)
                                    logging.info(f"Moved unexpected top-level key '{k}' into unknown_extras")
                                except Exception:
                                    # ensure unknown_extras exists
                                    details.setdefault('unknown_extras', {})
                                    details['unknown_extras'][k] = details.pop(k)
                                    logging.info(f"Moved unexpected top-level key '{k}' into unknown_extras")
                    except Exception:
                        pass

                    # Log any unknown_extras keys found for this alert to help tuning
                    try:
                        if details.get('unknown_extras') and isinstance(details.get('unknown_extras'), dict):
                            keys_found = list(details.get('unknown_extras').keys())
                            if keys_found:
                                logging.info(f"Alert unknown_extras keys: {keys_found}")
                    except Exception:
                        pass

                    # Post-process: if top-level id or sent look wrong (e.g. id == 'Sent'), try to pull from history
                    try:
                        if (not details.get('id') or (isinstance(details.get('id'), str) and details.get('id').strip().lower() == 'sent')) and details.get('history'):
                            for h in details.get('history'):
                                if isinstance(h, dict) and h.get('id'):
                                    details['id'] = h.get('id')
                                    break
                        if (not details.get('sent')) and details.get('history'):
                            for h in details.get('history'):
                                if isinstance(h, dict) and h.get('sent'):
                                    details['sent'] = h.get('sent')
                                    break
                    except Exception:
                        pass

                    # NOTE: per-alert `page_updated` removed; keep page_updated only at file-level
                    alerts.append(details)
                except Exception:
                    continue

            # Save alerts to JSON using site timestamp (fallback to utcnow if missing)
            try:
                # Use site timestamp when available, otherwise UTC now. Ensure trailing 'Z' to indicate UTC.
                raw_ts = format_timestamp_for_filename(site_timestamp) if site_timestamp else datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
                ts_for_file = f"{raw_ts}Z" if not str(raw_ts).endswith('Z') else raw_ts
                output_folder = Path("./pbs_warn_outputs")
                output_folder.mkdir(parents=True, exist_ok=True)
                out_file = output_folder / f"pbs_warn_alerts_{ts_for_file}.json"
                # file-level metadata
                file_payload = {
                    "scrape_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "page_updated": site_timestamp if site_timestamp else None,
                    "alerts": alerts,
                }
                with open(out_file, "w", encoding="utf-8") as fh:
                    json.dump(file_payload, fh, ensure_ascii=False, indent=2)
                logging.info(f"Saved {len(alerts)} detailed alerts to {out_file}")
            except Exception as e:
                logging.error(f"Failed saving detailed alerts JSON: {e}")

            browser.close()
            return alerts
    except Exception as e:
        logging.error(f"Error fetching detailed alert list: {e}")
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
        with open(out_file, "w", encoding="utf-8") as fh:
            json.dump(html, fh, ensure_ascii=False, indent=2)
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

    # Homepage fetch with keyword scan and "Updated MM/DD/YYYY HH:MM" timestamp extraction test
    # test_fetch_homepage()

    # Alert list extraction and saving to JSON
    # test_fetch_alert_list()

    # Alert list extraction with detailed fields and saving to JSON
    test_fetch_alerts_with_details()
    
    

if __name__ == "__main__":
    main()