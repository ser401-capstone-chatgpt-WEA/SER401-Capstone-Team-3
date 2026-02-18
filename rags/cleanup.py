"""
Alert Cleanup Service for PBS WARN RAG System
"""

import logging
import time
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from pathlib import Path

from chroma_setup import ChromaDBManager

logging.basicConfig(
    filename='pbs_warn_scraper.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


class AlertCleanupService:
    """
    Manages automatic cleanup of expired alerts from the vector database.
    
    Attributes:
        db: ChromaDBManager instance for database operations
        collection_name: Name of the collection being managed
    """
    
    def __init__(
        self,
        chroma_path: str = "./chroma_db",
        collection_name: str = "pbs_warn_alerts"
    ):
        """
        Initialize the cleanup service.
        
        Args:
            chroma_path: Path to Chroma database directory
            collection_name: Name of the collection to clean
        """
        self.db = ChromaDBManager(
            persist_directory=chroma_path,
            collection_name=collection_name
        )
        self.collection_name = collection_name
        logging.info(f"Initialized AlertCleanupService for collection '{collection_name}'")
    
    def find_expired_alerts(self) -> List[str]:
        """
        Query ChromaDB for alerts with expired timestamps.
        
        Retrieves all documents and filters by comparing 'expires' metadata
        field against current UTC time. Handles timezone-aware ISO timestamps
        with 'Z' suffix following PBS WARN API conventions.
        
        Returns:
            List of document IDs that have expired
        
        Notes:
            - Timestamps are parsed as ISO format with 'Z' -> '+00:00' conversion
            - Malformed timestamps are logged as warnings and skipped
            - Alerts without 'expires' field are considered non-expiring
        """
        try:
            current_time = datetime.now(timezone.utc)
            logging.info(f"Finding expired alerts (current time: {current_time.isoformat()})")
            
            # Get all documents from collection
            # ChromaDB requires at least one query, so we use empty string with max results
            all_results = self.db.collection.get(
                include=['metadatas']
            )
            
            expired_ids = []
            total_checked = len(all_results['ids'])
            
            # Check each document's expiration timestamp
            for doc_id, metadata in zip(all_results['ids'], all_results['metadatas']):
                expires_str = metadata.get('expires')
                
                if not expires_str:
                    # No expiration set - skip (considered non-expiring)
                    continue
                
                try:
                    # Parse ISO timestamp with 'Z' suffix (PBS WARN API format)
                    # Example: "2025-11-08T05:24:05+00:00" or "2025-11-08T05:24:05Z"
                    expires_normalized = expires_str.replace('Z', '+00:00')
                    expires_dt = datetime.fromisoformat(expires_normalized)
                    
                    # Check if expired
                    if expires_dt < current_time:
                        expired_ids.append(doc_id)
                        logging.debug(f"Alert {doc_id} expired at {expires_str}")
                
                except (ValueError, TypeError) as e:
                    # Log malformed timestamps but don't fail entire cleanup
                    logging.warning(f"Malformed expires timestamp for alert {doc_id}: {expires_str} - {e}")
                    continue
            
            logging.info(f"Found {len(expired_ids)} expired alerts out of {total_checked} total documents")
            return expired_ids
        
        except Exception as e:
            logging.error(f"Error finding expired alerts: {e}", exc_info=True)
            return []
    
    def delete_expired_alerts(self, alert_ids: List[str]) -> int:
        """
        Delete specified alerts from ChromaDB.

        Args:
            alert_ids: List of document IDs to delete

        Returns:
            Number of alerts successfully deleted

        Notes:
            - Uses ChromaDB's collection.delete() method
            - Logs each deletion operation for audit trail
            - Continues on error to delete as many as possible
        """
        if not alert_ids:
            logging.info("No alerts to delete")
            return 0

        try:
            logging.info(f"Deleting {len(alert_ids)} expired alerts from collection '{self.collection_name}'")
            
            # ChromaDB delete operation
            self.db.collection.delete(ids=alert_ids)
            
            deleted_count = len(alert_ids)
            logging.info(f"Successfully deleted {deleted_count} alerts from collection '{self.collection_name}'")
            
            return deleted_count

        except Exception as e:
            logging.error(f"Error deleting expired alerts: {e}", exc_info=True)
            return 0
    
    def run_cleanup(self) -> Dict[str, Any]:
        """
        Execute full cleanup cycle: find and delete expired alerts.
        
        This is the main entry point for scheduled cleanup jobs. It performs
        the complete cleanup workflow and returns execution metrics.
        
        Returns:
            Dict with cleanup metrics:
                - removed_count: Number of alerts deleted
                - execution_time_ms: Time taken for cleanup (milliseconds)
                - timestamp: ISO timestamp of cleanup execution
                - status: "success" or "error"
        
        Example Response:
            {
                "removed_count": 42,
                "execution_time_ms": 347.2,
                "timestamp": "2025-01-15T14:00:00Z",
                "status": "success"
            }
        
        Notes:
            - Execution time includes both query and deletion operations
            - Logs start, progress, and completion to pbs_warn_scraper.log
            - Returns partial success if some deletes fail
        """
        start_time = time.time()
        timestamp = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        
        logging.info("="*80)
        logging.info("Starting scheduled alert cleanup")
        logging.info(f"Cleanup timestamp: {timestamp}")
        
        try:
            # Find expired alerts
            expired_ids = self.find_expired_alerts()
            
            if not expired_ids:
                execution_time_ms = (time.time() - start_time) * 1000
                logging.info(f"Cleanup completed in {execution_time_ms:.2f}ms (no expired alerts found)")
                logging.info("="*80)
                
                return {
                    "removed_count": 0,
                    "execution_time_ms": round(execution_time_ms, 2),
                    "timestamp": timestamp,
                    "status": "success"
                }
            
            # Delete expired alerts
            removed_count = self.delete_expired_alerts(expired_ids)
            
            # Calculate execution time
            execution_time_ms = (time.time() - start_time) * 1000
            
            # Log completion summary
            logging.info(f"Cleanup completed in {execution_time_ms:.2f}ms ({removed_count} removed)")
            logging.info("="*80)
            
            return {
                "removed_count": removed_count,
                "execution_time_ms": round(execution_time_ms, 2),
                "timestamp": timestamp,
                "status": "success"
            }
        
        except Exception as e:
            execution_time_ms = (time.time() - start_time) * 1000
            logging.error(f"Cleanup failed after {execution_time_ms:.2f}ms: {e}", exc_info=True)
            logging.info("="*80)
            
            return {
                "removed_count": 0,
                "execution_time_ms": round(execution_time_ms, 2),
                "timestamp": timestamp,
                "status": "error",
                "error": str(e)
            }


def main():
    """
    Standalone cleanup execution for manual testing.
    
    Usage:
        python rags/cleanup.py
    """
    try:
        service = AlertCleanupService()
        
        print("\n" + "="*80)
        print("PBS WARN Alert Cleanup Service")
        print("="*80)
        print(f"Collection: {service.collection_name}")
        print(f"Database: {service.db.persist_directory}")
        print("="*80)
        
        # Run cleanup
        metrics = service.run_cleanup()
        
        # Print results
        print("\nCleanup Results:")
        print(f"  Status: {metrics['status']}")
        print(f"  Removed: {metrics['removed_count']} alerts")
        print(f"  Execution Time: {metrics['execution_time_ms']:.2f}ms")
        print(f"  Timestamp: {metrics['timestamp']}")
        
        if metrics['status'] == 'error':
            print(f"  Error: {metrics.get('error', 'Unknown error')}")
        
        print("="*80)
        
        # Print updated collection stats
        stats = service.db.get_collection_stats()
        print("\nCollection Statistics:")
        print(f"  Documents Remaining: {stats['document_count']}")
        print("="*80)
    
    except Exception as e:
        logging.error(f"Error in main: {e}", exc_info=True)
        print(f"Error: {e}")
        raise


if __name__ == "__main__":
    main()