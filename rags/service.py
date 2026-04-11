"""
FastAPI RAG Service for PBS WARN Alerts

This module provides a REST API for querying PBS WARN emergency alert data using
Retrieval-Augmented Generation (RAG). The service combines semantic search over
indexed alerts with LLM-based response generation to answer natural language
questions about emergency alerts.

Architecture:
- AlertRetriever: Performs semantic search against Chroma vector database
- ResponseGenerator: Generates grounded responses using Google Gemini
- Query validation and preprocessing for security and consistency
- In-memory query history tracking (last 100 queries)

Endpoints:
- POST /query: Query alerts with natural language
- GET /health: Service health check with component status
- GET /history: Retrieve past query history
- GET /: API information and endpoint documentation
"""
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
import logging
import json
import re
import uuid
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from rags.retriever import AlertRetriever
from rags.generator import ResponseGenerator
from rags.query_utils import preprocess_query, store_query_history, get_query_history
from rags.exceptions import (
    RAGServiceError,
    QueryValidationError,
    RetrieverError,
    GeneratorError,
    RateLimitExceededError,
    rag_exception_to_http
)

logging.basicConfig(
    filename='pbs_warn_scraper.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Ensure console logging for Docker environments
if not any(isinstance(handler, logging.StreamHandler) for handler in logging.getLogger().handlers):
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logging.getLogger().addHandler(console_handler)

app = FastAPI(
    title="PBS WARN RAG Service",
    description="Retrieval-Augmented Generation service for PBS WARN emergency alerts",
    version="1.0.0"
)

# Initialize components
retriever = AlertRetriever()
generator = ResponseGenerator()

# In-memory query history (limited to the last 100 queries)
query_history = deque(maxlen=100)

# Rate limiting configuration
RATE_LIMIT_REQUESTS = 60  # Max requests per window
RATE_LIMIT_WINDOW = 60    # Window size in seconds
rate_limit_store: Dict[str, List[float]] = {}  # IP -> list of request timestamps

# Query cache configuration
CACHE_TTL = 300  # Cache TTL in seconds (5 minutes)
CACHE_MAX_SIZE = 100  # Maximum number of cached queries
query_cache: Dict[str, Dict[str, Any]] = {}  # query_hash -> {response, timestamp}

# Cleanup service tracking
last_cleanup_result: Optional[Dict[str, Any]] = None
CLEANUP_STALE_THRESHOLD = 7200  # 2 hour in seconds

# Metrics tracking
metrics = {
    "total_queries": 0,
    "cache_hits": 0,
    "cache_misses": 0,
    "total_errors": 0,
    "total_response_time_ms": 0.0,
    "service_start_time": time.time()
}


def _get_scheduler_status_path() -> Path:
    return Path(__file__).resolve().parents[1] / "pbs_warn_outputs" / "scheduler_status.json"


def _load_scheduler_status() -> Dict[str, Any]:
    status_path = _get_scheduler_status_path()
    if not status_path.exists():
        return {}
    try:
        return json.loads(status_path.read_text())
    except Exception as exc:
        logging.warning(f"Failed to read scheduler status file: {exc}")
        return {}


def _parse_iso_timestamp(timestamp: Optional[str]) -> Optional[datetime]:
    if not timestamp:
        return None
    try:
        return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except Exception:
        return None


def _time_since_seconds(timestamp: Optional[str]) -> Optional[int]:
    parsed = _parse_iso_timestamp(timestamp)
    if not parsed:
        return None
    return int((datetime.now(timezone.utc) - parsed).total_seconds())


def get_cache_key(query: str, top_k: int, filters: Optional[Dict]) -> str:
    """
    Generate a cache key from query parameters.
    
    Args:
        query: The processed query string
        top_k: Number of documents to retrieve
        filters: Optional metadata filters
    
    Returns:
        A unique string key for the query
    """
    import hashlib
    import json
    filter_str = json.dumps(filters, sort_keys=True) if filters else ""
    key_str = f"{query}:{top_k}:{filter_str}"
    return hashlib.md5(key_str.encode()).hexdigest()


def get_cached_response(cache_key: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve a cached response if it exists and hasn't expired.
    
    Args:
        cache_key: The cache key to look up
    
    Returns:
        Cached response dict or None if not found/expired
    """
    if cache_key in query_cache:
        cached = query_cache[cache_key]
        if time.time() - cached['timestamp'] < CACHE_TTL:
            return cached['response']
        else:
            # Remove expired entry
            del query_cache[cache_key]
    return None


def store_cached_response(cache_key: str, response: Dict[str, Any]) -> None:
    """
    Store a response in the cache.
    
    Implements LRU-style eviction when cache is full.
    
    Args:
        cache_key: The cache key
        response: The response to cache
    """
    # Evict oldest entries if cache is full
    if len(query_cache) >= CACHE_MAX_SIZE:
        oldest_key = min(query_cache.keys(), key=lambda k: query_cache[k]['timestamp'])
        del query_cache[oldest_key]
    
    query_cache[cache_key] = {
        'response': response,
        'timestamp': time.time()
    }


@app.exception_handler(RAGServiceError)
async def rag_service_error_handler(request: Request, exc: RAGServiceError):
    """
    Global exception handler for RAG service errors.
    
    Converts custom RAGServiceError exceptions to appropriate HTTP responses
    with consistent error formatting.
    """
    request_id = getattr(request.state, 'request_id', 'unknown')
    logging.error(f"[{request_id}] {exc.__class__.__name__}: {exc.message}")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.__class__.__name__,
            "detail": exc.message,
            "request_id": request_id
        }
    )


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """
    HTTP request/response logging middleware with request ID tracking.
    
    Generates a unique request ID for each incoming request and includes it
    in logs and response headers for easier debugging and tracing.
    
    Args:
        request: Incoming FastAPI request
        call_next: Next middleware/handler in chain
    
    Returns:
        Response from downstream handlers with X-Request-ID header
    """
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    logging.info(f"[{request_id}] Incoming request: {request.method} {request.url}")
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    logging.info(f"[{request_id}] Response status: {response.status_code}")
    return response


def check_rate_limit(client_ip: str) -> bool:
    """
    Check if a client has exceeded the rate limit.
    
    Uses a sliding window algorithm to track requests per client IP.
    
    Args:
        client_ip: The client's IP address
    
    Returns:
        True if within rate limit, False if exceeded
    """
    current_time = time.time()
    window_start = current_time - RATE_LIMIT_WINDOW
    
    # Initialize or get existing timestamps
    if client_ip not in rate_limit_store:
        rate_limit_store[client_ip] = []
    
    # Remove timestamps outside the current window
    rate_limit_store[client_ip] = [
        ts for ts in rate_limit_store[client_ip] if ts > window_start
    ]
    
    # Check if within limit
    if len(rate_limit_store[client_ip]) >= RATE_LIMIT_REQUESTS:
        return False
    
    # Add current request timestamp
    rate_limit_store[client_ip].append(current_time)
    return True


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """
    Rate limiting middleware for the /query endpoint.
    
    Limits requests to RATE_LIMIT_REQUESTS per RATE_LIMIT_WINDOW seconds per client IP.
    Only applies to POST requests to /query endpoint.
    
    Args:
        request: Incoming FastAPI request
        call_next: Next middleware/handler in chain
    
    Returns:
        Response or 429 error if rate limit exceeded
    """
    # Only rate limit the /query endpoint
    if request.method == "POST" and request.url.path == "/query":
        client_ip = request.client.host if request.client else "unknown"
        
        if not check_rate_limit(client_ip):
            request_id = getattr(request.state, 'request_id', 'unknown')
            logging.warning(f"[{request_id}] Rate limit exceeded for {client_ip}")
            return JSONResponse(
                status_code=429,
                content={
                    "error": "RateLimitExceededError",
                    "detail": f"Rate limit exceeded. Maximum {RATE_LIMIT_REQUESTS} requests per {RATE_LIMIT_WINDOW} seconds.",
                    "request_id": request_id,
                    "retry_after": RATE_LIMIT_WINDOW
                },
                headers={"Retry-After": str(RATE_LIMIT_WINDOW)}
            )
    
    return await call_next(request)


class QueryRequest(BaseModel):
    """
    Request model for RAG query endpoint.
    
    Attributes:
        query: Natural language question about emergency alerts
        top_k: Number of relevant documents to retrieve (1-20, default: 5)
        filters: Optional metadata filters (e.g., {"severity": "Severe"})
        formatted: If True, returns human-readable summary instead of raw answer
    
    Example:
        {
            "query": "What severe weather alerts are active in Arizona?",
            "top_k": 3,
            "filters": {"severity": "Severe"},
            "formatted": true
        }
    """
    query: str = Field(..., description="Natural language query about emergency alerts")
    top_k: int = Field(default=5, ge=1, le=20, description="Number of documents to retrieve")
    filters: Optional[Dict[str, Any]] = Field(default=None, description="Optional metadata filters")
    formatted: bool = Field(default=True, description="Return formatted summary instead of raw answer")


class Source(BaseModel):
    """
    Model for a single source document citation.
    
    Attributes:
        id: Document identifier (typically CAP identifier)
        score: Relevance score from vector similarity search (0.0-1.0)
        metadata: Alert metadata including event, sender, severity, etc.
    """
    id: str
    score: float
    metadata: Dict[str, Any]


class QueryResponse(BaseModel):
    """
    Response model for RAG query endpoint.
    
    Attributes:
        answer: Generated natural language response
        sources: List of source documents used to ground the answer
        tokens_used: Approximate LLM token count for generation
        formatted_summary: Optional human-readable summary with citations
    
    Example:
        {
            "answer": "There are 2 active severe weather alerts...",
            "sources": [
                {"id": "abc123", "score": 0.95, "metadata": {...}},
                {"id": "def456", "score": 0.88, "metadata": {...}}
            ],
            "tokens_used": 245,
            "formatted_summary": "RAG RESPONSE SUMMARY\n..."
        }
    """
    answer: str
    sources: List[Source]
    tokens_used: int = 0
    formatted_summary: Optional[str] = None


def validate_query(query: str):
    """
    Validate and sanitize user query input.
    
    Performs multiple security and quality checks:
    - Non-empty query
    - Length constraints (3-1000 characters)
    - SQL injection pattern detection
    - Character whitelist enforcement
    
    Args:
        query: User-provided query string
    
    Raises:
        QueryValidationError: With specific validation failure message
    
    Security Notes:
        - Blocks common SQL injection patterns (DROP TABLE, --, ;)
        - Restricts to alphanumeric and basic punctuation
        - Case-insensitive pattern matching
    """
    if not query or len(query.strip()) == 0:
        raise QueryValidationError("Query cannot be empty.")
    if len(query) > 1000:
        raise QueryValidationError("Query exceeds maximum length of 1,000 characters.")
    if len(query) < 3:
        raise QueryValidationError("Query must be at least 3 characters long.")

    # Check for prohibited characters or patterns
    prohibited_patterns = [r"DROP TABLE", r"--", r";"]
    for pattern in prohibited_patterns:
        if re.search(pattern, query, re.IGNORECASE):
            raise QueryValidationError("Query contains prohibited patterns or characters.")

    # Ensure query contains only allowed characters
    if not re.match(r"^[a-zA-Z0-9 .,?!'\"-]+$", query):
        raise QueryValidationError("Query contains unsupported characters.")


@app.post("/query", response_model=QueryResponse)
async def query_rag(request: QueryRequest, http_request: Request):
    """
    Query the RAG system for emergency alert information.
    
    This endpoint performs a multi-step RAG pipeline:
    1. Preprocesses and validates the query
    2. Retrieves semantically relevant alert documents from Chroma
    3. Generates a grounded response using Google Gemini
    4. Stores query/response in history for analytics
    
    Args:
        request: QueryRequest containing query text, top_k, filters, and formatting options
        http_request: FastAPI Request object for accessing request ID
    
    Returns:
        QueryResponse with generated answer, source citations, token usage, and optional formatted summary
    
    Raises:
        HTTPException: 
            - 400 for invalid query format
            - 500 for internal processing errors
    
    Example:
        POST /query
        {
            "query": "Are there any tornado warnings near Phoenix?",
            "top_k": 5,
            "filters": {"severity": "Severe"}
        }
        
        Response:
        {
            "answer": "Yes, there is 1 active tornado warning...",
            "sources": [...],
            "tokens_used": 234
        }
    
    Notes:
        - All queries are logged to pbs_warn_scraper.log with request ID
        - Query history is stored in-memory (last 100 queries)
        - Filters apply to alert metadata (severity, urgency, event, sender, etc.)
        - Responses are cached for CACHE_TTL seconds to reduce redundant lookups
    """
    request_id = getattr(http_request.state, 'request_id', 'unknown')
    start_time = time.time()
    metrics["total_queries"] += 1
    
    try:
        # Preprocess the query
        processed_query = preprocess_query(request.query)
        logging.info(f"[{request_id}] Processed query: {processed_query}")

        # Validate the query
        validate_query(processed_query)
        logging.info(f"[{request_id}] Query parameters: top_k={request.top_k}, filters={request.filters}")
        
        # Check cache first
        cache_key = get_cache_key(processed_query, request.top_k, request.filters)
        cached_response = get_cached_response(cache_key)
        if cached_response:
            logging.info(f"[{request_id}] Cache hit for query")
            metrics["cache_hits"] += 1
            elapsed_ms = (time.time() - start_time) * 1000
            metrics["total_response_time_ms"] += elapsed_ms
            return QueryResponse(**cached_response)
        
        metrics["cache_misses"] += 1
        logging.info(f"[{request_id}] Cache miss, querying RAG system")
        
        # Retrieve relevant documents
        retrieved = retriever.retrieve(
            query=processed_query,
            top_k=request.top_k,
            filters=request.filters
        )
        logging.info(f"[{request_id}] Retrieved {len(retrieved)} documents")
        
        # Generate grounded response
        response = generator.generate(
            query=processed_query,
            retrieved_docs=retrieved
        )
        logging.info(f"[{request_id}] Generated response successfully")

        formatted_summary = format_response_summary(response, retrieved)
        response["formatted_summary"] = formatted_summary

        # Format the query if needed
        if request.formatted:
            response["answer"] = formatted_summary
        
        # Store in cache
        store_cached_response(cache_key, response)
        logging.info(f"[{request_id}] Response cached")

        # Store query and result in history
        store_query_history(
            query=processed_query,
            parameters={
                "top_k": request.top_k,
                "filters": request.filters
            },
            response=response
        )
        
        # Track response time
        elapsed_ms = (time.time() - start_time) * 1000
        metrics["total_response_time_ms"] += elapsed_ms
        
        return QueryResponse(**response)
        
    except Exception as e:
        metrics["total_errors"] += 1
        logging.error(f"[{request_id}] Query error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def format_response_summary(response: dict, retrieved: list) -> str:
    """
    Format RAG response into human-readable summary.
    
    Creates a structured text summary including:
    - Generated answer text
    - Source document citations with relevance scores
    - Token usage statistics
    
    Args:
        response: Generator response dict with answer, sources, tokens_used
        retrieved: List of retrieved documents (unused but kept for compatibility)
    
    Returns:
        Multi-line formatted string with bordered sections
    
    Format:
        ================================================================================
        RAG RESPONSE SUMMARY
        ================================================================================
        
        Answer:
        [Generated response text]
        
        Sources (N):
          [1] Event Name - Sender (score: 0.xxx)
          [2] Event Name - Sender (score: 0.xxx)
          ...
        
        Tokens Used: XXX
        ================================================================================
    
    Notes:
        - Returns error message if formatting fails (graceful degradation)
        - Scores are 3 decimal places for readability
    """
    try:
        lines = []
        lines.append("="*80)
        lines.append("RAG RESPONSE SUMMARY")
        lines.append("="*80)
        lines.append(f"\nAnswer:\n{response.get('answer', 'N/A')}\n")
        lines.append(f"Sources ({len(response.get('sources', []))}):")
        for idx, source in enumerate(response.get('sources', []), 1):
            meta = source.get('metadata', {})
            lines.append(f"  [{idx}] {meta.get('event', 'N/A')} - {meta.get('sender', 'N/A')} (score: {source.get('score', 0):.3f})")
        lines.append(f"\nTokens Used: {response.get('tokens_used', 0)}")
        lines.append("="*80)
        return "\n".join(lines)
    except Exception as e:
        logging.error(f"Error formatting summary: {e}")
        return "Error generating formatted summary."


@app.get("/history")
async def get_query_history_endpoint():
    """
    Retrieve recent query history.
    
    Returns the last 100 queries and their results for analytics and debugging.
    History is stored in-memory and lost on service restart.
    
    Returns:
        List[Dict]: Query history with query text, parameters, and responses
    
    Example Response:
        [
            {
                "query": "what severe weather alerts are active",
                "parameters": {"top_k": 5, "filters": null},
                "response": {"answer": "...", "sources": [...]}
            },
            ...
        ]
    
    Notes:
        - Limited to 100 most recent queries (FIFO queue)
        - Useful for monitoring popular queries and system usage
        - Consider adding authentication for production deployments
    """
    return get_query_history()


@app.get("/metrics")
async def get_metrics():
    """
    Retrieve service usage metrics.
    
    Returns statistics about service usage including query counts,
    cache performance, error rates, and response times.
    
    Returns:
        Dict containing usage metrics and calculated statistics
    
    Example Response:
        {
            "total_queries": 1523,
            "cache_hits": 892,
            "cache_misses": 631,
            "cache_hit_rate": 0.585,
            "total_errors": 12,
            "error_rate": 0.008,
            "average_response_time_ms": 245.3,
            "uptime_seconds": 86400,
            "current_cache_size": 87,
            "rate_limit_config": {
                "requests_per_window": 60,
                "window_seconds": 60
            }
        }
    
    Notes:
        - Metrics are reset on service restart
        - Cache hit rate = cache_hits / total_queries
        - Error rate = total_errors / total_queries
        - Average response time includes both cache hits and misses
    """
    total_queries = metrics["total_queries"]
    cache_hit_rate = metrics["cache_hits"] / total_queries if total_queries > 0 else 0
    error_rate = metrics["total_errors"] / total_queries if total_queries > 0 else 0
    avg_response_time = metrics["total_response_time_ms"] / total_queries if total_queries > 0 else 0
    uptime = time.time() - metrics["service_start_time"]
    
    return {
        "total_queries": total_queries,
        "cache_hits": metrics["cache_hits"],
        "cache_misses": metrics["cache_misses"],
        "cache_hit_rate": round(cache_hit_rate, 3),
        "total_errors": metrics["total_errors"],
        "error_rate": round(error_rate, 3),
        "average_response_time_ms": round(avg_response_time, 1),
        "uptime_seconds": round(uptime, 0),
        "current_cache_size": len(query_cache),
        "rate_limit_config": {
            "requests_per_window": RATE_LIMIT_REQUESTS,
            "window_seconds": RATE_LIMIT_WINDOW
        }
    }


@app.get("/scheduler/metrics")
async def get_scheduler_metrics():
    """
    Retrieve scheduler job metrics.

    Returns the latest scheduler status information, including per-job
    status, timestamps, durations, and time-since fields derived from
    scheduler_status.json.
    """
    scheduler_status = _load_scheduler_status()
    scheduler_jobs = scheduler_status.get("jobs", {})
    job_metrics = {}
    error_jobs = []

    for job_name, job_data in scheduler_jobs.items():
        status = job_data.get("status")
        if status == "error":
            error_jobs.append(job_name)
        job_metrics[job_name] = {
            "status": status,
            "timestamp": job_data.get("timestamp"),
            "duration_ms": job_data.get("duration_ms"),
            "error": job_data.get("error"),
            "time_since_seconds": _time_since_seconds(job_data.get("timestamp"))
        }

    return {
        "last_updated": scheduler_status.get("last_updated"),
        "time_since_last_updated_seconds": _time_since_seconds(scheduler_status.get("last_updated")),
        "job_count": len(scheduler_jobs),
        "error_jobs": error_jobs,
        "jobs": job_metrics
    }


@app.get("/health")
async def health():
    """
    Service health check endpoint.
    
    Checks health of all RAG system components:
    - AlertRetriever: Database connectivity and document count
    - ResponseGenerator: LLM API availability
    - AlertCleanupService: Last cleanup execution status and metrics
    
    Returns:
        Dict with component statuses and database statistics
    
     Example Response:
        {
            "status": "healthy",
            "retriever_status": "healthy",
            "generator_status": "healthy",
            "cleanup_status": "healthy",
            "documents_indexed": 1523,
            "collection_name": "pbs_warn_alerts",
            "last_cleanup_timestamp": "2025-01-15T14:00:00Z",
            "last_cleanup_metrics": {
                "removed_count": 42,
                "execution_time_ms": 347.2
            }
        }
    
    Status Values:
        - "healthy": All components operational
        - "never_run": Cleanup service hasn't executed yet (startup grace period)
        - "unhealthy": One or more components failed health check or cleanup is stale
    
    Cleanup Health Logic:
        - "never_run": No cleanup has occurred yet
        - "unhealthy": Last cleanup was more than 2 hours ago
        - "healthy": Last cleanup was within 2 hours and successful
    
    HTTP Status:
        - Always returns 200 (use response body to check actual health)
    
    Notes:
        - Component failures are logged to pbs_warn_scraper.log
        - Monitor this endpoint for production alerting
        - Check documents_indexed to ensure ingestion is working
        - Cleanup status helps detect scheduler failures
    """
    try:
        # Check retriever database stats
        stats = retriever.db.get_collection_stats()
        retriever_status = "healthy"
    except Exception as e:
        logging.error(f"Retriever health check error: {e}")
        retriever_status = "unhealthy"

    try:
        # Check generator readiness
        generator_status = generator.check_health()
    except Exception as e:
        logging.error(f"Health check error: {e}")
        generator_status = "unhealthy"

    # Check cleanup service status
    cleanup_status = "never_run"
    last_cleanup_timestamp = None
    last_cleanup_metrics = None
    
    if last_cleanup_result is not None:
        last_cleanup_timestamp = last_cleanup_result.get('timestamp')
        last_cleanup_metrics = {
            'removed_count': last_cleanup_result.get('removed_count', 0),
            'execution_time_ms': last_cleanup_result.get('execution_time_ms', 0.0)
        }
        
        # Check if cleanup is stale (more than 2 hours ago)
        try:
            # Parse last cleanup timestamp
            cleanup_time_str = last_cleanup_result.get('timestamp', '').replace('Z', '+00:00')
            cleanup_time = datetime.fromisoformat(cleanup_time_str)
            current_time = datetime.now(timezone.utc)
            time_since_cleanup = (current_time - cleanup_time).total_seconds()
            
            if time_since_cleanup > CLEANUP_STALE_THRESHOLD:
                cleanup_status = "unhealthy"
                logging.warning(f"Cleanup service stale: last run {time_since_cleanup:.0f}s ago (threshold: {CLEANUP_STALE_THRESHOLD}s)")
            elif last_cleanup_result.get('status') == 'error':
                cleanup_status = "unhealthy"
                logging.warning(f"Last cleanup failed: {last_cleanup_result.get('error', 'Unknown error')}")
            else:
                cleanup_status = "healthy"
        except Exception as e:
            logging.error(f"Error checking cleanup staleness: {e}")
            cleanup_status = "unhealthy"

    scheduler_status = _load_scheduler_status()
    scheduler_jobs = scheduler_status.get("jobs", {})
    scraper_job = scheduler_jobs.get("scraper", {})
    ingestion_job = scheduler_jobs.get("ingestion", {})
    cleanup_job = scheduler_jobs.get("cleanup", {})

    # Determine overall status
    overall_status = "healthy"
    if retriever_status != "healthy" or generator_status != "healthy":
        overall_status = "unhealthy"
    # Note: cleanup_status of "never_run" doesn't fail overall health (startup grace period)
    if cleanup_status == "unhealthy":
        overall_status = "unhealthy"

    return {
        "status": overall_status,
        "retriever_status": retriever_status,
        "generator_status": generator_status,
        "cleanup_status": cleanup_status,
        "documents_indexed": stats['document_count'] if retriever_status == "healthy" else None,
        "collection_name": retriever.db.collection_name if retriever_status == "healthy" else None,
        "last_cleanup_timestamp": last_cleanup_timestamp,
        "last_cleanup_metrics": last_cleanup_metrics,
        "last_scrape_timestamp": scraper_job.get("timestamp"),
        "last_ingestion_timestamp": ingestion_job.get("timestamp"),
        "last_scheduler_update": scheduler_status.get("last_updated"),
        "scraper_status": scraper_job.get("status"),
        "ingestion_status": ingestion_job.get("status"),
        "scheduler_cleanup_status": cleanup_job.get("status"),
        "time_since_last_scrape_seconds": _time_since_seconds(scraper_job.get("timestamp")),
        "time_since_last_ingestion_seconds": _time_since_seconds(ingestion_job.get("timestamp")),
        "time_since_last_scheduler_update_seconds": _time_since_seconds(scheduler_status.get("last_updated")),
        "scheduler_jobs": {
            "scraper": {
                "status": scraper_job.get("status"),
                "timestamp": scraper_job.get("timestamp"),
                "duration_ms": scraper_job.get("duration_ms"),
                "error": scraper_job.get("error")
            },
            "ingestion": {
                "status": ingestion_job.get("status"),
                "timestamp": ingestion_job.get("timestamp"),
                "duration_ms": ingestion_job.get("duration_ms"),
                "error": ingestion_job.get("error")
            },
            "cleanup": {
                "status": cleanup_job.get("status"),
                "timestamp": cleanup_job.get("timestamp"),
                "duration_ms": cleanup_job.get("duration_ms"),
                "error": cleanup_job.get("error")
            }
        }
    }

def update_cleanup_metrics(cleanup_result: Dict[str, Any]) -> None:
    """
    Update the last cleanup result for health reporting.
    
    This function is called by the scheduler after each cleanup execution
    to update the service's cleanup status tracking.
    
    Args:
        cleanup_result: Dict from AlertCleanupService.run_cleanup() containing:
            - removed_count: Number of alerts deleted
            - execution_time_ms: Cleanup execution time
            - timestamp: ISO timestamp of cleanup
            - status: "success" or "error"
            - error: Error message (if status is "error")
    
    Notes:
        - Stored in module-level variable for health endpoint access
        - Used to determine cleanup_status in /health endpoint
        - Logs update for audit trail
    """
    global last_cleanup_result
    last_cleanup_result = cleanup_result
    
    status = cleanup_result.get('status', 'unknown')
    removed = cleanup_result.get('removed_count', 0)
    exec_time = cleanup_result.get('execution_time_ms', 0)
    
    logging.info(f"Updated cleanup metrics: status={status}, removed={removed}, time={exec_time:.2f}ms")
    

@app.get("/")
async def root():
    """
    Root endpoint with API information.
    
    Provides service metadata and available endpoint documentation for API discovery.
    
    Returns:
        Dict with service name, version, and endpoint list
    
    Example Response:
        {
            "service": "PBS WARN RAG API",
            "version": "1.0.0",
            "endpoints": {
                "query": "/query (POST)",
                "health": "/health (GET)",
                "docs": "/docs (GET)"
            }
        }
    
    Notes:
        - Visit /docs for interactive Swagger UI documentation
        - Visit /redoc for ReDoc-style documentation
    """
    return {
        "service": "PBS WARN RAG API",
        "version": "1.0.0",
        "description": "Retrieval-Augmented Generation service for emergency alerts",
        "endpoints": {
            "query": {
                "path": "/query",
                "method": "POST",
                "description": "Query the RAG system for alert information"
            },
            "health": {
                "path": "/health",
                "method": "GET",
                "description": "Check service health status"
            },
            "history": {
                "path": "/history",
                "method": "GET",
                "description": "Retrieve recent query history"
            },
            "metrics": {
                "path": "/metrics",
                "method": "GET",
                "description": "Retrieve service usage metrics and statistics"
            },
            "docs": {
                "path": "/docs",
                "method": "GET",
                "description": "Interactive API documentation (Swagger UI)"
            },
            "redoc": {
                "path": "/redoc",
                "method": "GET",
                "description": "Alternative API documentation (ReDoc)"
            }
        },
        "data_source": "PBS WARN API",
        "vector_database": "ChromaDB",
        "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
        "llm_provider": "Google Gemini"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
