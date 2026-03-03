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
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

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
    Scheduled to run 5 minutes after scraper to ensure data availability.
    """
    logging.info("="*80)
    logging.info(f"[SCHEDULER] Starting RAG ingestion job at {get_timestamp()}")
    logging.info("="*80)
    
    try:
        result = subprocess.run(
            ['python3', '-m', 'rags.ingest_alerts'],
            capture_output=True,
            text=True,
            timeout=600,  # 10 minute timeout
            cwd=Path(__file__).parent
        )
        
        if result.returncode == 0:
            logging.info("[SCHEDULER] RAG ingestion completed successfully")
            if result.stdout:
                # Log key statistics from ingestion
                for line in result.stdout.split('\n'):
                    if 'Ingested' in line or 'documents' in line or 'files processed' in line:
                        logging.info(f"[SCHEDULER] {line.strip()}")
        else:
            logging.error(f"[SCHEDULER] RAG ingestion failed with return code {result.returncode}")
            if result.stderr:
                logging.error(f"[SCHEDULER] Ingestion error: {result.stderr}")
                
    except subprocess.TimeoutExpired:
        logging.error("[SCHEDULER] RAG ingestion timed out after 10 minutes")
    except Exception as e:
        logging.error(f"[SCHEDULER] Unexpected ingestion error: {e}", exc_info=True)
    finally:
        logging.info("="*80)


def run_cleanup():
    """
    Execute expired alert cleanup from vector database.
    
    Runs rags.cleanup module to remove expired alerts from Chroma.
    Scheduled every 2 hours to maintain database hygiene.
    """
    logging.info("="*80)
    logging.info(f"[SCHEDULER] Starting cleanup job at {get_timestamp()}")
    logging.info("="*80)
    
    try:
        result = subprocess.run(
            ['python3', '-m', 'rags.cleanup'],
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
            cwd=Path(__file__).parent
        )
        
        if result.returncode == 0:
            logging.info("[SCHEDULER] Cleanup completed successfully")
            if result.stdout:
                # Log cleanup statistics
                for line in result.stdout.split('\n'):
                    if 'removed' in line.lower() or 'expired' in line.lower() or 'Documents Remaining' in line:
                        logging.info(f"[SCHEDULER] {line.strip()}")
        else:
            logging.error(f"[SCHEDULER] Cleanup failed with return code {result.returncode}")
            if result.stderr:
                logging.error(f"[SCHEDULER] Cleanup error: {result.stderr}")
                
    except subprocess.TimeoutExpired:
        logging.error("[SCHEDULER] Cleanup timed out after 5 minutes")
    except Exception as e:
        logging.error(f"[SCHEDULER] Unexpected cleanup error: {e}", exc_info=True)
    finally:
        logging.info("="*80)


def main():
    """
    Initialize and run the scheduler with all configured jobs.
    
    Jobs:
    - Scraper: Every 30 minutes
    - Ingestion: Every 35 minutes (5 min offset from scraper)
    - Cleanup: Every 2 hours
    
    All jobs run on startup, then continue on schedule.
    """
    logging.info("="*80)
    logging.info("PBS WARN SCHEDULER STARTING")
    logging.info("="*80)
    logging.info(f"Start time: {get_timestamp()}")
    logging.info(f"Working directory: {Path.cwd()}")
    logging.info("")
    logging.info("Scheduled Jobs:")
    logging.info("  - Scraper:   Every 30 minutes")
    logging.info("  - Ingestion: Every 35 minutes (offset)")
    logging.info("  - Cleanup:   Every 2 hours")
    logging.info("="*80)
    
    # Initialize scheduler
    scheduler = BlockingScheduler(timezone='UTC')
    
    # Add scraper job (every 30 minutes)
    scheduler.add_job(
        run_scraper,
        trigger=IntervalTrigger(minutes=30),
        id='scraper',
        name='PBS WARN API Scraper',
        replace_existing=True,
        max_instances=1,  # Prevent overlapping executions
        coalesce=True     # Skip missed runs if system was down
    )

     # Add ingestion job (every 35 minutes, offset to allow scraper completion)
    scheduler.add_job(
        run_rag_ingestion,
        trigger=IntervalTrigger(minutes=35),
        id='ingestion',
        name='RAG Data Ingestion',
        replace_existing=True,
        max_instances=1,
        coalesce=True
    )
    
    # Add cleanup job (every 2 hours)
    scheduler.add_job(
        run_cleanup,
        trigger=IntervalTrigger(hours=2),
        id='cleanup',
        name='RAG Database Cleanup',
        replace_existing=True,
        max_instances=1,
        coalesce=True
    )
    
    # Run initial jobs immediately on startup
    logging.info("\n[SCHEDULER] Executing initial jobs...")
    try:
        run_scraper()
        # Small delay to ensure scraper completes before ingestion
        import time
        time.sleep(5)
        run_rag_ingestion()
    except Exception as e:
        logging.error(f"[SCHEDULER] Error during initial job execution: {e}", exc_info=True)
    
    logging.info("\n[SCHEDULER] Entering scheduled execution mode...")
    logging.info("[SCHEDULER] Press Ctrl+C to stop")

    # Start scheduler (blocking)
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logging.info("\n[SCHEDULER] Shutting down gracefully...")
        scheduler.shutdown(wait=True)
        logging.info("[SCHEDULER] Scheduler stopped")
        sys.exit(0)
    


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logging.error(f"[SCHEDULER] Fatal error: {e}", exc_info=True)
        sys.exit(1)