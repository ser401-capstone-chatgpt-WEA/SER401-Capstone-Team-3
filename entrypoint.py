"""
Unified Entrypoint for PBS WARN Automation Service

Starts both the FastAPI RAG service and the background scheduler in a single process.
This eliminates the need for separate containers and simplifies deployment.

Architecture:
- Main thread: Runs FastAPI service with uvicorn
- Background thread: Runs APScheduler for periodic jobs
- Graceful shutdown: Stops both services cleanly on SIGTERM/SIGINT

Usage:
    python entrypoint.py                    # Start all services
    docker compose up automation            # Run in Docker
"""

import logging
import sys
import threading
import signal
from pathlib import Path

import uvicorn
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

# Import scheduler job functions
from scheduler import run_scraper, run_rag_ingestion, run_cleanup, get_timestamp

# Configure logging following PBS WARN conventions
logging.basicConfig(
    filename='pbs_warn_scraper.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Console logging for Docker logs
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logging.getLogger().addHandler(console_handler)

# Global scheduler reference for graceful shutdown
scheduler = None
uvicorn_server = None


def run_initial_jobs():
    """Execute initial scraper and ingestion jobs on startup."""
    logging.info("\n[ENTRYPOINT] Executing initial jobs...")
    try:
        run_scraper()
        # Small delay to ensure scraper completes before ingestion
        import time
        time.sleep(5)
        run_rag_ingestion()
    except Exception as e:
        logging.error(f"[ENTRYPOINT] Error during initial job execution: {e}", exc_info=True)


def start_scheduler():
    """
    Initialize and start the background scheduler.
    
    Runs in a separate thread to avoid blocking the FastAPI server.
    Schedules:
    - Scraper: Every 30 minutes
    - Ingestion: Every 35 minutes (offset)
    - Cleanup: Every 2 hours
    """
    global scheduler
    
    logging.info("="*80)
    logging.info("[ENTRYPOINT] Initializing Background Scheduler")
    logging.info("="*80)
    logging.info(f"Start time: {get_timestamp()}")
    logging.info(f"Working directory: {Path.cwd()}")
    logging.info("")
    logging.info("Scheduled Jobs:")
    logging.info("  - Scraper:   Every 30 minutes")
    logging.info("  - Ingestion: Every 35 minutes (offset)")
    logging.info("  - Cleanup:   Every 2 hours")
    logging.info("="*80)
    
    # Use BackgroundScheduler (non-blocking, runs in separate thread)
    scheduler = BackgroundScheduler(timezone='UTC')
    
    # Add scraper job
    scheduler.add_job(
        run_scraper,
        trigger=IntervalTrigger(minutes=30),
        id='scraper',
        name='PBS WARN API Scraper',
        replace_existing=True,
        max_instances=1,
        coalesce=True
    )
    
    # Add ingestion job
    scheduler.add_job(
        run_rag_ingestion,
        trigger=IntervalTrigger(minutes=35),
        id='ingestion',
        name='RAG Data Ingestion',
        replace_existing=True,
        max_instances=1,
        coalesce=True
    )
    
    # Add cleanup job
    scheduler.add_job(
        run_cleanup,
        trigger=IntervalTrigger(hours=2),
        id='cleanup',
        name='RAG Database Cleanup',
        replace_existing=True,
        max_instances=1,
        coalesce=True
    )
    
    # Run initial jobs before starting scheduler
    run_initial_jobs()
    
    # Start scheduler in background
    scheduler.start()
    logging.info("[ENTRYPOINT] Background scheduler started successfully")


def shutdown_handler(signum, frame):
    """Handle graceful shutdown on SIGTERM/SIGINT."""
    logging.info("\n[ENTRYPOINT] Shutdown signal received, stopping services...")
    
    # Stop scheduler
    if scheduler:
        scheduler.shutdown(wait=True)
        logging.info("[ENTRYPOINT] Scheduler stopped")
    
    # Stop uvicorn server
    if uvicorn_server:
        uvicorn_server.should_exit = True
        logging.info("[ENTRYPOINT] FastAPI server stopping...")
    
    sys.exit(0)


def main():
    """
    Main entrypoint: Start scheduler in background thread, then run FastAPI in main thread.
    
    This architecture allows both services to run in a single process:
    - FastAPI handles incoming HTTP requests for RAG queries
    - Scheduler runs periodic jobs in background
    - Both share the same Python environment and dependencies
    """
    global uvicorn_server
    
    logging.info("="*80)
    logging.info("PBS WARN AUTOMATION SERVICE STARTING")
    logging.info("="*80)
    logging.info("Components:")
    logging.info("  - FastAPI RAG Service (port 8000)")
    logging.info("  - Background Scheduler (scraper/ingestion/cleanup)")
    logging.info("="*80)
    
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)
    
    try:
        # Start scheduler in background thread
        scheduler_thread = threading.Thread(target=start_scheduler, daemon=True)
        scheduler_thread.start()
        logging.info("[ENTRYPOINT] Scheduler thread started")
        
        # Give scheduler time to initialize
        import time
        time.sleep(2)
        
        # Start FastAPI server in main thread (blocking)
        logging.info("[ENTRYPOINT] Starting FastAPI server on 0.0.0.0:8000")
        config = uvicorn.Config(
            "rags.service:app",
            host="0.0.0.0",
            port=8000,
            log_level="info",
            access_log=False  # Reduce log verbosity (already logged by middleware)
        )
        uvicorn_server = uvicorn.Server(config)
        uvicorn_server.run()
        
    except KeyboardInterrupt:
        logging.info("\n[ENTRYPOINT] KeyboardInterrupt received")
        shutdown_handler(None, None)
    except Exception as e:
        logging.error(f"[ENTRYPOINT] Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()