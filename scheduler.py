"""
Automated Scheduler for PBS WARN Scraper and RAG Services

Orchestrates periodic execution of:
- PBS WARN API scraping (every 30 minutes)
- RAG data ingestion (5 minutes after scraping)
- Expired alert cleanup (every 2 hours)

Usage:
    python scheduler.py                   # Run in foreground
    nohup python scheduler.py &           # Run in background
    
Stop:
    pkill -f scheduler.py
"""

import logging
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
# TODO import relevant from apscheduler

# Configure logging to match project conventions
logging.basicConfig(
    filename='pbs_warn_scraper.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Also log to console for monitoring
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logging.getLogger().addHandler(console_handler)


def get_timestamp() -> str:
    """Get current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def run_scraper():
    """
    Execute the PBS WARN API scraper.
    
    Runs scrape_pbs_warn_api.py with report generation enabled.
    Includes timeout protection and error handling.
    """
    logging.info("="*80)
    logging.info(f"[SCHEDULER] Starting scraper job at {get_timestamp()}")
    logging.info("="*80)
    
    try:
        result = subprocess.run(
            ['python3', 'scrape_pbs_warn_api.py', '--generate-report'],
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
            cwd=Path(__file__).parent
        )
        
        if result.returncode == 0:
            logging.info("[SCHEDULER] Scraper completed successfully")
            if result.stdout:
                logging.debug(f"[SCHEDULER] Scraper output: {result.stdout[:500]}")
        else:
            logging.error(f"[SCHEDULER] Scraper failed with return code {result.returncode}")
            if result.stderr:
                logging.error(f"[SCHEDULER] Scraper error: {result.stderr}")
                
    except subprocess.TimeoutExpired:
        logging.error("[SCHEDULER] Scraper timed out after 5 minutes")
    except FileNotFoundError:
        logging.error("[SCHEDULER] scrape_pbs_warn_api.py not found - check working directory")
    except Exception as e:
        logging.error(f"[SCHEDULER] Unexpected scraper error: {e}", exc_info=True)
    finally:
        logging.info("="*80)


def run_rag_ingestion():
    """
    Execute RAG data ingestion from scraped alerts.
    
    Runs rags.ingest_alerts module to index new alerts into Chroma.
    Scheduled to run X minutes after scraper to ensure data availability.
    """
    # TODO maybe 5 minutes
    pass


def run_cleanup():
    """
    Execute expired alert cleanup from vector database.
    
    Runs rags.cleanup module to remove expired alerts from Chroma.
    Scheduled every 2 hours to maintain database hygiene.
    """
   # TODO every 2 hours?
    pass


def main():
    """
    Initialize and run the scheduler with all configured jobs.
    
    Jobs:
    - Scraper: Every 30 minutes
    - Ingestion: Every 35 minutes (5 min offset from scraper)
    - Cleanup: Every 2 hours
    
    All jobs run on startup, then continue on schedule.
    """
    # TODO implement main scheduler logic
    pass


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logging.error(f"[SCHEDULER] Fatal error: {e}", exc_info=True)
        sys.exit(1)