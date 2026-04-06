"""
Health monitoring script for PBS WARN services.

Checks two things:
1. Latest scrape output freshness (based on file mtime)
2. RAG service health endpoint status

Exit codes:
- 0: Healthy
- 1: Unhealthy
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Optional
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError


DEFAULT_HEALTH_URL = "http://localhost:8000/health"
DEFAULT_MAX_AGE_MINUTES = 40
DEFAULT_TIMEOUT_SECONDS = 5
DEFAULT_OUTPUTS_DIR = "pbs_warn_outputs"


def _find_latest_scrape(outputs_dir: Path) -> Optional[Path]:
    candidates = sorted(outputs_dir.glob("pbs_warn_alerts_*.json"))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _scrape_age_minutes(latest_file: Path) -> float:
    age_seconds = time.time() - latest_file.stat().st_mtime
    return age_seconds / 60.0


def _fetch_health(url: str, timeout_seconds: int) -> dict:
    request = Request(url, headers={"User-Agent": "pbs-warn-monitor"})
    with urlopen(request, timeout=timeout_seconds) as response:
        payload = response.read().decode("utf-8")
    return json.loads(payload)


def main() -> int:
    parser = argparse.ArgumentParser(description="PBS WARN health monitor")
    parser.add_argument(
        "--health-url",
        default=DEFAULT_HEALTH_URL,
        help=f"Health endpoint URL (default: {DEFAULT_HEALTH_URL})"
    )
    parser.add_argument(
        "--max-age-minutes",
        type=int,
        default=DEFAULT_MAX_AGE_MINUTES,
        help=f"Max allowed age for latest scrape output in minutes (default: {DEFAULT_MAX_AGE_MINUTES})"
    )
    parser.add_argument(
        "--outputs-dir",
        default=DEFAULT_OUTPUTS_DIR,
        help=f"Directory containing scrape outputs (default: {DEFAULT_OUTPUTS_DIR})"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"Health request timeout in seconds (default: {DEFAULT_TIMEOUT_SECONDS})"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON"
    )

    args = parser.parse_args()

    outputs_dir = Path(args.outputs_dir)
    latest_file = _find_latest_scrape(outputs_dir)
    scrape_ok = False
    scrape_age_minutes = None

    if latest_file is None:
        scrape_ok = False
    else:
        scrape_age_minutes = _scrape_age_minutes(latest_file)
        scrape_ok = scrape_age_minutes <= args.max_age_minutes

    health_ok = False
    health_status = None
    health_error = None

    try:
        health_status = _fetch_health(args.health_url, args.timeout)
        health_ok = health_status.get("status") == "healthy"
    except (URLError, HTTPError, json.JSONDecodeError) as exc:
        health_error = str(exc)
        health_ok = False

    result = {
        "scrape": {
            "ok": scrape_ok,
            "latest_file": str(latest_file) if latest_file else None,
            "age_minutes": round(scrape_age_minutes, 2) if scrape_age_minutes is not None else None,
            "max_age_minutes": args.max_age_minutes
        },
        "rag_health": {
            "ok": health_ok,
            "url": args.health_url,
            "status": health_status.get("status") if health_status else None,
            "error": health_error
        }
    }

    overall_ok = scrape_ok and health_ok

    if args.json:
        print(json.dumps({"ok": overall_ok, **result}, indent=2))
    else:
        if scrape_ok:
            print(f"OK  scrape age: {result['scrape']['age_minutes']} minutes")
        else:
            print("FAIL scrape freshness check")
        if health_ok:
            print(f"OK  rag health: {result['rag_health']['status']}")
        else:
            error_msg = result["rag_health"]["error"] or "status != healthy"
            print(f"FAIL rag health: {error_msg}")

    return 0 if overall_ok else 1


if __name__ == "__main__":
    sys.exit(main())
