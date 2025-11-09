"""
Alert Summary Report Generator for PBS WARN alerts.

This module generates Markdown reports from PBS WARN alert JSON files.
Reports include aggregate statistics, groupings, and detailed alert listings.
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any
from collections import Counter

# Configure logging
logging.basicConfig(
    filename='pbs_warn_scraper.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Output configuration
DEFAULT_OUTPUT_FOLDER = './pbs_warn_reports'
DEFAULT_DATA_FOLDER = './pbs_warn_outputs'


def load_latest_alert_file(data_folder: str = DEFAULT_DATA_FOLDER) -> tuple[Dict[str, Any], Path]:
    """
    Load the most recent alert JSON file from the data folder.

    Args:
        data_folder: Folder containing alert JSON files (default: './pbs_warn_outputs')

    Returns:
        Tuple of (API response dict, file path)
    """
    try:
        data_path = Path(data_folder)
        json_files = sorted(data_path.glob("pbs_warn_alerts_*.json"), reverse=True)
        
        # Filter out diff files
        json_files = [f for f in json_files if not f.name.endswith('_diff.json')]
        
        if not json_files:
            logging.error(f"No alert files found in {data_folder}")
            raise FileNotFoundError(f"No alert files found in {data_folder}")
        
        latest_file = json_files[0]
        logging.info(f"Loading latest alert file: {latest_file}")
        
        with open(latest_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        return data, latest_file
        
    except Exception as e:
        logging.error(f"Error loading alert file: {e}")
        raise


def load_alert_file(file_path: str) -> tuple[Dict[str, Any], Path]:
    """
    Load a specific alert JSON file.

    Args:
        file_path: Path to the alert JSON file

    Returns:
        Tuple of (API response dict, file path)
    """
    try:
        file_path_obj = Path(file_path)
        logging.info(f"Loading alert file: {file_path_obj}")
        
        with open(file_path_obj, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        return data, file_path_obj
        
    except Exception as e:
        logging.error(f"Error loading alert file {file_path}: {e}")
        raise


def generate_markdown_report(api_response: Dict[str, Any], source_file: Path) -> str:
    """
    Generate a Markdown report from API response data.

    Args:
        api_response: The API response dictionary
        source_file: Path to the source JSON file

    Returns:
        Markdown report as a string
    """
    alerts = api_response.get('alerts', [])
    pages_info = api_response.get('pages', {})
    timestamp = api_response.get('timestamp', 'N/A')
    last_heartbeat = api_response.get('last_heartbeat', 'N/A')
    
    # Start building the markdown report
    md_lines = []
    
    # Header
    md_lines.append("# PBS WARN Alert Summary Report")
    md_lines.append("")
    md_lines.append(f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")
    md_lines.append(f"**Source File:** `{source_file.name}`")
    md_lines.append("")
    md_lines.append("---")
    md_lines.append("")
    
    # API Metadata
    md_lines.append("## API Metadata")
    md_lines.append("")
    md_lines.append(f"- **API Timestamp:** {timestamp}")
    md_lines.append(f"- **Last Heartbeat:** {last_heartbeat}")
    md_lines.append(f"- **Total Alerts:** {len(alerts)}")
    md_lines.append(f"- **Pages Fetched:** {pages_info.get('page', 'N/A')} of {pages_info.get('pages', 'N/A')}")
    md_lines.append("")
    md_lines.append("---")
    md_lines.append("")
    
    if not alerts:
        md_lines.append("## No Active Alerts")
        md_lines.append("")
        md_lines.append("There are currently no active alerts in the system.")
        return "\n".join(md_lines)
    
    # Aggregate Statistics
    md_lines.append("## Alert Statistics")
    md_lines.append("")
    
    # Count by severity
    severity_counts = Counter(alert.get('severity', 'Unknown') for alert in alerts)
    md_lines.append("### By Severity")
    md_lines.append("")
    for severity, count in severity_counts.most_common():
        md_lines.append(f"- **{severity}:** {count}")
    md_lines.append("")
    
    # Count by urgency
    urgency_counts = Counter(alert.get('urgency', 'Unknown') for alert in alerts)
    md_lines.append("### By Urgency")
    md_lines.append("")
    for urgency, count in urgency_counts.most_common():
        md_lines.append(f"- **{urgency}:** {count}")
    md_lines.append("")
    
    # Count by certainty
    certainty_counts = Counter(alert.get('certainty', 'Unknown') for alert in alerts)
    md_lines.append("### By Certainty")
    md_lines.append("")
    for certainty, count in certainty_counts.most_common():
        md_lines.append(f"- **{certainty}:** {count}")
    md_lines.append("")
    
    # Count by event type
    event_counts = Counter(alert.get('event', 'Unknown') for alert in alerts)
    md_lines.append("### By Event Type")
    md_lines.append("")
    for event, count in event_counts.most_common():
        md_lines.append(f"- **{event}:** {count}")
    md_lines.append("")
    
    # Count by category
    category_counts = Counter(alert.get('category', 'Unknown') for alert in alerts)
    md_lines.append("### By Category")
    md_lines.append("")
    for category, count in category_counts.most_common():
        md_lines.append(f"- **{category}:** {count}")
    md_lines.append("")
    
    # Top senders
    sender_counts = Counter(alert.get('sender', 'Unknown') for alert in alerts)
    md_lines.append("### Top Alert Senders")
    md_lines.append("")
    for sender, count in sender_counts.most_common(10):
        md_lines.append(f"- **{sender}:** {count}")
    md_lines.append("")
    
    # Geographic breakdown
    md_lines.append("### Geographic Distribution")
    md_lines.append("")
    state_codes = []
    geocodes = []
    for alert in alerts:
        areas = alert.get('areas', [])
        for area in areas:
            if area.get('type') == 'state':
                state_codes.append(area.get('value', 'Unknown'))
            elif area.get('type') == 'cmas_geocode':
                geocodes.append(area.get('value', 'Unknown'))
    
    if state_codes:
        state_counts = Counter(state_codes)
        md_lines.append("#### States Affected")
        md_lines.append("")
        for state, count in state_counts.most_common(10):
            md_lines.append(f"- **State Code {state}:** {count} area(s)")
        md_lines.append("")
    
    if geocodes:
        geocode_counts = Counter(geocodes)
        md_lines.append("#### Top CMAS Geocodes")
        md_lines.append("")
        for geocode, count in geocode_counts.most_common(10):
            md_lines.append(f"- **{geocode}:** {count} area(s)")
        md_lines.append("")
    
    # Temporal analysis
    md_lines.append("### Temporal Analysis")
    md_lines.append("")
    
    now = datetime.now(timezone.utc)
    expiring_soon = []
    recently_sent = []
    
    for alert in alerts:
        # Check expiration
        expires_str = alert.get('expires')
        if expires_str:
            try:
                expires_dt = datetime.fromisoformat(expires_str.replace('Z', '+00:00'))
                time_until_expiry = expires_dt - now
                if timedelta(0) < time_until_expiry <= timedelta(hours=24):
                    expiring_soon.append(alert)
            except Exception:
                pass
        
        # Check sent time
        sent_str = alert.get('sent')
        if sent_str:
            try:
                sent_dt = datetime.fromisoformat(sent_str.replace('Z', '+00:00'))
                time_since_sent = now - sent_dt
                if timedelta(0) <= time_since_sent <= timedelta(hours=24):
                    recently_sent.append(alert)
            except Exception:
                pass
    
    md_lines.append(f"- **Alerts expiring within 24 hours:** {len(expiring_soon)}")
    md_lines.append(f"- **Alerts sent within last 24 hours:** {len(recently_sent)}")
    md_lines.append("")
    md_lines.append("---")
    md_lines.append("")
    
    # Detailed Alert Listings
    md_lines.append("## Detailed Alert Listings")
    md_lines.append("")
    
    for idx, alert in enumerate(alerts, 1):
        md_lines.append(f"### Alert {idx}")
        md_lines.append("")
        md_lines.append(f"- **Event:** {alert.get('event', 'N/A')}")
        md_lines.append(f"- **Sender:** {alert.get('sender', 'N/A')}")
        md_lines.append(f"- **Severity:** {alert.get('severity', 'N/A')}")
        md_lines.append(f"- **Urgency:** {alert.get('urgency', 'N/A')}")
        md_lines.append(f"- **Certainty:** {alert.get('certainty', 'N/A')}")
        md_lines.append(f"- **Category:** {alert.get('category', 'N/A')}")
        md_lines.append(f"- **Status:** {alert.get('status', 'N/A')}")
        md_lines.append(f"- **Sent:** {alert.get('sent', 'N/A')}")
        md_lines.append(f"- **Expires:** {alert.get('expires', 'N/A')}")
        md_lines.append(f"- **CAP Identifier:** {alert.get('cap_identifier', 'N/A')}")
        md_lines.append("")
        
        # Messages
        texts = alert.get('texts', [])
        if texts:
            md_lines.append(f"**Messages ({len(texts)}):**")
            md_lines.append("")
            for text in texts:
                text_type = text.get('type', 'N/A')
                text_value = text.get('value', 'N/A')
                # Truncate long messages
                if len(text_value) > 200:
                    text_value = text_value[:200] + '...'
                md_lines.append(f"- **[{text_type}]:** {text_value}")
            md_lines.append("")
        
        # Areas
        areas = alert.get('areas', [])
        if areas:
            md_lines.append(f"**Areas ({len(areas)}):**")
            md_lines.append("")
            for area in areas[:5]:  # Limit to first 5 for readability
                area_type = area.get('type')
                area_value = area.get('value')
                
                if 'polygons' in area:
                    polys = area.get('polygons') or []
                    rings = len(polys) if isinstance(polys, list) else 0
                    first_ring_pts = len(polys[0]) if rings and isinstance(polys[0], list) else 0
                    md_lines.append(f"- **Polygons:** {rings} ring(s), first ring has {first_ring_pts} point(s)")
                elif area_type == 'area_description':
                    md_lines.append(f"- **Description:** {area_value}")
                elif area_type == 'polygon':
                    count = len(area_value) if isinstance(area_value, list) else 0
                    md_lines.append(f"- **Polygon:** {count} point(s)")
                elif area_type == 'state':
                    md_lines.append(f"- **State Code:** {area_value}")
                elif area_type == 'cmas_geocode':
                    md_lines.append(f"- **CMAS Geocode:** {area_value}")
                else:
                    atype = area_type if area_type else 'unknown'
                    md_lines.append(f"- **{atype}:** {area_value}")
            
            if len(areas) > 5:
                md_lines.append(f"- *... and {len(areas) - 5} more areas*")
            md_lines.append("")
        
        md_lines.append("---")
        md_lines.append("")
    
    return "\n".join(md_lines)


def save_markdown_report(
    markdown_content: str,
    output_folder: str = DEFAULT_OUTPUT_FOLDER,
    custom_filename: str = None
) -> Path:
    """
    Save the Markdown report to a file.

    Args:
        markdown_content: The Markdown content to save
        output_folder: Folder to save the report (default: './pbs_warn_reports')
        custom_filename: Optional custom filename (default: auto-generated with timestamp)

    Returns:
        Path to the saved report file
    """
    try:
        # Create output directory
        out_folder = Path(output_folder)
        out_folder.mkdir(parents=True, exist_ok=True)
        
        # Generate filename
        if custom_filename:
            filename = custom_filename
        else:
            timestamp_str = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
            filename = f"pbs_warn_report_{timestamp_str}Z.md"
        
        output_file = out_folder / filename
        
        # Save report
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(markdown_content)
        
        logging.info(f"Saved Markdown report to {output_file}")
        return output_file
        
    except Exception as e:
        logging.error(f"Error saving Markdown report: {e}")
        raise


def generate_report_from_file(
    file_path: str = None,
    output_folder: str = DEFAULT_OUTPUT_FOLDER,
    data_folder: str = DEFAULT_DATA_FOLDER
) -> Path:
    """
    Generate a Markdown report from an alert JSON file.

    Args:
        file_path: Path to specific alert file (default: None, uses latest)
        output_folder: Folder to save the report (default: './pbs_warn_reports')
        data_folder: Folder containing alert JSON files (default: './pbs_warn_outputs')

    Returns:
        Path to the generated report file
    """
    logging.info("Starting Markdown report generation")
    
    # Load alert data
    if file_path:
        api_response, source_file = load_alert_file(file_path)
    else:
        api_response, source_file = load_latest_alert_file(data_folder)
    
    # Generate Markdown content
    markdown_content = generate_markdown_report(api_response, source_file)
    
    # Save to file
    output_file = save_markdown_report(markdown_content, output_folder)
    
    logging.info(f"Completed Markdown report generation: {output_file}")
    return output_file


def main():
    try:
        # Generate report from latest alert file
        report_file = generate_report_from_file()
        
        print("\n" + "="*80)
        print("Alert Summary Report Generated")
        print("="*80)
        print(f"Report saved to: {report_file}")
        print("="*80)
        
    except Exception as e:
        logging.error(f"Error in main: {e}")
        print(f"Error generating report: {e}")
        raise


if __name__ == "__main__":
    main()
