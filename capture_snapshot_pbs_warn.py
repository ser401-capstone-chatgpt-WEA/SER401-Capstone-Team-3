"""
capture_snapshot_pbs_warn.py

Small utility to fetch a deterministic snapshot of https://warn.pbs.org/ using Playwright.

What it saves:
 - page HTML (timestamped)
 - a full-page screenshot (PNG)
 - browser storage state (cookies + localStorage)
 - optionally: recorded network responses stored under OUTDIR/warn_cache/ as JSON files

Recording modes:
 - --record-responses : record responses whose URL starts with the target --url (useful for origin-only captures)
 - --record-all       : record every network response seen during the run (useful to capture the whole site and assets)

Recorded response format (JSON): {"status": int, "headers": {...}, "body_b64": "..."}
A manifest.json mapping request URL -> cached filename is written when recording is enabled.

By default the script will create a timestamped subdirectory inside --outdir so repeated runs do not clutter.
If you prefer to reuse the same directory, pass --no-append-ts.

Usage examples:
    # Quick snapshot (interactive / headful)
    python capture_snapshot_pbs_warn.py

    # Headless snapshot and record only origin responses
    python capture_snapshot_pbs_warn.py --headless --record-responses

    # Headless snapshot and record all network responses (whole-site capture) with specified output directory
    python capture_snapshot_pbs_warn.py --headless --record-all --outdir ./warn_snapshot_full

Recommended examples (full site capture AND replay test):
    # Capture a full site snapshot
    python capture_snapshot_pbs_warn.py --headless --record-all

    # Run a replay test against an existing snapshot directory (replace with your snapshot path)
    python capture_snapshot_pbs_warn.py --test-snapshot ./warn_snapshot/YYYY-MM-DD_HHMMSSZ --headless
"""

from playwright.sync_api import sync_playwright
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import base64
import logging
from typing import Optional, Dict, Any

# Basic logging to console and file
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

DEFAULT_URL = "https://warn.pbs.org/"


def _url_to_cache_path(cache_dir: Path, url: str) -> Path:
    h = hashlib.sha1(url.encode("utf-8")).hexdigest()
    return cache_dir / f"{h}.json"


def record_response_to_cache(resp, cache_dir: Path, url_predicate=None):
    try:
        url = resp.url
        if url_predicate and not url_predicate(url):
            return
        body = resp.body()
        headers = dict(resp.headers)
        status = resp.status
        payload = {"status": status, "headers": headers, "body_b64": base64.b64encode(body).decode("ascii")}
        target = _url_to_cache_path(cache_dir, url)
        target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        logging.info(f"Recorded response for {url} -> {target.name}")
    except Exception as e:
        logging.warning(f"Failed to record response {getattr(resp, 'url', 'unknown')}: {e}")


def enable_cached_route(page, cache_dir: str, manifest_path: Optional[str] = None, allow_network_fallback: bool = False):
    """Enable request interception and fulfill requests from a cache directory.

    Args:
        page: Playwright Page instance to install the route on.
        cache_dir: Path to the directory containing cached response JSON files.
        manifest_path: Optional path to a manifest.json mapping request URL -> filename.
        allow_network_fallback: If True, requests with no cached file will be sent to the network; otherwise a 404 is returned.

    Returns:
        None. Installs a route handler on the provided page.
    """
    cache_dir_path = Path(cache_dir)
    manifest: Dict[str, str] = {}
    if manifest_path:
        try:
            manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        except Exception:
            manifest = {}

    def _sha1_name(url: str) -> str:
        return hashlib.sha1(url.encode("utf-8")).hexdigest() + ".json"

    def _find_cache_file(url: str) -> Optional[Path]:
        # prefer manifest mapping
        if manifest and url in manifest:
            candidate = cache_dir_path / manifest[url]
            if candidate.exists():
                return candidate
        # fallback to sha1 filename
        candidate = cache_dir_path / _sha1_name(url)
        if candidate.exists():
            return candidate
        return None

    def handler(route, request):
        try:
            url = request.url
            cache_file = _find_cache_file(url)
            if cache_file:
                data = json.loads(cache_file.read_text(encoding="utf-8"))
                status = int(data.get("status", 200))
                headers = data.get("headers", {}) or {}
                body_b64 = data.get("body_b64")
                if body_b64 is not None:
                    body = base64.b64decode(body_b64)
                else:
                    body = (data.get("body", "") or "").encode("utf-8")
                # strip hop-by-hop headers
                headers.pop("transfer-encoding", None)
                headers.pop("content-encoding", None)
                route.fulfill(status=status, headers=headers, body=body)
                return
        except Exception as e:
            logging.warning(f"Cache replay failed for {request.url}: {e}")
        if allow_network_fallback:
            route.continue_()
        else:
            route.fulfill(status=404, body=b"Not cached")

    page.route("**/*", handler)


def test_against_snapshot(snapshot_dir: str, url: str = DEFAULT_URL, headless: bool = True, allow_network_fallback: bool = False) -> Dict[str, Any]:
    """Run a quick test that loads a saved snapshot with cached responses.

    This function launches Playwright, installs a cached-response route using the
    `warn_cache` directory inside ``snapshot_dir`` and (if present) applies the
    saved storage_state. It then navigates to ``url`` and attempts to extract
    alerts using the scraper's extractor function.

    Args:
        snapshot_dir: Path to the snapshot folder (the one that contains `warn_cache/`).
        url: The page URL to navigate to. Defaults to the WARN homepage.
        headless: Whether to run the browser in headless mode.
        allow_network_fallback: If True, requests missing from the cache will be fetched from network.

    Returns:
        A dict with keys:
        - "html_len": length of the loaded page HTML
        - "alerts_count": number of alerts extracted by `extract_alerts_from_card_list`
        - "alerts_sample": a small sample (first alert) or None

    Raises:
        RuntimeError: if Playwright fails to start or navigation fails.
    """
    snap = Path(snapshot_dir)
    if not snap.exists() or not snap.is_dir():
        raise RuntimeError(f"Snapshot directory not found: {snapshot_dir}")

    cache_dir = snap / "warn_cache"
    manifest = snap / "manifest.json"

    # find storage_state if present
    storage_state_files = list(snap.glob("storage_state_*.json"))
    storage_state = str(storage_state_files[0]) if storage_state_files else None

    # launch and run
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = None
        try:
            if storage_state:
                context = browser.new_context(storage_state=storage_state)
            else:
                context = browser.new_context()
            page = context.new_page()
            # enable cached route
            if cache_dir.exists():
                enable_cached_route(page, str(cache_dir), manifest_path=str(manifest) if manifest.exists() else None, allow_network_fallback=allow_network_fallback)

            page.goto(url, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(500)
            html = page.content()
            alerts = []
            try:
                # NOTE: Snapshot capture + replay helpers are implemented in this
                # module (capture_snapshot, enable_cached_route, test_against_snapshot).
                # The goal of this script is to produce deterministic snapshots for
                # testing. It intentionally does not contain a full scraping pipeline.
                # Below we attempt to call an in-repo extractor if present so the
                # quick replay test can show a sample extraction, but absence of a
                # scraper is acceptable for the snapshot-only workflow.
                extractor = globals().get("extract_alerts_from_card_list")
                if callable(extractor):
                    try:
                        alerts = extractor(page)
                    except Exception:
                        alerts = []
                else:
                    alerts = []
            except Exception:
                alerts = []
            # save a debug screenshot into snapshot dir
            try:
                ss = snap / "test_replay_screenshot.png"
                page.screenshot(path=str(ss), full_page=True)
            except Exception:
                pass
            return {"html_len": len(html), "alerts_count": len(alerts), "alerts_sample": alerts[0] if alerts else None}
        finally:
            try:
                if context:
                    context.close()
            except Exception:
                pass
            browser.close()


def capture_snapshot(url: str = DEFAULT_URL, outdir: str = "warn_snapshot", headless: bool = True, record_responses: bool = False, record_all: bool = False, append_ts: bool = True):
    # If append_ts is True, create a timestamped subdirectory under outdir
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    if append_ts:
        ts_dir = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%SZ")
        outdir = outdir / ts_dir
    outdir.mkdir(parents=True, exist_ok=True)
    cache_dir = outdir / "warn_cache"
    if record_responses or record_all:
        cache_dir.mkdir(parents=True, exist_ok=True)
    # Will collect a manifest of recorded urls -> filename
    manifest = {}

    # filename-friendly timestamp
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%SZ")
    html_file = outdir / f"page_{ts}.html"
    screenshot_file = outdir / f"screenshot_{ts}.png"
    storage_file = outdir / f"storage_state_{ts}.json"

    headers = {"User-Agent": "Mozilla/5.0 (compatible; EmergencyMLScraper/0.1)"}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context()
        page = context.new_page()
        page.set_extra_http_headers(headers)

        if record_responses:
            def _on_response(resp):
                # record if same origin or useful resource
                try:
                    record_response_to_cache(resp, cache_dir, url_predicate=(lambda u: u.startswith(url)) if not record_all else None)
                    # record in-manifest mapping
                    try:
                        manifest[resp.url] = _url_to_cache_path(cache_dir, resp.url).name
                    except Exception:
                        pass
                except Exception:
                    pass
            page.on("response", _on_response)
        elif record_all:
            # attach same handler when record_all specified
            def _on_response_all(resp):
                try:
                    record_response_to_cache(resp, cache_dir, url_predicate=None)
                    try:
                        manifest[resp.url] = _url_to_cache_path(cache_dir, resp.url).name
                    except Exception:
                        pass
                except Exception:
                    pass
            page.on("response", _on_response_all)

        logging.info(f"Navigating to {url} (headless={headless})")
        page.goto(url, wait_until="networkidle", timeout=60000)

        # small wait to let any UI settle
        page.wait_for_timeout(500)

        # save HTML
        html = page.content()
        html_file.write_text(html, encoding="utf-8")
        logging.info(f"Saved page HTML -> {html_file}")

        # save screenshot
        try:
            page.screenshot(path=str(screenshot_file), full_page=True)
            logging.info(f"Saved screenshot -> {screenshot_file}")
        except Exception as e:
            logging.warning(f"Failed to save screenshot: {e}")

        # save storage state (cookies + localStorage)
        try:
            storage = context.storage_state()
            storage_file.write_text(json.dumps(storage, indent=2), encoding="utf-8")
            logging.info(f"Saved storage state -> {storage_file}")
        except Exception as e:
            logging.warning(f"Failed to save storage state: {e}")

        browser.close()

    # write manifest if recording
    if (record_responses or record_all) and manifest:
        try:
            manifest_file = outdir / "manifest.json"
            manifest_file.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            logging.info(f"Wrote manifest with {len(manifest)} entries -> {manifest_file}")
        except Exception as e:
            logging.warning(f"Failed to write manifest: {e}")

    return {"html": str(html_file), "screenshot": str(screenshot_file), "storage": str(storage_file), "cache_dir": str(cache_dir) if (record_responses or record_all) else None, "manifest": str(outdir / "manifest.json") if (record_responses or record_all) else None}

def main():
    parser = argparse.ArgumentParser(description="Capture a snapshot of PBS WARN for deterministic testing")
    parser.add_argument("--url", default=DEFAULT_URL, help="URL to snapshot")
    parser.add_argument("--outdir", default="warn_snapshot", help="Output directory")
    parser.add_argument("--headless", action="store_true", help="Run in headless mode")
    parser.add_argument("--record-responses", action="store_true", help="Record network responses into outdir/warn_cache")
    parser.add_argument("--record-all", action="store_true", help="Record all network responses seen during the run (full site capture)")
    parser.add_argument("--no-append-ts", action="store_true", help="Do not append a timestamp subdirectory to --outdir; write files directly into --outdir")
    parser.add_argument("--test-snapshot", default=None, help="Run a quick replay test against an existing snapshot directory and print results")
    args = parser.parse_args()

    if args.test_snapshot:
        # run the quick replay test against provided snapshot dir
        result = test_against_snapshot(args.test_snapshot, url=args.url, headless=args.headless, allow_network_fallback=False)
        print("Replay test result:", result)
    else:
        res = capture_snapshot(url=args.url, outdir=args.outdir, headless=args.headless, record_responses=args.record_responses, record_all=args.record_all, append_ts=not args.no_append_ts)
        print("Snapshot saved:", res)

if __name__ == "__main__":
    main()