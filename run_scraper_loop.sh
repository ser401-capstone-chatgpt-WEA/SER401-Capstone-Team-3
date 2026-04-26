#!/bin/bash
# Run the PBS WARN scraper every 30 minutes
# Please use the following commands to run this script:
# --------------------------------------------------------------
# Basic Usage: ./run_scraper_loop.sh
# Background Usage (Recommended): nohup ./run_scraper_loop.sh > scraper_loop.log 2>&1 &
# Check output in real-time with: tail -f scraper_loop.log
# TO STOP: pkill -f run_scraper_loop.sh

cd "$(dirname "$0")"

echo "Starting PBS WARN scraper loop..."
echo "Running every 30 minutes. Press Ctrl+C to stop."

while true; do
    echo "=== Running scraper at $(date) ==="
    python3 scrape_pbs_warn_api.py
    echo "=== Completed at $(date). Waiting 30 minutes... ==="
    sleep 1800  # 30 minutes = 1800 seconds
done
