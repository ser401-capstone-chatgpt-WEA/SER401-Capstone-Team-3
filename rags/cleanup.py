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
        pass # TODO - query ChromaDB for alerts
    
    def run_cleanup(self) -> Dict[str, Any]:
        pass # TODO - run full cleanup


def main():
    pass

if __name__ == "__main__":
    main()