"""
Performance Test for PBS WARN RAG System

Tests performance degradation under single user and concurrent load conditions.
"""
import time
import concurrent.futures
import logging
import os
from rags.retriever import AlertRetriever
from rags.generator import ResponseGenerator

# Configure logging
project_root = os.path.dirname(os.path.abspath(__file__))
log_file_path = os.path.join(project_root, 'pbs_warn_scraper.log')
logging.basicConfig(
    filename=log_file_path,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def test_single_query():
    """Test single user query performance."""
    try:
        retriever = AlertRetriever()
        generator = ResponseGenerator()
        query = "What are the current emergency alerts?"
        
        start_time = time.time()
        retrieved_docs = retriever.retrieve(query)
        response = generator.generate(query, retrieved_docs)
        end_time = time.time()
        
        duration = end_time - start_time
        logging.info(f"Single query response time: {duration:.2f} seconds")
        print(f"Single query response time: {duration:.2f} seconds")
        return duration
    except Exception as e:
        logging.error(f"Error in single query test: {e}")
        return None

def test_concurrent_load(num_concurrent=5):
    """Test concurrent load performance."""
    logging.info(f"Starting concurrent load test with {num_concurrent} queries")
    print(f"Starting concurrent load test with {num_concurrent} queries")
    
    start_time = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_concurrent) as executor:
        futures = [executor.submit(test_single_query) for _ in range(num_concurrent)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]
    end_time = time.time()
    
    total_duration = end_time - start_time
    valid_results = [r for r in results if r is not None]
    
    if valid_results:
        avg_duration = sum(valid_results) / len(valid_results)
        max_duration = max(valid_results)
        min_duration = min(valid_results)
        
        logging.info(f"Concurrent test results: total={total_duration:.2f}s, avg={avg_duration:.2f}s, max={max_duration:.2f}s, min={min_duration:.2f}s")
        print(f"Concurrent test results: total={total_duration:.2f}s, avg={avg_duration:.2f}s, max={max_duration:.2f}s, min={min_duration:.2f}s")
        
        # Check for degradation (assuming single query baseline ~2-3s, concurrent should not exceed 10s avg or something)
        if avg_duration > 10:
            logging.warning(f"Performance degradation detected: average query time {avg_duration:.2f}s exceeds threshold")
            print(f"WARNING: Performance degradation detected: average query time {avg_duration:.2f}s exceeds threshold")
    else:
        logging.error("No valid results from concurrent test")
        print("ERROR: No valid results from concurrent test")

if __name__ == "__main__":
    print("Running performance tests...")
    
    # Single user test
    print("\n--- Single User Test ---")
    single_time = test_single_query()
    
    # Concurrent load test
    print("\n--- Concurrent Load Test ---")
    test_concurrent_load(5)
    
    print("\nPerformance tests completed.")