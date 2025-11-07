# This module contains a focused implementation of the detailed-alert scraper for PBS WARN.

from playwright.sync_api import sync_playwright
from datetime import datetime, timezone
from pathlib import Path
import logging
import json
import re

# Configure logging similarly to the main scraper
logging.basicConfig(filename='pbs_warn_scraper.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

### JS Extracters ###
GLOBAL_JS = r"""
() => {
const candidate = Array.from(document.querySelectorAll('div')).find(d => /SENDER|EXPIRES/i.test(d.textContent || ''));
const panel = candidate || document.querySelector('div._2kD36e8w0LlK3JPw_QHlKm');
if (!panel) return null;
const titleNode = panel.querySelector('div[style*="background-color"]') || panel.querySelector('h1') || panel.querySelector('h2') || panel.querySelector(':scope > div');
const title = titleNode ? titleNode.textContent.trim() : '';
const out = { title: title, message: '', sender: null, expires: null, sent: null, area: null, id: null, wea360: null, wea90: null, severity_color: null, history: [], unknown_extras: {}, raw_html: panel.outerHTML };

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

const msgCandidate = panel.querySelector('.LgcsbPsiL2uEI-nZqHF-e') || panel.querySelector('.message') || panel.querySelector('p');
if (msgCandidate) out.message = msgCandidate.textContent.trim();

// Prefer to respect the 'Alert History (n)' header when present so we
// capture the expected number of history entries for this panel and avoid
// accidentally reading cached items from a different alert.
out.history = (function(){
    try {
        const header = Array.from(panel.querySelectorAll('div')).find(d => /Alert\s+History\s*\(\d+\)/i.test(d.textContent||''));
        let items = [];
        if (header) {
            const m = (header.textContent||'').match(/Alert\s+History\s*\((\d+)\)/i);
            const count = m ? parseInt(m[1], 10) : null;
            // Navigate up to find the history container, then search down for ul.ant-list-items
            let historyContainer = header.parentElement;
            let ul = null;
            if (historyContainer) {
                // The ul is nested several levels deep, so use querySelectorAll to find it
                ul = historyContainer.querySelector('ul.ant-list-items');
            }
            if (!ul) ul = panel.querySelector('ul.ant-list-items');
            if (ul) {
                // Use :scope > li to get direct children only
                const all = Array.from(ul.querySelectorAll(':scope > li'));
                items = (count && count > 0) ? all.slice(0, count) : all;
            }
        }
        if (!items || items.length === 0) {
            const ul = panel.querySelector('ul.ant-list-items');
            if (ul) {
                items = Array.from(ul.querySelectorAll(':scope > li'));
            } else {
                items = Array.from(panel.querySelectorAll('.ant-list-items li'));
            }
        }
        return items.map(li => {
    try {
    // Robust tag/title extraction without relying on hashed classes
    // The first row inside the history list item holds the visible title and an icon+tag cluster
    const titleRow = li.querySelector(':scope > div.ant-row');
    let titleText = '';
    let tag = null;
    if (titleRow) {
        const clone = titleRow.cloneNode(true);
        // The tag label is typically the parent of span[role="img"]. Remove just that container to leave a clean title
        const icon = clone.querySelector('span[role="img"]');
        const tagContainer = icon && icon.parentElement ? icon.parentElement : null;
        if (tagContainer) {
            tag = (tagContainer.textContent||'').trim();
            tagContainer.remove();
        }
        titleText = (clone.textContent||'').trim();
    } else {
        // Fallback to previous approach
        const titleNode = li.querySelector('div.ant-row > div, div');
        titleText = titleNode ? (titleNode.textContent||'').trim() : '';
        // Try to locate a tag container structurally and strip it from the title
        const icon = li.querySelector('span[role="img"]');
        const tagContainer = icon && icon.parentElement ? icon.parentElement : null;
        if (tagContainer) {
            const tagText = (tagContainer.textContent||'').trim();
            if (!tag) tag = tagText;
            titleText = titleText.replace(tagText, '').replace(/^[:\s\u00A0]+/, '').trim();
        }
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
    } catch (e) { return []; }
})();

const titleEl = panel.querySelector('div[style*="background-color"]') || panel.querySelector('span[role="img"], svg');
if (titleEl && titleEl.style && titleEl.style.backgroundColor) out.severity_color = titleEl.style.backgroundColor;
else if (titleEl && titleEl.style && titleEl.style.color) out.severity_color = titleEl.style.color;

return out;
}
"""

SCOPED_JS = r"""
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
// Scoped extractor: respect the 'Alert History (n)' header inside the card
out.history = (function(){
    try {
        const header = Array.from(el.querySelectorAll('div')).find(d => /Alert\s+History\s*\(\d+\)/i.test(d.textContent||''));
        let items = [];
        if (header) {
            const m = (header.textContent||'').match(/Alert\s+History\s*\((\d+)\)/i);
            const count = m ? parseInt(m[1], 10) : null;
            // Navigate up to find the history container, then search down for ul.ant-list-items
            let historyContainer = header.parentElement;
            let ul = null;
            if (historyContainer) {
                // The ul is nested several levels deep, so use querySelectorAll to find it
                ul = historyContainer.querySelector('ul.ant-list-items');
            }
            if (!ul) ul = el.querySelector('ul.ant-list-items');
            if (ul) {
                // Use :scope > li to get direct children only
                const all = Array.from(ul.querySelectorAll(':scope > li'));
                items = (count && count > 0) ? all.slice(0, count) : all;
            }
        }
        if (!items || items.length === 0) {
            const ul = el.querySelector('ul.ant-list-items');
            if (ul) {
                items = Array.from(ul.querySelectorAll(':scope > li'));
            } else {
                items = Array.from(el.querySelectorAll('.ant-list-items li'));
            }
        }
        return items.map(li => {
    try {
    // Robust tag/title extraction without relying on hashed classes
    const titleRow = li.querySelector(':scope > div.ant-row');
    let titleText = '';
    let tag = null;
    if (titleRow) {
        const clone = titleRow.cloneNode(true);
        const icon = clone.querySelector('span[role="img"]');
        const tagContainer = icon && icon.parentElement ? icon.parentElement : null;
        if (tagContainer) {
            tag = (tagContainer.textContent||'').trim();
            tagContainer.remove();
        }
        titleText = (clone.textContent||'').trim();
    } else {
        const titleNode = li.querySelector('div.ant-row > div, div');
        titleText = titleNode ? (titleNode.textContent||'').trim() : '';
        const icon = li.querySelector('span[role="img"]');
        const tagContainer = icon && icon.parentElement ? icon.parentElement : null;
        if (tagContainer) {
            const tagText = (tagContainer.textContent||'').trim();
            if (!tag) tag = tagText;
            titleText = titleText.replace(tagText, '').replace(/^[:\s\u00A0]+/, '').trim();
        }
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
    } catch (e) { return []; }
})();
return out;
}
"""

### Helper Functions ###
def format_timestamp_for_filename(timestamp_str):
    """Format a timestamp string into a filename-friendly format (YYYY-MM-DD_HHMMSS)."""
    if not timestamp_str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    match = re.search(r"(\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2})", timestamp_str)
    if match:
        try:
            dt = datetime.strptime(match.group(1), "%m/%d/%Y %H:%M:%S")
            return dt.strftime("%Y-%m-%d_%H%M%S")
        except Exception:
            pass
    return re.sub(r"[^\w]", "_", timestamp_str)


def _filter_candidates(candidates):
    """
    Return a filtered list of candidate elements, skipping header/prelude nodes.

    Args:
        candidates (list): A list of candidate elements to filter.

    Returns:
        list: A filtered list of candidate elements.
    """
    filtered = []
    for el in candidates:
        try:
            title_preview = el.evaluate("el => { const n = el.querySelector('div[style*=\"background-color\"]') || el.querySelector(':scope > div'); return n ? n.textContent.trim() : (el.textContent||'').trim(); }")
            if not title_preview:
                continue
            low = title_preview.lower()
            if 'alert list' in low or 'active alerts' in low:
                logging.debug(f"Skipping non-alert card with preview: {title_preview}")
                continue
            filtered.append(el)
        except Exception:
            filtered.append(el)
    return filtered


def _get_carousel_info(page):
    """Return (current_index, total) if a Carousel 'Alert i of n' indicator exists on the page.

    Returns None if not found or parsing fails.
    """
    try:
        txt = page.evaluate(r"() => { const n = Array.from(document.querySelectorAll('div')).find(d => /Alert\s+\d+\s+of\s+\d+/i.test(d.textContent||'')); return n ? n.textContent.trim() : null; }")
        if not txt:
            return None
        m = re.search(r"Alert\s+(\d+)\s+of\s+(\d+)", txt, re.I)
        if m:
            return (int(m.group(1)), int(m.group(2)))
    except Exception:
        return None
    return None


def fetch_details_impl(headless=False, output_folder='./pbs_warn_outputs'):
    """
    Fetch detailed alerts and save a JSON payload (scrape_utc, page_updated, alerts).

    Args:
        headless (bool): Whether to run the browser in headless mode.
        output_folder (str): Folder to save output JSON files.

    Returns:
        list: A list of detailed alert dictionaries.
    """
    url = "https://warn.pbs.org/"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; EmergencyMLScraper/0.1)"}
    alerts = []
    site_timestamp = None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            page = browser.new_page()
            page.set_extra_http_headers(headers)
            page.goto(url, wait_until='networkidle', timeout=30000)

            try:
                page.on('console', lambda msg: logging.info(f"[browser console] {msg.type}: {msg.text}"))
            except Exception:
                pass

            # capture page timestamp if present
            try:
                timestamp_element = '_36XBCKh9PtUiaizdAv2d7t._3rGW2ARGcFG6V04zyupN-3'
                timestamp_div = f"div.{timestamp_element}"
                if page.query_selector(timestamp_div):
                    site_timestamp = page.query_selector(timestamp_div).inner_text()
            except Exception:
                site_timestamp = None

            # try open menu
            try:
                locator = page.locator("div:has-text(\"active alerts\")").first
                if locator.count() > 0:
                    try:
                        locator.locator('button').first.click()
                    except Exception:
                        try:
                            locator.click()
                        except Exception:
                            pass
                else:
                    btn = page.locator('button.ant-btn.ant-btn-icon-only').first
                    if btn.count() > 0:
                        try:
                            btn.click()
                        except Exception:
                            pass
            except Exception:
                pass

            try:
                page.wait_for_selector('#card-alerts-list, div.infinite-scroll-component__outerdiv', timeout=4000)
            except Exception:
                pass

            # Attempt to switch to the Carousel view first (try multiple
            # selectors and a JS click fallback). If the page switches to
            # carousel mode, we will iterate deterministically by using the
            # carousel indicator. Otherwise we'll fall back to index loop.
            carousel_switched = False
            try:
                carousel_btn_selectors = [
                    "#root > section > section > aside.ant-layout-sider.ant-layout-sider-dark.Gb6ok_P6af6seffG7YNra._26t5t_5MUYTCqs9AJH5DRO > div > div > div._323XwujjRZBLWALqFE5ESb.k2rNyTK4VfG39NuCnq2EA._3X5aNRykq33B670UdsI3wF > button",
                    "button:has-text('Carousel')",
                    "button[title*='carousel']",
                    "button[aria-label*='carousel']",
                ]
                for sel in carousel_btn_selectors:
                    try:
                        el = page.query_selector(sel)
                        if el:
                            try:
                                el.click()
                                page.wait_for_timeout(900)
                                logging.info(f"Switched to carousel view via selector: {sel}")
                                carousel_switched = True
                                break
                            except Exception:
                                # Try a JS click as a fallback
                                try:
                                    page.evaluate("(s) => { const e = document.querySelector(s); if (e) { e.click(); return true; } return false; }", sel)
                                    page.wait_for_timeout(900)
                                    logging.info(f"Switched to carousel view via JS click (selector): {sel}")
                                    carousel_switched = True
                                    break
                                except Exception:
                                    pass
                    except Exception:
                        continue
            except Exception:
                pass

            candidates = page.query_selector_all('div._3hppmX6GqLF_toD4XOvBXz')
            if not candidates:
                container = page.query_selector('#card-alerts-list') or page.query_selector('div.infinite-scroll-component__outerdiv')
                if container:
                    candidates = container.query_selector_all(':scope > *')

            # Filter out non-alert header cards (e.g., the 'Alert List' container)
            candidates = _filter_candidates(candidates)
            total = len(candidates)
            if total == 0:
                browser.close()
                return []
            # If we successfully switched to carousel view (or the page already
            # shows the carousel indicator), avoid clicking the card list — that
            # can toggle UI states and prevent the carousel from being active.
            carousel_active = carousel_switched or (_get_carousel_info(page) is not None)
            first = None
            if not carousel_active:
                first = candidates[0]
                try:
                    try:
                        first.scroll_into_view_if_needed()
                    except Exception:
                        pass
                    try:
                        title_node = first.query_selector("div[style*='background-color']") or first.query_selector(":scope > div")
                        if title_node:
                            try:
                                title_node.click()
                                page.wait_for_timeout(700)
                            except Exception:
                                first.click()
                                page.wait_for_timeout(700)
                        else:
                            first.click()
                            page.wait_for_timeout(700)
                    except Exception:
                        page.wait_for_timeout(300)
                except Exception:
                    pass

            def extract_current(card_el=None):
                details = None
                for attempt in range(4):
                    try:
                        panel_selector = 'div._3g3ZIcAdPcGK1KmFtttxbk._2kD36e8w0LlK3JPw_QHlKm, div._2kD36e8w0LlK3JPw_QHlKm'
                        try:
                            page.wait_for_selector(panel_selector, timeout=1200)
                            details = page.evaluate(GLOBAL_JS)
                        except Exception:
                            details = None
                    except Exception:
                        details = None

                    if not details or not (details.get('sender') or details.get('expires') or details.get('wea90')):
                        try:
                            if card_el:
                                details = card_el.evaluate(SCOPED_JS)
                        except Exception:
                            details = details or None

                    if details and (details.get('sender') or details.get('expires') or details.get('wea90')):
                        break

                    page.wait_for_timeout(250 * (attempt + 1))

                # final normalization
                if not isinstance(details, dict):
                    details = {}
                canonical_keys = ['title','message','sender','expires','sent','area','id','wea360','wea90','severity_color','raw_html','history','headline_en','description_en','instructions_en','contact','unknown_extras']
                for k in canonical_keys:
                    if k not in details:
                        details[k] = [] if k == 'history' else ({} if k == 'unknown_extras' else None)

                try:
                    for k in list(details.keys()):
                        if k not in canonical_keys:
                            details.setdefault('unknown_extras', {})
                            details['unknown_extras'][k] = details.pop(k)
                            logging.info(f"Moved unexpected top-level key '{k}' into unknown_extras")
                except Exception:
                    pass

                # If the panel extractor didn't find a message, try to recover a
                # message from the original card element (some UIs render the
                # short message inside the card instead of the detail panel).
                if (not details.get('message') or str(details.get('message')).strip() == '') and card_el is not None:
                    try:
                        card_msg = card_el.evaluate(r"el => { const possibleMsgs = Array.from(el.querySelectorAll('div')).filter(d => { const t=(d.textContent||'').trim(); return t.length>20 && !/SENDER|EXPIRES/i.test(t); }); return possibleMsgs.length>0 ? possibleMsgs[0].textContent.trim() : ''; }")
                        if card_msg:
                            details['message'] = card_msg
                    except Exception:
                        pass

                # If history is empty or incomplete, wait for all history items to load.
                # The history section may load progressively, so we need to wait for
                # the actual item count to match the header's declared count.
                try:
                    if (not details.get('history')) or len(details.get('history', [])) <= 1:
                        try:
                            # First, wait for the history list to appear
                            page.wait_for_selector(panel_selector + ' .ant-list-items li', timeout=1200)
                            
                            # Now wait for the item count to match the header's declared count
                            page.wait_for_function("""
                                () => {
                                    const panel = document.querySelector('div._3g3ZIcAdPcGK1KmFtttxbk._2kD36e8w0LlK3JPw_QHlKm, div._2kD36e8w0LlK3JPw_QHlKm');
                                    if (!panel) return false;
                                    
                                    const header = Array.from(panel.querySelectorAll('div')).find(d => /Alert\\s+History\\s*\\(\\d+\\)/i.test(d.textContent||''));
                                    if (!header) return true; // No header, proceed
                                    
                                    const m = (header.textContent||'').match(/Alert\\s+History\\s*\\((\\d+)\\)/i);
                                    const expectedCount = m ? parseInt(m[1], 10) : 0;
                                    if (expectedCount === 0) return true;
                                    
                                    const ul = panel.querySelector('ul.ant-list-items');
                                    if (!ul) return false;
                                    
                                    const actualCount = ul.querySelectorAll(':scope > li').length;
                                    return actualCount >= expectedCount;
                                }
                            """, timeout=3000)
                            
                            # re-evaluate the GLOBAL_JS to refresh history
                            refreshed = page.evaluate(GLOBAL_JS)
                            if isinstance(refreshed, dict) and refreshed.get('history'):
                                details['history'] = refreshed.get('history')
                        except Exception as e:
                            # Timeout or error; continue with what we have
                            logging.debug(f"History wait/refresh failed: {e}")
                            pass
                except Exception:
                    pass

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

                # Ensure at least one history item — some UIs implicitly include
                # the alert itself as the first history entry but our extractor
                # may miss it due to timing or DOM placement. If history is
                # empty, synthesize a minimal entry from the current details so
                # downstream code always has a predictable history list.
                try:
                    if not details.get('history'):
                        synth = {
                            'tag': 'ORIGINAL',
                            'title': details.get('title') or None,
                            'id': details.get('id') or None,
                            'sent': details.get('sent') or None,
                        }
                        # Only add if we have at least one useful field
                        if synth.get('title') or synth.get('id') or synth.get('sent'):
                            details['history'] = [synth]
                except Exception:
                    pass

                return details

            # extract first
            details = extract_current(card_el=first)
            alerts.append(details)

            # iterate remaining: using Carousel-driven loop when the page shows
            # a deterministic "Alert i of n" indicator. This avoids duplicates
            # and ensures we capture exactly n alerts. If the carousel is not
            # present, fall back to the previous index-based iteration.
            carousel = _get_carousel_info(page)
            if carousel:
                try:
                    cur_idx, total_count = carousel
                    # create a dedupe key maker
                    def _make_key(d):
                        if not d:
                            return None
                        if isinstance(d.get('id'), str) and d.get('id').strip():
                            return f"id:{d.get('id').strip()}"
                        raw = d.get('raw_html') or ''
                        if raw:
                            try:
                                return f"html:{hash(raw)}"
                            except Exception:
                                return None
                        return f"t:{(d.get('title') or '')}|s:{(d.get('sent') or '')}"

                    seen = set()
                    # record the first one we already extracted
                    first_key = _make_key(details)
                    if first_key:
                        seen.add(first_key)

                    # Next button selector — use as a fallback
                    next_btn_sel = "#root > section > section > aside.ant-layout-sider.ant-layout-sider-dark.Gb6ok_P6af6seffG7YNra._26t5t_5MUYTCqs9AJH5DRO > div > div > div.Vm0ocG4nLk4tOiMCx6F92 > div > div > div > div > div:nth-child(3) > button"

                    # loop until we've collected the expected total
                    while len(alerts) < total_count:
                        try:
                            # prefer a button labelled 'Next'
                            next_btn = page.locator("button:has-text('Next')").first
                            clicked_next = False
                            if next_btn.count() > 0:
                                try:
                                    next_btn.click()
                                    clicked_next = True
                                except Exception:
                                    try:
                                        # JS click fallback for the 'Next' button
                                        page.evaluate("() => { const b = Array.from(document.querySelectorAll('button')).find(x => /Next/.test(x.textContent||'')); if (b) { b.click(); return true; } return false; }")
                                        clicked_next = True
                                    except Exception:
                                        clicked_next = False

                            # if not clicked via labelled button, try selector
                            if not clicked_next:
                                try:
                                    el = page.query_selector(next_btn_sel)
                                    if el:
                                        try:
                                            el.click()
                                            clicked_next = True
                                        except Exception:
                                            try:
                                                page.evaluate("(s) => { const e = document.querySelector(s); if (e) { e.click(); return true; } return false; }", next_btn_sel)
                                                clicked_next = True
                                            except Exception:
                                                clicked_next = False
                                except Exception:
                                    clicked_next = False

                        except Exception:
                            pass

                        # wait briefly for the carousel index to change
                        old_idx = cur_idx
                        for _ in range(20):
                            page.wait_for_timeout(200)
                            info = _get_carousel_info(page)
                            if info and info[0] != old_idx:
                                cur_idx = info[0]
                                break

                        # extract the newly-displayed alert
                        details = extract_current(card_el=None)
                        key = _make_key(details)
                        if key and key not in seen:
                            alerts.append(details)
                            seen.add(key)
                        else:
                            logging.debug("Duplicate alert detected while using carousel; skipping append")
                except Exception:
                    logging.exception("Carousel-driven iteration failed; falling back to index loop")
                    # fall through to the index-based loop below

            if len(alerts) < total:
                # fallback: original index-based iteration (best-effort)
                for idx in range(1, total):
                    try:
                        next_btn = page.locator("button:has-text('Next')").first
                        clicked = False
                        try:
                            if next_btn.count() > 0:
                                next_btn.click()
                                clicked = True
                        except Exception:
                            clicked = False

                        if not clicked:
                            try:
                                cand = candidates[idx]
                                try:
                                    cand.scroll_into_view_if_needed()
                                except Exception:
                                    pass
                                cand.click()
                            except Exception:
                                pass

                        page.wait_for_timeout(700)
                        details = extract_current(card_el=(candidates[idx] if idx < len(candidates) else None))
                        alerts.append(details)
                    except Exception:
                        continue

            # save
            try:
                raw_ts = format_timestamp_for_filename(site_timestamp) if site_timestamp else datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
                ts_for_file = f"{raw_ts}Z" if not str(raw_ts).endswith('Z') else raw_ts
                out_folder = Path(output_folder)
                out_folder.mkdir(parents=True, exist_ok=True)
                out_file = out_folder / f"pbs_warn_alerts_{ts_for_file}.json"
                file_payload = {
                    'scrape_utc': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
                    'page_updated': site_timestamp if site_timestamp else None,
                    'alerts': alerts,
                }
                with open(out_file, 'w', encoding='utf-8') as fh:
                    json.dump(file_payload, fh, ensure_ascii=False, indent=2)
                logging.info(f"Saved {len(alerts)} detailed alerts to {out_file}")
            except Exception as e:
                logging.error(f"Failed saving detailed alerts JSON: {e}")

            browser.close()
            return alerts
    except Exception as e:
        logging.error(f"Error fetching detailed alerts: {e}")
        return []

# Public wrapper kept for backwards compatibility and simple imports.
def fetch_alerts_with_details(url: str = "https://warn.pbs.org/", headless: bool = False, output_folder: str = './pbs_warn_outputs', debug_folder: str = None):
    """Public API: fetch detailed alerts and save JSON payload.

    Args:
        url: The URL to scrape (default: PBS WARN).
        headless: If True, runs the browser in headless mode.
        output_folder: Folder to save the detailed alerts JSON files.

    Returns:
        A list of detailed alert dictionaries.
    """
    try:
        return fetch_details_impl(headless=headless, output_folder=output_folder)
    except Exception as e:
        logging.error(f"Error running fetch_alerts_with_details: {e}")
        return []

def run_and_print_details(headless: bool = False, output_folder: str = './pbs_warn_outputs'):
    """
    Wrapper to run the detailed scraper and print human-friendly output.

    Args:
        headless: If True, runs the browser in headless mode.
        output_folder: Folder to save the detailed alerts JSON files.
    """
    logging.info("Starting PBS WARN detailed alert fetch")
    alerts = fetch_alerts_with_details(headless=headless, output_folder=output_folder)
    print(f"Extracted {len(alerts)} detailed alerts from PBS WARN.")
    for alert in alerts:
        print(f"- Title: {alert.get('title')}")
        print(f"  Message: {alert.get('message')}")
        print(f"  Sender: {alert.get('sender')}")
        print(f"  Expires: {alert.get('expires')}")
        print(f"  Sent: {alert.get('sent')}")
        print(f"  Area: {alert.get('area')}")
        print(f"  ID: {alert.get('id')}")
        print(f"  WEA 360CH: {alert.get('wea360')}")
        print(f"  WEA 90CH: {alert.get('wea90')}")
        print(f"  Severity Color: {alert.get('severity_color')}")
        history = alert.get('history') or []
        print(f"  History Items: {len(history)} entries")
        for h in history:
            try:
                print(f"\t- {h.get('tag')}: {h.get('title')} (id={h.get('id')}, sent={h.get('sent')})")
            except Exception:
                pass
        print()

def main():
    run_and_print_details(headless=False)

if __name__ == "__main__":
    main()