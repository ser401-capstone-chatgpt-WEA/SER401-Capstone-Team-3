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
from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
import logging
import re
import uuid
from collections import deque

from rags.retriever import AlertRetriever
from rags.generator import ResponseGenerator
from rags.query_utils import preprocess_query, store_query_history, get_query_history
from rags.exceptions import (
    RAGServiceError,
    QueryValidationError,
    RetrieverError,
    GeneratorError,
    rag_exception_to_http
)

logging.basicConfig(
    filename='pbs_warn_scraper.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

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
    """
    request_id = getattr(http_request.state, 'request_id', 'unknown')
    try:
        # Preprocess the query
        processed_query = preprocess_query(request.query)
        logging.info(f"[{request_id}] Processed query: {processed_query}")

        # Validate the query
        validate_query(processed_query)
        logging.info(f"[{request_id}] Query parameters: top_k={request.top_k}, filters={request.filters}")
        
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

        # Store query and result in history
        store_query_history(
            query=processed_query,
            parameters={
                "top_k": request.top_k,
                "filters": request.filters
            },
            response=response
        )
        
        return QueryResponse(**response)
        
    except Exception as e:
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


@app.get("/health")
async def health():
    """
    Service health check endpoint.
    
    Checks health of all RAG system components:
    - AlertRetriever: Database connectivity and document count
    - ResponseGenerator: LLM API availability
    
    Returns:
        Dict with component statuses and database statistics
    
    Example Response:
        {
            "status": "healthy",
            "retriever_status": "healthy",
            "generator_status": "healthy",
            "documents_indexed": 1523,
            "collection_name": "pbs_warn_alerts"
        }
    
    Status Values:
        - "healthy": All components operational
        - "unhealthy": One or more components failed health check
    
    HTTP Status:
        - Always returns 200 (use response body to check actual health)
    
    Notes:
        - Component failures are logged to pbs_warn_scraper.log
        - Monitor this endpoint for production alerting
        - Check documents_indexed to ensure ingestion is working
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

    overall_status = "healthy" if retriever_status == "healthy" and generator_status == "healthy" else "unhealthy"

    return {
        "status": overall_status,
        "retriever_status": retriever_status,
        "generator_status": generator_status,
        "documents_indexed": stats['document_count'] if retriever_status == "healthy" else None,
        "collection_name": retriever.db.collection_name if retriever_status == "healthy" else None
    }


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
