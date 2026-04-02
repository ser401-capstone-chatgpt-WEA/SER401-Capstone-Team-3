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

import json
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


def _get_status_path() -> Path:
    return Path(__file__).resolve().parent / "pbs_warn_outputs" / "scheduler_status.json"


def _load_scheduler_status() -> dict:
    status_path = _get_status_path()
    if not status_path.exists():
        return {}
    try:
        return json.loads(status_path.read_text())
    except Exception as exc:
        logging.warning(f"[SCHEDULER] Failed to read scheduler status file: {exc}")
        return {}


def _write_scheduler_status(status_payload: dict) -> None:
    status_path = _get_status_path()
    status_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = status_path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(status_payload, indent=2))
    tmp_path.replace(status_path)


def _update_job_status(job_name: str, status: str, start_time: float, error: str | None = None) -> None:
    now_iso = get_timestamp()
    duration_ms = int((datetime.now(timezone.utc).timestamp() - start_time) * 1000)
    payload = _load_scheduler_status()
    jobs = payload.get("jobs", {})
    jobs[job_name] = {
        "status": status,
        "timestamp": now_iso,
        "duration_ms": duration_ms,
        "error": error
    }
    payload["jobs"] = jobs
    payload["last_updated"] = now_iso
    _write_scheduler_status(payload)


def run_scraper():
    """
    Execute the PBS WARN API scraper.
    
    Runs scrape_pbs_warn_api.py with report generation enabled.
    Includes timeout protection and error handling.
    """
    logging.info("="*80)
    logging.info(f"[SCHEDULER] Starting scraper job at {get_timestamp()}")
    logging.info("="*80)
    
    start_time = datetime.now(timezone.utc).timestamp()
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
            _update_job_status("scraper", "success", start_time)
        else:
            logging.error(f"[SCHEDULER] Scraper failed with return code {result.returncode}")
            if result.stderr:
                logging.error(f"[SCHEDULER] Scraper error: {result.stderr}")
            _update_job_status("scraper", "error", start_time, result.stderr)
                
    except subprocess.TimeoutExpired:
        logging.error("[SCHEDULER] Scraper timed out after 5 minutes")
        _update_job_status("scraper", "error", start_time, "Timeout expired")
    except FileNotFoundError:
        logging.error("[SCHEDULER] scrape_pbs_warn_api.py not found - check working directory")
        _update_job_status("scraper", "error", start_time, "scrape_pbs_warn_api.py not found")
    except Exception as e:
        logging.error(f"[SCHEDULER] Unexpected scraper error: {e}", exc_info=True)
        _update_job_status("scraper", "error", start_time, str(e))
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
    
    start_time = datetime.now(timezone.utc).timestamp()
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
            _update_job_status("ingestion", "success", start_time)
        else:
            logging.error(f"[SCHEDULER] RAG ingestion failed with return code {result.returncode}")
            if result.stderr:
                logging.error(f"[SCHEDULER] Ingestion error: {result.stderr}")
            _update_job_status("ingestion", "error", start_time, result.stderr)
                
    except subprocess.TimeoutExpired:
        logging.error("[SCHEDULER] RAG ingestion timed out after 10 minutes")
        _update_job_status("ingestion", "error", start_time, "Timeout expired")
    except Exception as e:
        logging.error(f"[SCHEDULER] Unexpected ingestion error: {e}", exc_info=True)
        _update_job_status("ingestion", "error", start_time, str(e))
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
    
    start_time = datetime.now(timezone.utc).timestamp()
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
            _update_job_status("cleanup", "success", start_time)
        else:
            logging.error(f"[SCHEDULER] Cleanup failed with return code {result.returncode}")
            if result.stderr:
                logging.error(f"[SCHEDULER] Cleanup error: {result.stderr}")
            _update_job_status("cleanup", "error", start_time, result.stderr)
                
    except subprocess.TimeoutExpired:
        logging.error("[SCHEDULER] Cleanup timed out after 5 minutes")
        _update_job_status("cleanup", "error", start_time, "Timeout expired")
    except Exception as e:
        logging.error(f"[SCHEDULER] Unexpected cleanup error: {e}", exc_info=True)
        _update_job_status("cleanup", "error", start_time, str(e))
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