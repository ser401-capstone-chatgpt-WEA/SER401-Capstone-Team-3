"""
Debug script to diagnose cleanup process issues.
"""

import logging
from datetime import datetime, timezone
from chroma_setup import ChromaDBManager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def debug_timestamps():
    """Check system time and database expiration timestamps."""
    
    # Check current system time
    current_time = datetime.now(timezone.utc)
    print("\n" + "="*80)
    print("DEBUG CLEANUP TIMESTAMP DEBUG REPORT")
    print("="*80)
    print(f"\nCurrent System Time (UTC): {current_time.isoformat()}")
    print(f"Current Unix Timestamp: {current_time.timestamp()}")
    
    # Connect to database
    db = ChromaDBManager(
        persist_directory="./chroma_db",
        collection_name="pbs_warn_alerts"
    )
    
    # Get all documents
    all_results = db.collection.get(include=['metadatas'])
    
    print(f"\nTotal Documents: {len(all_results['ids'])}")
    print("\n" + "-"*80)
    print("ALERT EXPIRATION ANALYSIS")
    print("-"*80)
    
    expired_count = 0
    active_count = 0
    no_expiry_count = 0
    malformed_count = 0
    
    samples = []
    
    for doc_id, metadata in zip(all_results['ids'], all_results['metadatas']):
        expires_str = metadata.get('expires')
        
        if not expires_str:
            no_expiry_count += 1
            continue
        
        try:
            # Parse timestamp (same logic as cleanup service)
            expires_normalized = expires_str.replace('Z', '+00:00')
            expires_dt = datetime.fromisoformat(expires_normalized)
            
            # Check if expired
            is_expired = expires_dt < current_time
            time_diff = (expires_dt - current_time).total_seconds()
            
            if is_expired:
                expired_count += 1
                status = "EXPIRED"
            else:
                active_count += 1
                status = "ACTIVE"
            
            # Collect samples for display
            if len(samples) < 10:  # Show first 10 alerts
                samples.append({
                    'id': doc_id[:30],  # Truncate long IDs
                    'expires': expires_str,
                    'status': status,
                    'diff_hours': time_diff / 3600
                })
        
        except (ValueError, TypeError) as e:
            malformed_count += 1
            logging.warning(f"Malformed timestamp for {doc_id}: {expires_str} - {e}")
    
    # Print summary
    print(f"\nExpired:     {expired_count}")
    print(f"Active:      {active_count}")
    print(f"No Expiry:   {no_expiry_count}")
    print(f"Malformed:   {malformed_count}")
    
    # Print samples
    if samples:
        print("\n" + "-"*80)
        print("SAMPLE ALERTS (first 10)")
        print("-"*80)
        print(f"{'Alert ID':<32} {'Expires':<28} {'Status':<10} {'Hours Diff'}")
        print("-"*80)
        for sample in samples:
            print(f"{sample['id']:<32} {sample['expires']:<28} {sample['status']:<10} {sample['diff_hours']:>10.1f}")
    
    print("\n" + "="*80)
    
    if expired_count == 0 and active_count > 0:
        print("\nWARNING: No expired alerts found, but there are active alerts.")
        print("   This could mean:")
        print("   1. All alerts have future expiration dates")
        print("   2. Alerts don't have 'expires' field set")
    
    print("="*80)


if __name__ == "__main__":
    debug_timestamps()