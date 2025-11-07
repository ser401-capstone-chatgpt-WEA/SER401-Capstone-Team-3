"""
API-based scraper for PBS WARN alerts using the warn_out endpoint.

This module fetches alerts directly from the PBS WARN API. 
It maintains similar logging and output conventions as the existing scrapers.
"""

import json
import logging
import requests
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any
from urllib.parse import urlencode

# Configure logging
logging.basicConfig(
    filename='pbs_warn_scraper.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# API Configuration
BASE_URL = "https://nmknkohb83.execute-api.us-east-1.amazonaws.com/prod"
ENDPOINT = "/warn_out/"
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; EmergencyMLScraper/0.1)",
    "Accept": "application/json"
}


def fetch_alerts_api(
    status: str = "active",
    page: int = 1,
    per_page: int = 50,
    fetch_all_pages: bool = True,
    timeout: int = 30
) -> Dict[str, Any]:
    """
    Fetch alerts from the PBS WARN API.

    Args:
        status: Filter by alert status (default: "active")
        page: Page number to fetch (default: 1)
        per_page: Number of alerts per page (default: 50)
        fetch_all_pages: If True, automatically fetch all pages (default: True)
        timeout: Request timeout in seconds (default: 30)

    Returns:
        Dict containing the API response with alerts and metadata
    """
    # Build query parameters
    params = {
        "status": status,
        "page": page,
        "per_page": per_page
    }
    
    # Full URL
    url = f"{BASE_URL}{ENDPOINT}"
    all_alerts = []
    
    try:
        # Fetch first page
        logging.info(f"Fetching alerts from API: {url}?{urlencode(params)}")
        response = requests.get(url, params=params, headers=DEFAULT_HEADERS, timeout=timeout)
        response.raise_for_status()
        
        data = response.json()
        logging.info(f"Successfully fetched page {page} with {len(data.get('alerts', []))} alerts")
        
        # Collect alerts from first page
        all_alerts.extend(data.get('alerts', []))
        
        # Check if we need to fetch more pages
        if fetch_all_pages:
            pages_info = data.get('pages', {})
            total_pages = pages_info.get('pages', 1)
            current_page = pages_info.get('page', 1)
            
            # Fetch remaining pages
            while current_page < total_pages:
                current_page += 1
                params['page'] = current_page
                
                logging.info(f"Fetching page {current_page} of {total_pages}")
                response = requests.get(url, params=params, headers=DEFAULT_HEADERS, timeout=timeout)
                response.raise_for_status()
                
                page_data = response.json()
                page_alerts = page_data.get('alerts', [])
                all_alerts.extend(page_alerts)
                logging.info(f"Fetched {len(page_alerts)} alerts from page {current_page}")
        
        # Update the data dict with all collected alerts
        data['alerts'] = all_alerts
        
        # Update pagination info to reflect we fetched everything
        if fetch_all_pages and 'pages' in data:
            data['pages']['total_fetched'] = len(all_alerts)
        
        return data
        
    except requests.exceptions.HTTPError as e:
        logging.error(f"HTTP error fetching alerts: {e}")
        logging.error(f"Response status code: {e.response.status_code}")
        logging.error(f"Response text: {e.response.text}")
        raise
    except requests.exceptions.RequestException as e:
        logging.error(f"Request error fetching alerts: {e}")
        raise
    except json.JSONDecodeError as e:
        logging.error(f"JSON decode error: {e}")
        raise
    except Exception as e:
        logging.error(f"Unexpected error fetching alerts: {e}")
        raise


def save_alerts_to_file(
    api_response: Dict[str, Any],
    output_folder: str = './pbs_warn_outputs'
) -> Path:
    """
    Save API response to a JSON file with timestamp-based naming.

    Args:
        api_response: The complete API response dictionary
        output_folder: Folder to save output files (default: './pbs_warn_outputs')

    Returns:
        Path to the saved file
    """
    try:
        # Create output directory
        out_folder = Path(output_folder)
        out_folder.mkdir(parents=True, exist_ok=True)

        # Prefer API-provided timestamp for filename; fall back to current UTC
        api_ts = api_response.get('timestamp')
        dt_for_name = None
        if isinstance(api_ts, str) and api_ts:
            try:
                # Support timestamps with 'Z' by converting to +00:00
                ts_norm = api_ts.replace('Z', '+00:00')
                dt_for_name = datetime.fromisoformat(ts_norm)
            except Exception:
                dt_for_name = None
        if dt_for_name is None:
            dt_for_name = datetime.now(timezone.utc)

        timestamp_str = dt_for_name.strftime("%Y-%m-%d_%H%M%S")
        filename = f"pbs_warn_alerts_{timestamp_str}Z.json"
        output_file = out_folder / filename

        # Save API response as-is 
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(api_response, f, ensure_ascii=False, indent=2)

        logging.info(f"Saved {len(api_response.get('alerts', []))} alerts to {output_file}")
        return output_file

    except Exception as e:
        logging.error(f"Error saving alerts to file: {e}")
        raise


def fetch_and_save_alerts(
    status: str = "active",
    page: int = 1,
    per_page: int = 50,
    fetch_all_pages: bool = True,
    output_folder: str = './pbs_warn_outputs',
    timeout: int = 30
) -> tuple[Dict[str, Any], Path]:
    """
    Fetch alerts from API and save to file.

    Args:
        status: Filter by alert status (default: "active")
        page: Page number to fetch (default: 1)
        per_page: Number of alerts per page (default: 50)
        fetch_all_pages: If True, automatically fetch all pages (default: True)
        output_folder: Folder to save output files (default: './pbs_warn_outputs')
        timeout: Request timeout in seconds (default: 30)

    Returns:
        Tuple of (API response dict, output file path)
    """
    logging.info("Starting PBS WARN API fetch")
    
    # Fetch alerts
    data = fetch_alerts_api(
        status=status,
        page=page,
        per_page=per_page,
        fetch_all_pages=fetch_all_pages,
        timeout=timeout
    )
    
    # Save to file
    output_file = save_alerts_to_file(data, output_folder)
    
    logging.info(f"Completed API fetch: {len(data.get('alerts', []))} total alerts")
    return data, output_file


def print_alert_summary(api_response: Dict[str, Any]) -> None:
    """
    Print a human-readable summary of the fetched alerts.

    Args:
        api_response: The API response dictionary
    """
    alerts = api_response.get('alerts', [])
    pages_info = api_response.get('pages', {})
    timestamp = api_response.get('timestamp', 'N/A')
    last_heartbeat = api_response.get('last_heartbeat', 'N/A')
    
    print("\n" + "="*80)
    print("PBS WARN API Fetch Summary")
    print("="*80)
    print(f"API Timestamp: {timestamp}")
    print(f"Last Heartbeat: {last_heartbeat}")
    print(f"Total Alerts: {len(alerts)}")
    print(f"Pages Fetched: {pages_info.get('page', 'N/A')} of {pages_info.get('pages', 'N/A')}")
    print("="*80)
    
    for idx, alert in enumerate(alerts, 1):
        print(f"\n[Alert {idx}]")
        print(f"  Event: {alert.get('event', 'N/A')}")
        print(f"  Sender: {alert.get('sender', 'N/A')}")
        print(f"  Severity: {alert.get('severity', 'N/A')}")
        print(f"  Urgency: {alert.get('urgency', 'N/A')}")
        print(f"  Certainty: {alert.get('certainty', 'N/A')}")
        print(f"  Sent: {alert.get('sent', 'N/A')}")
        print(f"  Expires: {alert.get('expires', 'N/A')}")
        print(f"  Status: {alert.get('status', 'N/A')}")
        print(f"  CAP ID: {alert.get('cap_identifier', 'N/A')}")
        
        # Print text messages
        texts = alert.get('texts', [])
        if texts:
            print(f"  Messages ({len(texts)}):")
            for text in texts:
                text_type = text.get('type', 'N/A')
                text_value = text.get('value', 'N/A')
                print(f"  - [{text_type}]: {text_value[:100]}{'...' if len(text_value) > 100 else ''}")
        
        # Print areas
        areas = alert.get('areas', [])
        if areas:
            print(f"\tAreas ({len(areas)}):")
            for area in areas[:3]:  # Limit to first 3 for conciseness
                area_type = area.get('type')
                area_value = area.get('value')

                # Some responses provide geometry under a 'polygons' key without type='polygon'
                if 'polygons' in area:
                    polys = area.get('polygons') or []
                    rings = len(polys) if isinstance(polys, list) else 0
                    first_ring_pts = len(polys[0]) if rings and isinstance(polys[0], list) else 0
                    print(f"\t - Polygons: {rings} ring(s), first ring has {first_ring_pts} point(s)")
                elif area_type == 'area_description':
                    print(f"\t - {area_value}")
                elif area_type == 'polygon':
                    count = len(area_value) if isinstance(area_value, list) else 0
                    print(f"\t - Polygon with {count} point(s)")
                else:
                    # Generic fallback
                    atype = area_type if area_type else 'unknown'
                    print(f"\t - {atype}: {area_value}")
            if len(areas) > 3:
                print(f"\t ... and {len(areas) - 3} more areas")
        
        print("-" * 80)


def main():
    try:
        # Fetch and save alerts
        data, output_file = fetch_and_save_alerts()
        
        # Print summary to console
        print_alert_summary(data)
        print(f"\nData saved to: {output_file}")
        
    except Exception as e:
        logging.error(f"Error in main: {e}")
        print(f"Error: {e}")
        raise


if __name__ == "__main__":
    main()
