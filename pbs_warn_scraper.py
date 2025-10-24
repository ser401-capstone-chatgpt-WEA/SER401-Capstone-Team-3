import logging
from playwright.sync_api import sync_playwright
from datetime import datetime, timezone
from pathlib import Path
from pbs_warn_utils import format_timestamp_for_filename
import json

# --- Playwright scraping functions for PBS WARN ---

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

def open_alert_menu(page, timeout=5000):
    """
    Click the 'active alerts' button for full details of alerts.
    Returns: True if the menu was opened successfully, False otherwise.
    """
    try:
        locator = page.locator("div:has-text(\"active alerts\")").first
        if locator.count() == 0:
            btn = page.locator("button.ant-btn.ant-btn-icon-only").first
            if btn.count() == 0:
                return False
            btn.click()
        else:
            try:
                locator.locator("button").first.click()
            except Exception:
                locator.click()
        page.wait_for_selector("#collapsed-alerts-list", timeout=timeout)
        return True
    except Exception:
        return False

def extract_alerts_from_card_list(page):
    """
    Extract alerts under the '#card-alerts-list' container into a list of dicts.
    Returns: [{ "title", "message", "sender", "expires", "area", "id", "wea360", "wea90", "severity_color", "raw_html" }, ...]
    Uses a page.evaluate JS snippet to be tolerant of changing class names.
    """
    try:
        container_sel = "#card-alerts-list"
        if page.query_selector(container_sel) is None:
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
            let candidates = Array.from(container.querySelectorAll("._3hppmX6GqLF_toD4XOvBXz, ._3g3ZIcAdPcGK1KmFtttxbk"));
            if (candidates.length === 0) {
                candidates = Array.from(container.querySelectorAll(":scope > *")).filter(n => (n.innerText||"").trim().length > 0);
            }
            return candidates.map(el => {
                const titleNode = el.querySelector('div[style*="background-color"]') || el.querySelector(":scope > div");
                const title = titleNode ? titleNode.textContent.trim() : "";
                let message = "";
                const possibleMsgs = Array.from(el.querySelectorAll("div")).filter(d => {
                    const t = (d.textContent||"").trim();
                    return t.length > 20 && !/SENDER|EXPIRES/i.test(t);
                });
                if (possibleMsgs.length > 0) message = possibleMsgs[0].textContent.trim();
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
    Returns: [{ "title", "message", "sender", "expires", "severity_color", "raw_html" }, ...]
    """
    url = "https://warn.pbs.org/"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; EmergencyMLScraper/0.1)"}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_extra_http_headers(headers)
            page.goto(url, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(500)
            opened = False
            try:
                opened = open_alert_menu(page, timeout=5000)
            except Exception:
                opened = False
            alerts = extract_alerts_from_card_list(page)
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
    Returns: [{ "title", "message", "sender", "expires", "severity_color", ... }]
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
                pass  # best-effort; not critical
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
            # JavaScript for global detail panel extraction
            global_js = r"""
            () => {
                const candidate = Array.from(document.querySelectorAll('div')).find(d => /SENDER|EXPIRES/i.test(d.textContent || ''));
                const panel = candidate || document.querySelector('div._2kD36e8w0LlK3JPw_QHlKm');
                if (!panel) return null;
                const titleNode = panel.querySelector('div[style*="background-color"]') || panel.querySelector('h1') || panel.querySelector('h2') || panel.querySelector(':scope > div');
                const title = titleNode ? titleNode.textContent.trim() : '';
                const out = {
                    title: title,
                    message: '',
                    sender: null,
                    expires: null,
                    sent: null,
                    area: null,
                    id: null,
                    wea360: null,
                    wea90: null,
                    severity_color: null,
                    history: [],
                    unknown_extras: {},
                    raw_html: panel.outerHTML
                };
                const rows = Array.from(panel.querySelectorAll('div')).filter(d => (d.querySelectorAll(':scope > div').length >= 2));
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
                const msgCandidate = panel.querySelector('.LgcsbPsiL2uEI-nZqHF-e') || panel.querySelector('.message') || panel.querySelector('p');
                if (msgCandidate) out.message = msgCandidate.textContent.trim();
                out.history = Array.from(panel.querySelectorAll('.ant-list-items li')).map(li => {
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
                    } catch (e) {
                        return null;
                    }
                }).filter(Boolean);
                const titleEl = panel.querySelector('div[style*="background-color"]') || panel.querySelector('span[role="img"], svg');
                if (titleEl && titleEl.style && titleEl.style.backgroundColor) out.severity_color = titleEl.style.backgroundColor;
                else if (titleEl && titleEl.style && titleEl.style.color) out.severity_color = titleEl.style.color;
                return out;
            }
            """
            # --- Carousel-based extraction ---
            # 1. Click the carousel view button
            carousel_btn_sel = "#root > section > section > aside.ant-layout-sider.ant-layout-sider-dark.Gb6ok_P6af6seffG7YNra._26t5t_5MUYTCqs9AJH5DRO > div > div > div._323XwujjRZBLWALqFE5ESb.k2rNyTK4VfG39NuCnq2EA._3X5aNRykq33B670UdsI3wF > button"
            try:
                carousel_btn = page.query_selector(carousel_btn_sel)
                if carousel_btn:
                    carousel_btn.click()
                    page.wait_for_timeout(1000)
                    logging.info("Switched to carousel view")
                else:
                    logging.warning("Carousel view button not found")
            except Exception as e:
                logging.warning(f"Could not click carousel view button: {e}")

            # 2. Cycle through alerts using next button
            next_btn_sel = "#root > section > section > aside.ant-layout-sider.ant-layout-sider-dark.Gb6ok_P6af6seffG7YNra._26t5t_5MUYTCqs9AJH5DRO > div > div > div.Vm0ocG4nLk4tOiMCx6F92 > div > div > div > div > div:nth-child(3) > button"
            alerts = []
            seen_keys = set()
            max_alerts = 20  # safety limit
            for i in range(max_alerts):
                # Extract details from the currently visible alert
                try:
                    details = page.evaluate(global_js)
                    if details:
                        # Create unique key from title, sender, expires, id
                        unique_key = f"{details.get('title', '')}|{details.get('sender', '')}|{details.get('expires', '')}|{details.get('id', '')}"
                        if unique_key in seen_keys:
                            logging.info(f"Detected duplicate alert at iteration {i}, stopping carousel")
                            break
                        seen_keys.add(unique_key)
                        alerts.append(details)
                        logging.info(f"Extracted alert {len(alerts)}: {details.get('title', 'Unknown')}")
                    else:
                        logging.warning(f"No details extracted at iteration {i}")
                except Exception as e:
                    logging.warning(f"Error extracting alert details at iteration {i}: {e}")
                    break

                # Click next button
                try:
                    next_btn = page.query_selector(next_btn_sel)
                    if not next_btn or next_btn.is_disabled():
                        logging.info(f"No more next button at iteration {i}, stopping")
                        break
                    next_btn.click()
                    page.wait_for_timeout(1000)
                except Exception as e:
                    logging.info(f"No more next button or error clicking next at iteration {i}: {e}")
                    break

            # Save alerts to JSON
            try:
                raw_ts = format_timestamp_for_filename(site_timestamp) if site_timestamp else datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
                ts_for_file = f"{raw_ts}Z" if not str(raw_ts).endswith('Z') else raw_ts
                output_folder = Path("./pbs_warn_outputs")
                output_folder.mkdir(parents=True, exist_ok=True)
                out_file = output_folder / f"pbs_warn_alerts_{ts_for_file}.json"
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